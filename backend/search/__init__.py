"""
Web / Reverse Image Search Module.
Exposes search providers, models, and convenience search helpers.
"""

from backend.search.models import CandidateResult
from backend.search.base import BaseSearchProvider
from backend.search.serpapi_lens import SerpApiGoogleLensProvider
from backend.search.exceptions import (
    SearchError,
    ConfigurationError,
    APIResponseError,
    ImageNotFoundError,
)

__all__ = [
    "CandidateResult",
    "BaseSearchProvider",
    "SerpApiGoogleLensProvider",
    "SearchError",
    "ConfigurationError",
    "APIResponseError",
    "ImageNotFoundError",
]
