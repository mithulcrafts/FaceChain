"""
SerpApi Google Lens reverse-image search implementation.
Provides genuine reverse-image lookup using SerpApi's Google Lens engine.
"""

import io
import os
import uuid
import logging
from pathlib import Path
from typing import List, Union, Optional, Dict, Any
from urllib.parse import urlparse
import requests

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from backend.search.base import BaseSearchProvider
from backend.search.models import CandidateResult
from backend.search.exceptions import (
    SearchError,
    ConfigurationError,
    APIResponseError,
    ImageNotFoundError,
)

logger = logging.getLogger(__name__)


class SerpApiGoogleLensProvider(BaseSearchProvider):
    """
    Genuine reverse-image search provider using SerpApi Google Lens engine.
    """

    SERPAPI_ENDPOINT = "https://serpapi.com/search.json"
    SERPAPI_IMAGE_UPLOAD_ENDPOINT = "https://serpapi.com/image"
    MAX_UPLOAD_BYTES = 500 * 1024  # 500 KB limit for SerpApi /image endpoint

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the SerpApi Google Lens search provider.

        :param api_key: Optional SerpApi API key. If not provided, reads from SERPAPI_API_KEY environment variable.
        """
        self.api_key = api_key or os.getenv("SERPAPI_API_KEY")

    def _prepare_image_payload(self, image_path: Path) -> tuple[bytes, str]:
        """
        Prepare image bytes for upload. Automatically resizes/compresses images exceeding 500 KB limit.
        """
        file_size = image_path.stat().st_size
        ext = image_path.suffix.lower()
        default_mime = "image/png" if ext == ".png" else "image/jpeg"

        if file_size <= self.MAX_UPLOAD_BYTES or not HAS_PIL:
            if file_size > self.MAX_UPLOAD_BYTES and not HAS_PIL:
                logger.warning(
                    f"Image size ({file_size / 1024:.1f} KB) exceeds 500 KB limit and Pillow is not installed."
                )
            return image_path.read_bytes(), default_mime

        logger.info(
            f"Image size ({file_size / 1024:.1f} KB) exceeds SerpApi 500 KB limit. "
            "Automatically compressing image in memory..."
        )

        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")

            max_dim = 1024
            if max(img.width, img.height) > max_dim:
                img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

            quality = 85
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=quality, optimize=True)

            while buffer.tell() > self.MAX_UPLOAD_BYTES and quality > 30:
                buffer = io.BytesIO()
                quality -= 10
                img.save(buffer, format="JPEG", quality=quality, optimize=True)

            compressed_bytes = buffer.getvalue()
            logger.info(f"Compressed image size: {len(compressed_bytes) / 1024:.1f} KB (JPEG quality {quality}).")
            return compressed_bytes, "image/jpeg"

    def _upload_local_image(self, image_path: Path) -> str:
        """
        Upload a local image file to SerpApi image endpoint to obtain an image_id.

        :param image_path: Path object pointing to local image file.
        :return: image_id string returned by SerpApi.
        """
        logger.info(f"Uploading local image file ({image_path.name}) to SerpApi image endpoint...")
        upload_params = {"api_key": self.api_key}

        image_bytes, mime_type = self._prepare_image_payload(image_path)
        upload_filename = image_path.name if mime_type != "image/jpeg" else f"{image_path.stem}.jpg"

        files = {"image": (upload_filename, image_bytes, mime_type)}
        response = requests.post(
            self.SERPAPI_IMAGE_UPLOAD_ENDPOINT,
            params=upload_params,
            files=files,
            timeout=30
        )

        if response.status_code in (401, 403):
            raise ConfigurationError(f"SerpApi Image Upload Authentication failed (HTTP {response.status_code}): {response.text}")

        try:
            data = response.json()
        except Exception as exc:
            raise APIResponseError(f"Failed to parse JSON response from SerpApi Image Upload (HTTP {response.status_code}): {response.text}") from exc

        if not response.ok or "error" in data:
            error_msg = data.get("error", f"HTTP {response.status_code} Error")
            raise APIResponseError(f"SerpApi Image Upload failed: {error_msg}")

        image_id = data.get("image_id") or data.get("id")
        if not image_id:
            raise APIResponseError(f"SerpApi Image Upload response missing 'image_id': {data}")

        logger.info(f"Successfully uploaded image. Received image_id: {image_id}")
        return str(image_id)

    def search(
        self, 
        image_input: Union[str, Path], 
        max_results: int = 10
    ) -> List[CandidateResult]:
        """
        Perform a genuine reverse image search via SerpApi Google Lens.

        :param image_input: Local file path or remote HTTP(S) URL of the image to search.
        :param max_results: Maximum number of candidate results to return (default 10).
        :return: List of normalized CandidateResult objects.
        :raises ConfigurationError: If SerpApi API key is not configured.
        :raises ImageNotFoundError: If local image file does not exist.
        :raises APIResponseError: If SerpApi returns an HTTP or payload error.
        :raises SearchError: On general network or search execution failures.
        """
        if not self.api_key:
            raise ConfigurationError(
                "SERPAPI_API_KEY is not set. Please set the SERPAPI_API_KEY environment variable "
                "or pass api_key to SerpApiGoogleLensProvider constructor."
            )

        image_str = str(image_input).strip()
        is_url = image_str.startswith("http://") or image_str.startswith("https://")

        params: Dict[str, Any] = {
            "engine": "google_lens",
            "api_key": self.api_key,
        }

        try:
            if is_url:
                logger.info(f"Initiating SerpApi Google Lens search for URL: {image_str}")
                params["url"] = image_str
            else:
                image_path = Path(image_str)
                if not image_path.is_file():
                    raise ImageNotFoundError(f"Input image file not found at path: {image_path.resolve()}")

                # Step 1: Upload local image to obtain image_id
                image_id = self._upload_local_image(image_path)
                params["image_id"] = image_id

            # Step 2: Execute search using engine=google_lens and image_id / url
            logger.info("Executing Google Lens search query via SerpApi...")
            response = requests.get(self.SERPAPI_ENDPOINT, params=params, timeout=30)

        except requests.RequestException as exc:
            raise SearchError(f"Network error during SerpApi search request: {exc}") from exc

        return self._parse_response(response, max_results)

    def _parse_response(self, response: requests.Response, max_results: int) -> List[CandidateResult]:
        """
        Parse SerpApi HTTP response and extract normalized CandidateResult objects.
        """
        if response.status_code == 401 or response.status_code == 403:
            raise ConfigurationError(f"SerpApi Authentication failed (HTTP {response.status_code}): {response.text}")
        
        try:
            data = response.json()
        except Exception as exc:
            raise APIResponseError(f"Failed to parse JSON response from SerpApi (HTTP {response.status_code}): {response.text}") from exc

        if not response.ok:
            error_msg = data.get("error", f"HTTP {response.status_code} Error")
            raise APIResponseError(f"SerpApi returned error: {error_msg}")

        if "error" in data:
            raise APIResponseError(f"SerpApi error: {data['error']}")

        # Extract visual matches from SerpApi payload
        matches = data.get("visual_matches", [])
        if not matches and "organic_results" in data:
            matches = data.get("organic_results", [])

        if not matches:
            logger.warning("SerpApi returned no visual matches for the input image.")
            return []

        candidates: List[CandidateResult] = []
        rank = 1

        for match in matches:
            if rank > max_results:
                break

            target_url = (
                match.get("link")
                or match.get("source_web_page")
                or match.get("url")
                or ""
            ).strip()

            image_url = (
                match.get("original")
                or match.get("thumbnail")
                or match.get("image")
                or match.get("source_icon")
                or ""
            ).strip()

            # Skip entries that have neither web page URL nor image URL
            if not target_url and not image_url:
                continue

            title = (match.get("title") or "").strip()
            snippet = (
                match.get("snippet")
                or match.get("subtitle")
                or match.get("description")
                or ""
            ).strip()

            # Determine source domain
            source = (match.get("source") or "").strip()
            if not source and target_url:
                try:
                    parsed_domain = urlparse(target_url).netloc
                    source = parsed_domain.replace("www.", "")
                except Exception:
                    source = "web"

            candidate = CandidateResult(
                candidate_id=str(uuid.uuid4()),
                url=target_url,
                image_url=image_url,
                title=title,
                snippet=snippet,
                source=source,
                search_rank=rank,
                metadata={
                    key: match.get(key)
                    for key in (
                        "position",
                        "link",
                        "url",
                        "source_web_page",
                        "source",
                        "title",
                        "snippet",
                        "subtitle",
                        "description",
                        "original",
                        "thumbnail",
                        "image",
                        "source_icon",
                        "author",
                        "timestamp",
                        "published_date",
                        "date",
                    )
                    if match.get(key) is not None
                },
            )
            candidates.append(candidate)
            rank += 1

        logger.info(f"Extracted {len(candidates)} candidate results from SerpApi.")
        return candidates
