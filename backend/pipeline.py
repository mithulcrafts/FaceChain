"""
Pipeline orchestrators.

Person 1 flow:
Input Image -> Face Processing -> Dual Web Search -> Merged Candidates

FaceChain flow:
Input Image -> Face Processing -> Dual Web Search -> Validation -> Evidence
-> Blockchain Anchor -> On-chain Verification
"""

import uuid
import logging
from pathlib import Path
from typing import List, Union, Optional, Dict
from urllib.parse import urlparse
import cv2
from pydantic import BaseModel, Field

from backend.face import FaceProcessor, FaceDetectionResult, NoFaceDetectedError
from backend.search import BaseSearchProvider, SerpApiGoogleLensProvider, CandidateResult
from backend.validation import CandidateValidator, ValidationDecision, CandidateValidationResult
from backend.evidence import EvidenceBuilder, EvidencePackage
from backend.archive import ArchiveError, ArchivePackage, EvidenceArchiver
from backend.blockchain import (
    AnchorResult,
    BlockchainError,
    EvidenceRegistryClient,
    VerificationResult,
)

logger = logging.getLogger(__name__)


def normalize_url_key(url: str) -> str:
    """Normalize web page or image URL for deduplication."""
    if not url:
        return ""
    parsed = urlparse(url.strip().lower())
    netloc = parsed.netloc.replace("www.", "")
    path = parsed.path.rstrip("/")
    return f"{netloc}{path}"


class Person1Result(BaseModel):
    """
    Standard output payload for Person 1 module.
    Delivers face detection/embedding data + reverse web search candidates to Person 2.
    """
    input_image_path: str = Field(description="Path to input image file")
    primary_face: FaceDetectionResult = Field(description="Primary face detection & 512-d embedding")
    detected_faces_count: int = Field(description="Total number of faces detected in input image")
    candidates: List[CandidateResult] = Field(description="List of reverse-search candidate results")


class FaceChainResult(BaseModel):
    """
    Full pipeline output for face search, validation, evidence, and blockchain.
    """

    input_image_path: str = Field(description="Path to input image file")
    person1: Person1Result = Field(description="Search-stage output")
    validation: ValidationDecision = Field(description="Validation-stage output")
    status: str = Field(description="Pipeline state: rejected, evidence_ready, anchored, verified, failed")
    reason: str = Field(default="", description="Short status reason")
    accepted_candidate: Optional[CandidateValidationResult] = Field(
        default=None,
        description="Accepted candidate after validation",
    )
    evidence: Optional[EvidencePackage] = Field(default=None, description="Deterministic evidence payload")
    archive: Optional[ArchivePackage] = Field(default=None, description="Archived evidence snapshot")
    anchor: Optional[AnchorResult] = Field(default=None, description="On-chain anchoring result")
    verification: Optional[VerificationResult] = Field(default=None, description="On-chain verification result")


