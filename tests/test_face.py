"""
Unit tests for backend/face module and Person1Pipeline.
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


class MockSearchProvider(BaseSearchProvider):
    def search(self, image_input, max_results=10):
        return [
            CandidateResult(
                candidate_id="mock-uuid-1",
                url="https://example.com/speaker",
                image_url="https://example.com/speaker.jpg",
                title="Speaker Profile",
                snippet="Tech Speaker",
                source="example.com",
                search_rank=1,
            )
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

    def test_no_face_detected_raises_error(self):
        with patch.object(self.processor, "_app") as mock_app:
            mock_app.get.return_value = []
            with self.assertRaises(NoFaceDetectedError):
                self.processor.get_primary_face(self.blank_img)

    def test_invalid_image_path_raises_error(self):
        with self.assertRaises(InvalidImageError):
            self.processor.process_image("definitely_non_existent_image_123.jpg")

    def test_person1_pipeline_integration(self):
        mock_face = MagicMock()
        mock_face.bbox = np.array([50.0, 50.0, 200.0, 200.0])
        mock_face.det_score = 0.98
        mock_face.embedding = np.random.randn(512).astype(np.float32)
        mock_face.kps = np.array([[70, 80], [130, 80], [100, 110], [80, 140], [120, 140]])
        mock_face.norm_crop = np.zeros((112, 112, 3), dtype=np.uint8)

        temp_path = Path("temp_test_face.jpg")
        cv2.imwrite(str(temp_path), self.synthetic_face_img)

        try:
            with patch.object(self.processor, "_app") as mock_app:
                mock_app.get.return_value = [mock_face]
                pipeline = Person1Pipeline(
                    face_processor=self.processor,
                    search_provider=MockSearchProvider(),
                )
                result = pipeline.run(temp_path, max_search_results=5)

            self.assertIsInstance(result, Person1Result)
            self.assertEqual(len(result.primary_face.embedding), 512)
            self.assertEqual(len(result.candidates), 1)
            self.assertEqual(result.candidates[0].source, "example.com")
        finally:
            if temp_path.exists():
                temp_path.unlink()


if __name__ == "__main__":
    unittest.main()
