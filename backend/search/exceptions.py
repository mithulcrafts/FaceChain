"""
Custom exceptions for the search module.
"""

class SearchError(Exception):
    """Base exception for search provider errors."""
    pass

class ConfigurationError(SearchError):
    """Raised when required configuration (e.g., API key) is missing."""
    pass

class APIResponseError(SearchError):
    """Raised when the search API returns an error response."""
    pass

class ImageNotFoundError(SearchError):
    """Raised when the provided input image file does not exist."""
    pass
