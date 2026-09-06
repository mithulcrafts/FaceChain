"""
Unit tests for candidate validation and ranking.
"""

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from backend.face.models import FaceDetectionResult
from backend.search.models import CandidateResult
from backend.validation import CandidateValidator, CandidateValidationResult


def _write_image(path: Path, color: int) -> None:
    image = np.full((64, 64, 3), color, dtype=np.uint8)
    cv2.circle(image, (32, 32), 18, (255 - color, 255 - color, 255 - color), -1)
    cv2.imwrite(str(path), image)


class TestCandidateValidation(unittest.TestCase):
    def test_source_consistency_handles_human_readable_source_names(self):
        validator = CandidateValidator()
        candidate = CandidateResult(
            candidate_id="candidate-1",
            url="https://www.mansworldindia.com/fashion/style/beyond-50-odi-centuries-virat-kohli-style-influence",
            image_url="https://example.com/image.jpg",
            source="Man's World India",
        )

        self.assertEqual(validator._source_consistency(candidate), 0.75)

    def test_validate_candidate_accepts_matching_assets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            input_path = tmpdir_path / "input.jpg"
            candidate_handle = tempfile.NamedTemporaryFile(delete=False, dir=tempfile.gettempdir(), suffix=".jpg")
            candidate_path = Path(candidate_handle.name)
            candidate_handle.close()
            _write_image(input_path, 120)
            _write_image(candidate_path, 120)

            candidate = CandidateResult(
                candidate_id="candidate-1",
                url="https://example.com/post/1",
                image_url="https://example.com/image.jpg",
                title="Found Post",
                snippet="Matched caption",
                source="example.com",
            )
            face = FaceDetectionResult(
                bbox=[0.0, 0.0, 10.0, 10.0],
                det_score=0.99,
                embedding=[0.5] * 512,
                landmarks=None,
                aligned_face_shape=None,
            )
            candidate_face = FaceDetectionResult(
                bbox=[0.0, 0.0, 10.0, 10.0],
                det_score=0.98,
                embedding=[0.5] * 512,
                landmarks=None,
                aligned_face_shape=None,
            )
            candidate_hash = hashlib.sha256(candidate_path.read_bytes()).hexdigest()

            validator = CandidateValidator()
            with patch.object(validator, "_download_candidate_asset", return_value=(candidate_path, candidate_hash)), \
                 patch.object(validator.face_processor, "process_image", return_value=[candidate_face]):
                result = validator.validate_candidate(input_path, face, candidate)

            self.assertTrue(result.matched)
            self.assertGreaterEqual(result.face_similarity, validator.face_threshold)
            self.assertGreaterEqual(result.image_similarity, validator.image_threshold)
            self.assertEqual(result.candidate_image_sha256, candidate_hash)
            self.assertFalse(candidate_path.exists())

    def test_rank_candidates_selects_clear_winner(self):
        validator = CandidateValidator()
        top = CandidateValidationResult(
            candidate=CandidateResult(
                candidate_id="top",
                url="https://example.com/top",
                image_url="https://example.com/top.jpg",
            ),
            matched=True,
            overall_score=0.93,
        )
        runner_up = CandidateValidationResult(
            candidate=CandidateResult(
                candidate_id="runner",
                url="https://example.com/runner",
                image_url="https://example.com/runner.jpg",
            ),
            matched=True,
            overall_score=0.70,
        )

        with patch.object(validator, "validate_candidate", side_effect=[top, runner_up]):
            decision = validator.rank_candidates(
                "input.jpg",
                FaceDetectionResult(bbox=[0, 0, 1, 1], det_score=1.0, embedding=[1.0] * 512),
                [top.candidate, runner_up.candidate],
            )

        self.assertIsNotNone(decision.accepted)
        self.assertEqual(decision.accepted.candidate.candidate_id, "top")
        self.assertGreaterEqual(decision.margin, validator.min_margin)
