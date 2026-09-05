"""
Abstract base search provider interface.
Allows swapping SerpApi with alternative search providers in the future.
"""

from abc import ABC, abstractmethod
from typing import List, Union
from pathlib import Path
from backend.search.models import CandidateResult


class BaseSearchProvider(ABC):
    """
    Abstract Interface for Reverse Image Search Providers.
    All search provider implementations must inherit from this class.
    """

    @abstractmethod
    def search(
        self, 
        image_input: Union[str, Path], 
        max_results: int = 10
    ) -> List[CandidateResult]:
        """
        Execute reverse-image search for a given image (local file path or URL).

        :param image_input: Local file path or HTTP URL of the image to search.
        :param max_results: Maximum number of normalized CandidateResult objects to return.
        :return: List of normalized CandidateResult instances.
        """
        pass