class Person1Pipeline:
    """
    Complete Person 1 Pipeline combining Face Processing and Web Reverse-Search.
    Executes both Full-Image search and Face-Crop search, merging and deduplicating results.
    """

    def __init__(
        self,
        face_processor: Optional[FaceProcessor] = None,
        search_provider: Optional[BaseSearchProvider] = None,
        margin_ratio: float = 0.2,
    ):
        """
        Initialize Person 1 Pipeline.

        :param face_processor: Custom FaceProcessor instance. Defaults to InsightFace FaceProcessor().
        :param search_provider: Custom BaseSearchProvider instance. Defaults to SerpApiGoogleLensProvider().
        :param margin_ratio: Margin ratio around bounding box for face cropping (default 0.2).
        """
        self.face_processor = face_processor or FaceProcessor()
        self.search_provider = search_provider or SerpApiGoogleLensProvider()
        self.margin_ratio = margin_ratio

    def run(
        self, 
        image_path: Union[str, Path], 
        results_per_search: int = 30,
        max_candidates: int = 50
    ) -> Person1Result:
        """
        Execute Person 1 End-to-End Workflow with Dual Search (Full Image + Face Crop).

        :param image_path: Local file path of input image.
        :param results_per_search: Maximum candidates to collect per search variant (default 30).
        :param max_candidates: Maximum merged and deduplicated candidates to return (default 50).
        :return: Person1Result object containing face embedding data and candidate search list.
        :raises NoFaceDetectedError: If no face is detected in the input image.
        """
        path = Path(image_path)
        logger.info(f"Starting Person 1 Pipeline for image: {path.name}")

        # Step 1: Detect, Align, and Embed Face
        all_faces = self.face_processor.process_image(path)
        if not all_faces:
            raise NoFaceDetectedError(f"No face detected in input image '{path.name}'. Pipeline aborted.")

        primary_face = all_faces[0]
        logger.info(
            f"Face processing complete. Detected {len(all_faces)} face(s). "
            f"Primary face score: {primary_face.det_score:.2f}, embedding dim: {len(primary_face.embedding)}"
        )

        # Step 2: Full-Image Web Reverse Image Search
        logger.info(f"Initiating full-image search (max {results_per_search} results)...")
        full_image_candidates = self.search_provider.search(path, max_results=results_per_search)
        logger.info(f"Full-image search found {len(full_image_candidates)} candidate(s).")

        # Step 3: Face-Crop Web Reverse Image Search
        crop_path = path.parent / f"_temp_face_crop_{uuid.uuid4().hex[:8]}.jpg"
        face_crop_candidates: List[CandidateResult] = []

        try:
            face_crop_bgr = self.face_processor.create_face_crop(
                path, 
                primary_face.bbox, 
                margin_ratio=self.margin_ratio
            )
            cv2.imwrite(str(crop_path), face_crop_bgr)
            logger.info(f"Generated face crop ({face_crop_bgr.shape[1]}x{face_crop_bgr.shape[0]}px). Initiating face-crop search...")
            
            face_crop_candidates = self.search_provider.search(crop_path, max_results=results_per_search)
            logger.info(f"Face-crop search found {len(face_crop_candidates)} candidate(s).")
        except Exception as exc:
            logger.warning(f"Face-crop search failed or skipped: {exc}")
        finally:
            # Clean up temporary face crop resource
            if crop_path.exists():
                try:
                    crop_path.unlink()
                except Exception as e:
                    logger.warning(f"Failed to remove temporary face crop file {crop_path}: {e}")

        # Step 4: Merge and Deduplicate Candidates
        merged_candidates = self._merge_and_deduplicate(
            full_image_candidates, 
            face_crop_candidates, 
            max_candidates=max_candidates
        )

        logger.info(
            f"Merged dual-search candidates: {len(full_image_candidates)} (full) + "
            f"{len(face_crop_candidates)} (crop) -> {len(merged_candidates)} unique candidates."
        )

        return Person1Result(
            input_image_path=str(path.resolve()),
            primary_face=primary_face,
            detected_faces_count=len(all_faces),
            candidates=merged_candidates,
        )

    def _merge_and_deduplicate(
        self,
        full_image_candidates: List[CandidateResult],
        face_crop_candidates: List[CandidateResult],
        max_candidates: int = 50,
    ) -> List[CandidateResult]:
        """
        Merge full-image and face-crop candidates, deduplicate by normalized URL,
        preserve discovery method metadata, and re-rank.
        """
        merged_dict: Dict[str, CandidateResult] = {}

        # 1. Process full-image candidates
        for item in full_image_candidates:
            key = normalize_url_key(item.url) or normalize_url_key(item.image_url) or item.candidate_id
            item.discovery_method = "full_image"
            merged_dict[key] = item.model_copy()

        # 2. Process face-crop candidates
        for item in face_crop_candidates:
            key = normalize_url_key(item.url) or normalize_url_key(item.image_url) or item.candidate_id
            if key in merged_dict:
                # Discovered by both searches
                merged_dict[key].discovery_method = "both"
            else:
                item.discovery_method = "face_crop"
                merged_dict[key] = item.model_copy()

        # 3. Finalize ranking and cap results
        final_list: List[CandidateResult] = []
        rank = 1
        for candidate in merged_dict.values():
            if rank > max_candidates:
                break
            candidate.search_rank = rank
            final_list.append(candidate)
            rank += 1

        return final_list


