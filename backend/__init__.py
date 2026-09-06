"""
Backend package for FaceID Blockchain Verification Pipeline.
"""

from backend.pipeline import Person1Pipeline, Person1Result, FaceChainPipeline, FaceChainResult
from backend.evidence import EvidenceBuilder, EvidencePackage, EvidenceRecord
from backend.validation import CandidateValidator, CandidateValidationResult, ValidationDecision
from backend.blockchain import EvidenceRegistryClient, AnchorResult, VerificationResult

__all__ = [
    "Person1Pipeline",
    "Person1Result",
    "FaceChainPipeline",
    "FaceChainResult",
    "EvidenceBuilder",
    "EvidencePackage",
    "EvidenceRecord",
    "CandidateValidator",
    "CandidateValidationResult",
    "ValidationDecision",
    "EvidenceRegistryClient",
    "AnchorResult",
    "VerificationResult",
]
