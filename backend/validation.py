"""
Candidate validation and ranking.

Validates search candidates with:
- independent face matching
- image similarity support
- source/content consistency
- completeness scoring

Also keeps the simple image downloader used by older tests and demos.
"""

from __future__ import annotations

import hashlib
import logging
import re
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple, Union
from urllib.parse import urlparse

import cv2
import numpy as np
import requests
from pydantic import BaseModel, Field

from backend.face import FaceDetectionResult, FaceProcessor, InvalidImageError
from backend.search.models import CandidateResult

logger = logging.getLogger(__name__)

def download_candidate_image(url, save_path):
    print(f"[*] Attempting to download candidate image from: {url}")

    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        with open(save_path, "wb") as file:
            file.write(response.content)

        print(f"[+] SUCCESS: Image saved to {save_path}")
        return True

    except requests.exceptions.RequestException as e:
        print(f"[-] ERROR: Failed to download image. Reason: {e}")
        return False

def _normalize_domain(value: str) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    domain = parsed.netloc if parsed.scheme else value
    return domain.lower().replace("www.", "").strip()


def _normalize_source_key(value: str) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        raw = f"{parsed.netloc}{parsed.path}"
    else:
        raw = value
    return re.sub(r"[^a-z0-9]+", "", raw.lower())


def _cosine_similarity(left: List[float], right: List[float]) -> float:
    if not left or not right:
        return 0.0

    a = np.asarray(left, dtype=np.float32)
    b = np.asarray(right, dtype=np.float32)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.clip(np.dot(a, b) / denom, -1.0, 1.0))


def _normalized_similarity_score(value: float) -> float:
    # Map cosine similarity [-1, 1] to [0, 1].
    return float((value + 1.0) / 2.0)


def _read_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path))
    if image is None:
        raise InvalidImageError(f"Failed to read image at path: {path.resolve()}")
    return image