class FaceChainPipeline:
    """
    End-to-end FaceID pipeline.

    Keeps reverse-search discovery from Person1Pipeline, then adds:
    - candidate validation
    - evidence canonicalization and hashing
    - blockchain anchoring
    - on-chain verification
    """

    def __init__(
        self,
        person1_pipeline: Optional[Person1Pipeline] = None,
        validator: Optional[CandidateValidator] = None,
        evidence_builder: Optional[EvidenceBuilder] = None,
        evidence_archiver: Optional[EvidenceArchiver] = None,
        blockchain_client: Optional[EvidenceRegistryClient] = None,
        accept_score_floor: Optional[float] = None,
        allow_score_floor_fallback: bool = False,
    ):
        self.person1_pipeline = person1_pipeline or Person1Pipeline()
        self.validator = validator or CandidateValidator()
        self.evidence_builder = evidence_builder or EvidenceBuilder()
        self.evidence_archiver = evidence_archiver or EvidenceArchiver()
        self.blockchain_client = blockchain_client
        self.accept_score_floor = accept_score_floor
        self.allow_score_floor_fallback = allow_score_floor_fallback

    def run(
        self,
        image_path: Union[str, Path],
        results_per_search: int = 30,
        max_candidates: int = 50,
        anchor_on_chain: bool = True,
        verify_on_chain: bool = True,
    ) -> FaceChainResult:
        path = Path(image_path)
        logger.info("Starting FaceChain pipeline for image: %s", path.name)

        person1_result = self.person1_pipeline.run(
            path,
            results_per_search=results_per_search,
            max_candidates=max_candidates,
        )

        validation = self.validator.rank_candidates(
            path,
            person1_result.primary_face,
            person1_result.candidates,
        )

        accepted = validation.accepted or self._accept_by_score_floor(validation)
        if not accepted:
            return FaceChainResult(
                input_image_path=str(path.resolve()),
                person1=person1_result,
                validation=validation,
                status="rejected",
                reason=validation.reason or "no accepted candidate",
            )

        evidence = self.evidence_builder.build(
            accepted.candidate,
            candidate_image_sha256=accepted.candidate_image_sha256,
            source_url=accepted.candidate.url,
        )

        try:
            archive = self.evidence_archiver.archive(evidence)
            evidence = evidence.model_copy(update={"archive_uri": archive.uri})
        except ArchiveError as exc:
            logger.error("Evidence archival failed: %s", exc)
            return FaceChainResult(
                input_image_path=str(path.resolve()),
                person1=person1_result,
                validation=validation,
                status="failed",
                reason=str(exc),
                accepted_candidate=accepted,
                evidence=evidence,
            )

        if not anchor_on_chain:
            return FaceChainResult(
                input_image_path=str(path.resolve()),
                person1=person1_result,
                validation=validation,
                status="evidence_ready",
                reason="anchoring skipped",
                accepted_candidate=accepted,
                evidence=evidence,
            )

        client = self.blockchain_client or EvidenceRegistryClient()

        try:
            anchor = client.anchor_evidence(
                evidence.evidence_hash,
                evidence.record.source,
                source_url=evidence.record.source_url,
                archive_uri=archive.uri,
            )
            verification = client.verify_evidence(
                evidence.evidence_hash,
                expected_source=evidence.record.source,
            ) if verify_on_chain else None

            return FaceChainResult(
                input_image_path=str(path.resolve()),
                person1=person1_result,
                validation=validation,
                status="verified" if verification else "anchored",
                reason="anchored and verified" if verification else "anchored",
                accepted_candidate=accepted,
                evidence=evidence,
                archive=archive,
                anchor=anchor,
                verification=verification,
            )
        except BlockchainError as exc:
            logger.error("Blockchain stage failed: %s", exc)
            return FaceChainResult(
                input_image_path=str(path.resolve()),
                person1=person1_result,
                validation=validation,
                status="failed",
                reason=str(exc),
                accepted_candidate=accepted,
                evidence=evidence,
                archive=archive,
            )

    def _accept_by_score_floor(self, validation: ValidationDecision) -> Optional[CandidateValidationResult]:
        if not self.allow_score_floor_fallback or self.accept_score_floor is None:
            return None
        if not validation.ranked:
            return None

        top = validation.ranked[0]
        if top.matched and top.overall_score >= self.accept_score_floor:
            logger.info(
                "Accepting top candidate by score floor %.3f: overall_score=%.3f margin=%.3f",
                self.accept_score_floor,
                top.overall_score,
                validation.margin,
            )
            return top
        return None
