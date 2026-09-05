"""
Data models for face detection, alignment, and embedding extraction.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class FaceDetectionResult(BaseModel):
    """
    Result structure representing a detected, aligned face and its ArcFace embedding.
    """
    bbox: List[float] = Field(description="Bounding box coordinates [x1, y1, x2, y2]")
    det_score: float = Field(description="Face detection confidence score (0.0 - 1.0)")
    embedding: List[float] = Field(description="512-dimensional face embedding vector")
    landmarks: Optional[List[List[float]]] = Field(
        default=None, 
        description="5 facial keypoints/landmarks [[x, y], ...]"
    )
    aligned_face_shape: Optional[List[int]] = Field(
        default=None, 
        description="Dimensions [H, W, C] of aligned face crop"
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert FaceDetectionResult to dictionary."""
        return self.model_dump()
