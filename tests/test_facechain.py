"""
Unit tests for the full FaceChain orchestration pipeline.
"""

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from backend.blockchain import AnchorResult, VerificationResult
from backend.evidence import EvidencePackage, EvidenceRecord
from backend.face.models import FaceDetectionResult
from backend.pipeline import FaceChainPipeline, FaceChainResult, Person1Result
from backend.search.models import CandidateResult
from backend.validation import CandidateValidator
from backend.validation import CandidateValidationResult, ValidationDecision


def _write_image(path: Path, color: int) -> None:
    image = np.full((64, 64, 3), color, dtype=np.uint8)
    cv2.circle(image, (32, 32), 18, (255 - color, 255 - color, 255 - color), -1)
    cv2.imwrite(str(path), image)


class TestFaceChainPipeline(unittest.TestCase):
    def test_accepts_top_candidate_by_score_floor(self):
        primary_face = FaceDetectionResult(
            bbox=[0.0, 0.0, 10.0, 10.0],
            det_score=0.99,
            embedding=[0.5] * 512,
            landmarks=None,
            aligned_face_shape=None,
        )
        candidate = CandidateResult(
            candidate_id="candidate-1",
            url="https://example.com/post/1",
            image_url="https://example.com/image.jpg",
            title="Found Post",
            snippet="Matched caption",
            source="example.com",
            metadata={"author": "Alice", "timestamp": "2026-09-06T12:00:00Z"},
        )
        person1_result = Person1Result(
            input_image_path="/tmp/input.jpg",
            primary_face=primary_face,
            detected_faces_count=1,
            candidates=[candidate],
        )
        top = CandidateValidationResult(
            candidate=candidate,
            matched=True,
            face_similarity=0.91,
            image_similarity=0.90,
            source_consistency=1.0,
            completeness=1.0,
            overall_score=0.88,
            candidate_image_sha256="abc123",
            candidate_image_path="/tmp/candidate.jpg",
            reason="accepted",
        )
        validation = ValidationDecision(accepted=None, ranked=[top], margin=0.01, reason="ambiguous candidates")

        person1_pipeline = MagicMock()
        person1_pipeline.run.return_value = person1_result

        validator = MagicMock()
        validator.rank_candidates.return_value = validation

        evidence_builder = MagicMock()
        evidence_builder.build.return_value = EvidencePackage(
            record=EvidenceRecord(
                schema_version="1.0",
                source="example.com",
                source_url="https://example.com/post/1",
                title="Found Post",
                caption="Matched caption",
                author="Alice",
                timestamp="2026-09-06T12:00:00Z",
                image_sha256="abc123",
            ),
            canonical_json='{"schema_version":"1.0","source":"example.com","source_url":"https://example.com/post/1","title":"Found Post","caption":"Matched caption","author":"Alice","timestamp":"2026-09-06T12:00:00Z","image_sha256":"abc123"}',
            evidence_hash="0x" + "4" * 64,
            candidate_id="candidate-1",
            candidate_url="https://example.com/post/1",
            candidate_source="example.com",
            candidate_image_sha256="abc123",
        )

        blockchain_client = MagicMock()
        blockchain_client.anchor_evidence.return_value = AnchorResult(
            evidence_hash="0x" + "4" * 64,
            transaction_hash="0x" + "1" * 64,
            stored_timestamp=1700000000,
            stored_source="example.com",
        )
        blockchain_client.verify_evidence.return_value = VerificationResult(
            evidence_hash="0x" + "4" * 64,
            anchored=True,
            exists=True,
            submitter="0x" + "2" * 40,
            timestamp=1700000000,
            source="example.com",
            source_matches=True,
            hash_matches=True,
        )

        pipeline = FaceChainPipeline(
            person1_pipeline=person1_pipeline,
            validator=validator,
            evidence_builder=evidence_builder,
            blockchain_client=blockchain_client,
            accept_score_floor=0.85,
        )
        result = pipeline.run(Path("/tmp/input.jpg"))

        self.assertEqual(result.status, "verified")
        self.assertEqual(result.reason, "anchored and verified")
        self.assertIsNotNone(result.accepted_candidate)
        self.assertEqual(result.accepted_candidate.candidate.candidate_id, "candidate-1")

    def test_full_pipeline_smoke_with_real_validator_and_mocked_chain(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            input_path = tmpdir_path / "input.jpg"
            candidate_path = Path(tempfile.gettempdir()) / "facechain_smoke_candidate.jpg"
            _write_image(input_path, 120)
            _write_image(candidate_path, 120)

            primary_face = FaceDetectionResult(
                bbox=[0.0, 0.0, 10.0, 10.0],
                det_score=0.99,
                embedding=[0.5] * 512,
                landmarks=None,
                aligned_face_shape=None,
            )
            candidate = CandidateResult(
                candidate_id="candidate-1",
                url="https://example.com/post/1",
                image_url="https://example.com/image.jpg",
                title="Found Post",
                snippet="Matched caption",
                source="example.com",
                metadata={"author": "Alice", "timestamp": "2026-09-06T12:00:00Z"},
            )
            person1_result = Person1Result(
                input_image_path=str(input_path),
                primary_face=primary_face,
                detected_faces_count=1,
                candidates=[candidate],
            )

            accepted = CandidateValidationResult(
                candidate=candidate,
                matched=True,
                face_similarity=0.98,
                image_similarity=0.95,
                source_consistency=1.0,
                completeness=1.0,
                overall_score=0.96,
                candidate_image_sha256=hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
                candidate_image_path=str(candidate_path),
                reason="accepted",
            )
            validation = ValidationDecision(accepted=accepted, ranked=[accepted], margin=0.2, reason="accepted")

            person1_pipeline = MagicMock()
            person1_pipeline.run.return_value = person1_result

            validator = CandidateValidator()
            with patch.object(validator, "validate_candidate", return_value=accepted), \
                 patch.object(validator, "rank_candidates", return_value=validation):
                evidence_builder = MagicMock()
                evidence_builder.build.return_value = EvidencePackage(
                    record=EvidenceRecord(
                        schema_version="1.0",
                        source="example.com",
                        source_url="https://example.com/post/1",
                        title="Found Post",
                        caption="Matched caption",
                        author="Alice",
                        timestamp="2026-09-06T12:00:00Z",
                        image_sha256=accepted.candidate_image_sha256,
                    ),
                    canonical_json='{"schema_version":"1.0","source":"example.com","source_url":"https://example.com/post/1","title":"Found Post","caption":"Matched caption","author":"Alice","timestamp":"2026-09-06T12:00:00Z","image_sha256":"%s"}'
                    % accepted.candidate_image_sha256,
                    evidence_hash="0x" + "4" * 64,
                    candidate_id="candidate-1",
                    candidate_url="https://example.com/post/1",
                    candidate_source="example.com",
                    candidate_image_sha256=accepted.candidate_image_sha256,
                )

                blockchain_client = MagicMock()
                blockchain_client.anchor_evidence.return_value = AnchorResult(
                    evidence_hash="0x" + "4" * 64,
                    transaction_hash="0x" + "1" * 64,
                    stored_timestamp=1700000000,
                    stored_source="example.com",
                )
                blockchain_client.verify_evidence.return_value = VerificationResult(
                    evidence_hash="0x" + "4" * 64,
                    anchored=True,
                    exists=True,
                    submitter="0x" + "2" * 40,
                    timestamp=1700000000,
                    source="example.com",
                    source_matches=True,
                    hash_matches=True,
                )

                pipeline = FaceChainPipeline(
                    person1_pipeline=person1_pipeline,
                    validator=validator,
                    evidence_builder=evidence_builder,
                    blockchain_client=blockchain_client,
                )
                result = pipeline.run(input_path)

            self.assertEqual(result.status, "verified")
            self.assertEqual(result.reason, "anchored and verified")
            self.assertEqual(result.person1.candidates[0].candidate_id, "candidate-1")
            self.assertEqual(result.accepted_candidate.candidate.candidate_id, "candidate-1")
            self.assertEqual(result.evidence.record.author, "Alice")
            self.assertEqual(result.anchor.stored_source, "example.com")
            self.assertTrue(result.verification.hash_matches)

            if candidate_path.exists():
                candidate_path.unlink()

    def test_run_anchors_and_verifies_accepted_candidate(self):
        primary_face = FaceDetectionResult(
            bbox=[0.0, 0.0, 10.0, 10.0],
            det_score=0.99,
            embedding=[0.5] * 512,
            landmarks=None,
            aligned_face_shape=None,
        )
        candidate = CandidateResult(
            candidate_id="candidate-1",
            url="https://example.com/post/1",
            image_url="https://example.com/image.jpg",
            title="Found Post",
            snippet="Matched caption",
            source="example.com",
        )
        person1_result = Person1Result(
            input_image_path="/tmp/input.jpg",
            primary_face=primary_face,
            detected_faces_count=1,
            candidates=[candidate],
        )
        accepted = CandidateValidationResult(
            candidate=candidate,
            matched=True,
            face_similarity=0.98,
            image_similarity=0.95,
            source_consistency=1.0,
            completeness=1.0,
            overall_score=0.96,
            candidate_image_sha256="abc123",
            candidate_image_path="/tmp/candidate.jpg",
            reason="accepted",
        )
        validation = ValidationDecision(accepted=accepted, ranked=[accepted], margin=0.2, reason="accepted")
        evidence = EvidencePackage(
            record=EvidenceRecord(
                schema_version="1.0",
                source="example.com",
                source_url="https://example.com/post/1",
                title="Found Post",
                caption="Matched caption",
                author="Alice",
                timestamp="2026-09-06T12:00:00Z",
                image_sha256="abc123",
            ),
            canonical_json='{"schema_version":"1.0","source":"example.com","source_url":"https://example.com/post/1","title":"Found Post","caption":"Matched caption","author":"Alice","timestamp":"2026-09-06T12:00:00Z","image_sha256":"abc123"}',
            evidence_hash="0x" + "4" * 64,
            candidate_id="candidate-1",
            candidate_url="https://example.com/post/1",
            candidate_source="example.com",
            candidate_image_sha256="abc123",
        )

        person1_pipeline = MagicMock()
        person1_pipeline.run.return_value = person1_result

        validator = MagicMock()
        validator.rank_candidates.return_value = validation

        evidence_builder = MagicMock()
        evidence_builder.build.return_value = evidence

        blockchain_client = MagicMock()
        blockchain_client.anchor_evidence.return_value = AnchorResult(
            evidence_hash=evidence.evidence_hash,
            transaction_hash="0x" + "1" * 64,
            stored_timestamp=1700000000,
            stored_source="example.com",
        )
        blockchain_client.verify_evidence.return_value = VerificationResult(
            evidence_hash=evidence.evidence_hash,
            anchored=True,
            exists=True,
            submitter="0x" + "2" * 40,
            timestamp=1700000000,
            source="example.com",
            source_matches=True,
            hash_matches=True,
        )

        pipeline = FaceChainPipeline(
            person1_pipeline=person1_pipeline,
            validator=validator,
            evidence_builder=evidence_builder,
            blockchain_client=blockchain_client,
        )
        result = pipeline.run(Path("/tmp/input.jpg"))

        self.assertIsInstance(result, FaceChainResult)
        self.assertEqual(result.status, "verified")
        self.assertIsNotNone(result.evidence)
        self.assertIsNotNone(result.anchor)
        self.assertIsNotNone(result.verification)
        self.assertEqual(result.evidence.evidence_hash, evidence.evidence_hash)
        self.assertEqual(result.anchor.transaction_hash, "0x" + "1" * 64)
        self.assertTrue(result.verification.anchored)

    def test_run_rejects_when_no_candidate_passes(self):
        primary_face = FaceDetectionResult(
            bbox=[0.0, 0.0, 10.0, 10.0],
            det_score=0.99,
            embedding=[0.5] * 512,
            landmarks=None,
            aligned_face_shape=None,
        )
        person1_result = Person1Result(
            input_image_path="/tmp/input.jpg",
            primary_face=primary_face,
            detected_faces_count=1,
            candidates=[],
        )

        person1_pipeline = MagicMock()
        person1_pipeline.run.return_value = person1_result

        validation = ValidationDecision(accepted=None, ranked=[], margin=0.0, reason="no accepted candidates")
        validator = MagicMock()
        validator.rank_candidates.return_value = validation

        pipeline = FaceChainPipeline(person1_pipeline=person1_pipeline, validator=validator)
        result = pipeline.run(Path("/tmp/input.jpg"), anchor_on_chain=False)

        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.reason, "no accepted candidates")
        self.assertIsNone(result.evidence)
        self.assertIsNone(result.anchor)
