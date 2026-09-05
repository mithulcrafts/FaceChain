"""
Data models for the web/reverse-image-search module.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class CandidateResult(BaseModel):
    """
    Standardized result structure for a reverse-image search candidate.
    Agreed contract across all pipeline components.
    """
    candidate_id: str = Field(description="Unique UUID for candidate result")
    url: str = Field(description="Source post / web page URL")
    image_url: str = Field(description="Matched image URL on the source page")
    title: str = Field(default="", description="Title of the web page or post")
    snippet: str = Field(default="", description="Text snippet or caption from the post")
    source: str = Field(default="", description="Source domain or platform (e.g. twitter.com)")
    search_rank: int = Field(default=1, description="Rank position in search results (1-indexed)")

    def to_dict(self) -> Dict[str, Any]:
        """Convert CandidateResult to dictionary format."""
        return self.model_dump()