def _image_histogram_similarity(left: np.ndarray, right: np.ndarray) -> float:
    if left.size == 0 or right.size == 0:
        return 0.0

    left_hsv = cv2.cvtColor(left, cv2.COLOR_BGR2HSV)
    right_hsv = cv2.cvtColor(right, cv2.COLOR_BGR2HSV)

    left_hist = cv2.calcHist([left_hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
    right_hist = cv2.calcHist([right_hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
    cv2.normalize(left_hist, left_hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    cv2.normalize(right_hist, right_hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

    score = float(cv2.compareHist(left_hist, right_hist, cv2.HISTCMP_CORREL))
    return float(np.clip((score + 1.0) / 2.0, 0.0, 1.0))


class CandidateValidationResult(BaseModel):
    candidate: CandidateResult
    matched: bool
    face_similarity: float = Field(default=0.0)
    image_similarity: float = Field(default=0.0)
    source_consistency: float = Field(default=0.0)
    completeness: float = Field(default=0.0)
    overall_score: float = Field(default=0.0)
    input_faces: int = Field(default=0)
    candidate_faces: int = Field(default=0)
    face_margin: float = Field(default=0.0)
    candidate_image_sha256: str = Field(default="")
    candidate_image_path: str = Field(default="")
    reason: str = Field(default="")


class ValidationDecision(BaseModel):
    accepted: Optional[CandidateValidationResult] = None
    ranked: List[CandidateValidationResult] = Field(default_factory=list)
    margin: float = Field(default=0.0)
    reason: str = Field(default="")


class CandidateValidator:
    """
    Validate and rank candidates.
    """

    def __init__(
        self,
        face_processor: Optional[FaceProcessor] = None,
        face_threshold: float = 0.70,
        image_threshold: float = 0.50,
        confidence_threshold: float = 0.70,
        min_margin: float = 0.02,
        max_validation_candidates: int = 20,
    ):
        self.face_processor = face_processor or FaceProcessor()
        self.face_threshold = face_threshold
        self.image_threshold = image_threshold
        self.confidence_threshold = confidence_threshold
        self.min_margin = min_margin
        self.max_validation_candidates = max_validation_candidates

    def validate_candidate(
        self,
        input_image_path: Union[str, Path],
        input_face: FaceDetectionResult,
        candidate: CandidateResult,
    ) -> CandidateValidationResult:
        input_path = Path(input_image_path)
        if not input_path.is_file():
            raise InvalidImageError(f"Input image file does not exist: {input_path.resolve()}")

        candidate_image_path, candidate_image_sha256 = self._download_candidate_asset(candidate)
        if candidate_image_path is None:
            return CandidateValidationResult(
                candidate=candidate,
                matched=False,
                reason="candidate image unavailable",
            )

        try:
            candidate_faces = self.face_processor.process_image(candidate_image_path)
            candidate_face_count = len(candidate_faces)
            if candidate_face_count == 0:
                return CandidateValidationResult(
                    candidate=candidate,
                    matched=False,
                    candidate_image_sha256=candidate_image_sha256,
                    candidate_image_path=str(candidate_image_path),
                    reason="no face detected in candidate image",
                )

            face_scores = [_cosine_similarity(input_face.embedding, face.embedding) for face in candidate_faces]
            best_face_score = max(face_scores)
            runner_up = sorted(face_scores, reverse=True)[1] if len(face_scores) > 1 else -1.0
            face_margin = best_face_score - runner_up if len(face_scores) > 1 else best_face_score
            face_similarity = _normalized_similarity_score(best_face_score)

            input_bgr = _read_image(input_path)
            candidate_bgr = _read_image(candidate_image_path)
            image_similarity = _image_histogram_similarity(input_bgr, candidate_bgr)
            source_consistency = self._source_consistency(candidate)
            completeness = self._completeness(candidate)

            overall_score = (
                (face_similarity * 0.55)
                + (image_similarity * 0.20)
                + (source_consistency * 0.15)
                + (completeness * 0.10)
            )

            matched = (
                face_similarity >= self.face_threshold
                and image_similarity >= self.image_threshold
                and overall_score >= self.confidence_threshold
            )
            reason = "accepted" if matched else self._reject_reason(
                face_similarity=face_similarity,
                image_similarity=image_similarity,
                overall_score=overall_score,
            )

            return CandidateValidationResult(
                candidate=candidate,
                matched=matched,
                face_similarity=face_similarity,
                image_similarity=image_similarity,
                source_consistency=source_consistency,
                completeness=completeness,
                overall_score=overall_score,
                input_faces=1,
                candidate_faces=candidate_face_count,
                face_margin=face_margin,
                candidate_image_sha256=candidate_image_sha256,
                candidate_image_path=str(candidate_image_path),
                reason=reason,
            )
        finally:
            if candidate_image_path.exists() and candidate_image_path.parent == Path(tempfile.gettempdir()):
                try:
                    candidate_image_path.unlink()
                except Exception:
                    pass

    def rank_candidates(
        self,
        input_image_path: Union[str, Path],
        input_face: FaceDetectionResult,
        candidates: List[CandidateResult],
    ) -> ValidationDecision:
        shortlisted = self._prefilter_candidates(candidates)
        results = [self.validate_candidate(input_image_path, input_face, candidate) for candidate in shortlisted]
        results.sort(key=lambda item: item.overall_score, reverse=True)

        accepted = None
        margin = 0.0
        reason = "no accepted candidates"

        if results:
            top = results[0]
            runner_up_score = results[1].overall_score if len(results) > 1 else 0.0
            margin = top.overall_score - runner_up_score

            if top.matched and margin >= self.min_margin:
                accepted = top
                reason = "accepted"
            elif not top.matched:
                reason = top.reason
            else:
                reason = "ambiguous candidates"

        return ValidationDecision(accepted=accepted, ranked=results, margin=margin, reason=reason)

    def _prefilter_candidates(self, candidates: List[CandidateResult]) -> List[CandidateResult]:
        ranked = [
            candidate
            for candidate in candidates
            if candidate.url or candidate.image_url
        ]
        ranked.sort(key=self._prefilter_score, reverse=True)
        return ranked[: self.max_validation_candidates]

    def _prefilter_score(self, candidate: CandidateResult) -> float:
        score = 0.0
        score += 0.3 if candidate.url else 0.0
        score += 0.3 if candidate.image_url else 0.0
        score += 0.15 if candidate.title else 0.0
        score += 0.10 if candidate.snippet else 0.0
        score += 0.10 if candidate.discovery_method == "both" else 0.0
        if candidate.search_rank > 0:
            score += max(0.0, 0.15 - (candidate.search_rank - 1) * 0.003)
        return score

    def _source_consistency(self, candidate: CandidateResult) -> float:
        source_domain = _normalize_domain(candidate.source)
        source_key = _normalize_source_key(candidate.source)
        url_domain = _normalize_domain(candidate.url)
        url_key = _normalize_source_key(candidate.url)
        image_domain = _normalize_domain(candidate.image_url)
        image_key = _normalize_source_key(candidate.image_url)

        if not source_domain and not source_key:
            return 0.5 if (url_domain or image_domain) else 0.0
        if source_domain == url_domain or source_domain == image_domain:
            return 1.0
        if source_key and (source_key == url_key or source_key == image_key):
            return 1.0
        if source_domain in url_domain or source_domain in image_domain or url_domain in source_domain:
            return 0.75
        if source_key and (source_key in url_key or source_key in image_key or url_key in source_key or image_key in source_key):
            return 0.75
        source_tokens = set(re.findall(r"[a-z0-9]+", (candidate.source or "").lower()))
        if source_tokens:
            url_tokens = set(re.findall(r"[a-z0-9]+", (candidate.url or "").lower()))
            image_tokens = set(re.findall(r"[a-z0-9]+", (candidate.image_url or "").lower()))
            if source_tokens & (url_tokens | image_tokens):
                return 0.75
        return 0.25

    def _completeness(self, candidate: CandidateResult) -> float:
        score = 0.0
        score += 0.25 if candidate.url else 0.0
        score += 0.25 if candidate.image_url else 0.0
        score += 0.20 if candidate.title else 0.0
        score += 0.20 if candidate.snippet else 0.0
        score += 0.10 if candidate.source else 0.0
        return score

    def _download_candidate_asset(self, candidate: CandidateResult) -> Tuple[Optional[Path], str]:
        reference = candidate.image_url or candidate.url
        if not reference:
            return None, ""

        parsed = urlparse(reference)
        if parsed.scheme not in ("http", "https"):
            path = Path(reference)
            if path.is_file():
                return path, hashlib.sha256(path.read_bytes()).hexdigest()
            return None, ""

        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as handle:
            temp_path = Path(handle.name)

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        try:
            response = requests.get(reference, headers=headers, timeout=20)
            response.raise_for_status()
            temp_path.write_bytes(response.content)
            return temp_path, hashlib.sha256(response.content).hexdigest()
        except Exception as exc:
            logger.warning("Candidate image download failed for %s: %s", reference, exc)
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            return None, ""

    def _reject_reason(self, face_similarity: float, image_similarity: float, overall_score: float) -> str:
        if face_similarity < self.face_threshold:
            return "face similarity below threshold"
        if image_similarity < self.image_threshold:
            return "image similarity below threshold"
        if overall_score < self.confidence_threshold:
            return "overall score below threshold"
        return "rejected"
