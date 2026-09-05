"""
Custom exceptions for face processing module.
"""

class FaceProcessingError(Exception):
    """Base exception for face processing errors."""
    pass

class NoFaceDetectedError(FaceProcessingError):
    """Raised when no face is detected in the input image."""
    pass

class InvalidImageError(FaceProcessingError):
    """Raised when the input image cannot be read or is invalid."""
    pass
