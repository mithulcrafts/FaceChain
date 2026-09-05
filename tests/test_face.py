"""
Unit tests for backend/face module and Person1Pipeline dual-search functionality.
"""

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import numpy as np
import cv2

from backend.face import (
    FaceProcessor,
    FaceDetectionResult,
    NoFaceDetectedError,
    InvalidImageError,
)
from backend.pipeline import Person1Pipeline, Person1Result
from backend.search.base import BaseSearchProvider
from backend.search.models import CandidateResult


class MultiSearchMockProvider(BaseSearchProvider):
    """Mock search provider returning different candidate lists based on input file."""

    def search(self, image_input, max_results=30):
        img_name = str(image_input)
        if "_temp_face_crop" in img_name:
            # Face-crop search results
            return [
                CandidateResult(
                    candidate_id="crop-1",
                    url="https://example.com/shared_post", # Duplicate (appears in full_image too)
                    image_url="https://example.com/shared.jpg",
                    title="Shared Profile",
                    source="example.com",
                ),
                CandidateResult(
                    candidate_id="crop-2",
                    url="https://instagram.com/p/face_only", # Unique to face crop
                    image_url="https://instagram.com/pic2.jpg",
                    title="Instagram Selfie",
                    source="instagram.com",
                ),
            ]
        else:
            # Full-image search results
            return [
                CandidateResult(
                    candidate_id="full-1",
                    url="https://example.com/shared_post", # Duplicate
                    image_url="https://example.com/shared.jpg",
                    title="Shared Profile",
                    source="example.com",
                ),
                CandidateResult(
                    candidate_id="full-2",
                    url="https://twitter.com/janedoe/status/123", # Unique to full image
                    image_url="https://twitter.com/pic1.jpg",
                    title="Twitter Post",
                    source="twitter.com",
                ),
            ]


class TestFaceProcessor(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.processor = FaceProcessor()

    def setUp(self):
        # Create a simple synthetic face image (white background with dark face circle and eyes)
        img = np.ones((300, 300, 3), dtype=np.uint8) * 255
        cv2.circle(img, (150, 150), 60, (100, 100, 100), -1)  # Head
        cv2.circle(img, (130, 130), 10, (0, 0, 0), -1)        # Left eye
        cv2.circle(img, (170, 130), 10, (0, 0, 0), -1)        # Right eye
        cv2.ellipse(img, (150, 170), (20, 10), 0, 0, 180, (0, 0, 0), 3) # Mouth
        self.synthetic_face_img = img

        # Create a blank black image with no face
        self.blank_img = np.zeros((300, 300, 3), dtype=np.uint8)

    def test_process_image_returns_detection_result(self):
        mock_face = MagicMock()
        mock_face.bbox = np.array([50.0, 50.0, 200.0, 200.0])
        mock_face.det_score = 0.98
        mock_face.embedding = np.random.randn(512).astype(np.float32)
        mock_face.kps = np.array([[70, 80], [130, 80], [100, 110], [80, 140], [120, 140]])
        mock_face.norm_crop = np.zeros((112, 112, 3), dtype=np.uint8)

        with patch.object(self.processor, "_app") as mock_app:
            mock_app.get.return_value = [mock_face]
            results = self.processor.process_image(self.synthetic_face_img)

        self.assertEqual(len(results), 1)
        face = results[0]
        self.assertIsInstance(face, FaceDetectionResult)
        self.assertEqual(len(face.embedding), 512)
        self.assertEqual(len(face.bbox), 4)
        self.assertAlmostEqual(face.det_score, 0.98)

    def test_face_crop_generation_with_margin(self):
        bbox = [100.0, 100.0, 200.0, 200.0]
        crop = self.processor.create_face_crop(self.synthetic_face_img, bbox, margin_ratio=0.2)
        
        # Bbox width = 100, height = 100. 20% margin adds 20px on each side -> (100 + 40) x (100 + 40) = 140x140
        self.assertEqual(crop.shape[0], 140)
        self.assertEqual(crop.shape[1], 140)

    def test_no_face_detected_raises_error(self):
        with patch.object(self.processor, "_app") as mock_app:
            mock_app.get.return_value = []
            with self.assertRaises(NoFaceDetectedError):
                self.processor.get_primary_face(self.blank_img)

    def test_invalid_image_path_raises_error(self):
        with self.assertRaises(InvalidImageError):
            self.processor.process_image("definitely_non_existent_image_123.jpg")

    def test_person1_dual_search_merging_deduplication_and_metadata(self):
        mock_face = MagicMock()
        mock_face.bbox = np.array([50.0, 50.0, 200.0, 200.0])
        mock_face.det_score = 0.98
        mock_face.embedding = np.random.randn(512).astype(np.float32)
        mock_face.kps = np.array([[70, 80], [130, 80], [100, 110], [80, 140], [120, 140]])
        mock_face.norm_crop = np.zeros((112, 112, 3), dtype=np.uint8)

        temp_path = Path("temp_test_dual_face.jpg")
        cv2.imwrite(str(temp_path), self.synthetic_face_img)

        try:
            with patch.object(self.processor, "_app") as mock_app:
                mock_app.get.return_value = [mock_face]
                pipeline = Person1Pipeline(
                    face_processor=self.processor,
                    search_provider=MultiSearchMockProvider(),
                )
                result = pipeline.run(temp_path, results_per_search=30, max_candidates=50)

            self.assertIsInstance(result, Person1Result)
            # 3 unique candidates should be returned (1 shared, 1 full_image only, 1 face_crop only)
            self.assertEqual(len(result.candidates), 3)

            by_url = {c.url: c for c in result.candidates}
            
            # Verify discovery_method metadata tag
            self.assertEqual(by_url["https://example.com/shared_post"].discovery_method, "both")
            self.assertEqual(by_url["https://twitter.com/janedoe/status/123"].discovery_method, "full_image")
            self.assertEqual(by_url["https://instagram.com/p/face_only"].discovery_method, "face_crop")

            # Verify rank updates
            self.assertEqual([c.search_rank for c in result.candidates], [1, 2, 3])

        finally:
            if temp_path.exists():
                temp_path.unlink()

            # Ensure temporary crop files were cleaned up
            temp_crop_files = list(Path(".").glob("_temp_face_crop_*.jpg"))
            self.assertEqual(len(temp_crop_files), 0, "Temporary face crop files were not cleaned up.")

    def test_max_candidates_limit_capping(self):
        mock_face = MagicMock()
        mock_face.bbox = np.array([50.0, 50.0, 200.0, 200.0])
        mock_face.det_score = 0.98
        mock_face.embedding = np.random.randn(512).astype(np.float32)

        temp_path = Path("temp_test_cap_face.jpg")
        cv2.imwrite(str(temp_path), self.synthetic_face_img)

        try:
            with patch.object(self.processor, "_app") as mock_app:
                mock_app.get.return_value = [mock_face]
                pipeline = Person1Pipeline(
                    face_processor=self.processor,
                    search_provider=MultiSearchMockProvider(),
                )
                # Request max 2 candidates cap
                result = pipeline.run(temp_path, results_per_search=30, max_candidates=2)

            self.assertEqual(len(result.candidates), 2)
        finally:
            if temp_path.exists():
                temp_path.unlink()


if __name__ == "__main__":
    unittest.main()
