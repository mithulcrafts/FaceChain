"""
Face processing module.
Provides face detection, alignment, and ArcFace embedding extraction.
"""

from backend.face.models import FaceDetectionResult
from backend.face.processor import FaceProcessor
from backend.face.exceptions import (
    FaceProcessingError,
    NoFaceDetectedError,
    InvalidImageError,
)

__all__ = [
    "FaceDetectionResult",
    "FaceProcessor",
    "FaceProcessingError",
    "NoFaceDetectedError",
    "InvalidImageError",
]
