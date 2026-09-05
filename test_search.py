"""
Demonstration and integration test for Web / Reverse Image Search Module (Phase 1).

Usage:
  1. Set your SerpApi key:
     export SERPAPI_API_KEY="your_api_key_here"  (Linux/macOS)
     $env:SERPAPI_API_KEY="your_api_key_here"      (PowerShell)

  2. Run with a sample local image or remote URL:
     python test_search.py path/to/sample_face.jpg

  3. Run offline mock test mode:
     python test_search.py --mock
"""

import sys
import os
import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure root workspace directory is in sys.path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from backend.search import (
    SerpApiGoogleLensProvider,
    CandidateResult,
    ConfigurationError,
    SearchError,
)

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
logger = logging.getLogger("TestSearch")


def run_mock_demo():
    """Demonstrate pipeline parsing and CandidateResult normalization using mock SerpApi response."""
    print("\n" + "=" * 60)
    print("RUNNING DEMO: [MOCK MODE] input image -> SerpApi Google Lens -> candidate results")
    print("=" * 60)

    mock_serpapi_response = {
        "visual_matches": [
            {
                "position": 1,
                "title": "Jane Doe - Official Speaker Profile at Tech Summit 2026",
                "link": "https://techsummit2026.com/speakers/jane-doe",
                "source": "TechSummit",
                "thumbnail": "https://techsummit2026.com/images/speakers/jane-doe-thumb.jpg",
                "original": "https://techsummit2026.com/images/speakers/jane-doe.jpg",
                "snippet": "Keynote Speaker on Artificial Intelligence & Ethics."
            },
            {
                "position": 2,
                "title": "Jane Doe (@janedoe_tech) / Twitter",
                "link": "https://twitter.com/janedoe_tech/status/1892304958",
                "source": "Twitter",
                "thumbnail": "https://pbs.twimg.com/profile_images/janedoe.jpg",
                "original": "https://pbs.twimg.com/media/janedoe_post.jpg",
                "snippet": "Building future web3 and AI verification tools #Goa2026"
            }
        ]
    }

    provider = SerpApiGoogleLensProvider(api_key="mock_key")

    # Create temporary dummy file for mock test
    sample_img = Path("sample_input.jpg")
    sample_img.write_bytes(b"dummy_image_content")

    try:
        with patch("requests.post") as mock_post, patch("requests.get") as mock_get:
            # Mock image upload response
            upload_response = MagicMock()
            upload_response.status_code = 200
            upload_response.ok = True
            upload_response.json.return_value = {"image_id": "mock_image_id_123"}
            mock_post.return_value = upload_response

            # Mock search response
            search_response = MagicMock()
            search_response.status_code = 200
            search_response.ok = True
            search_response.json.return_value = mock_serpapi_response
            mock_get.return_value = search_response

            # Execute search
            results = provider.search(image_input=sample_img, max_results=5)
    finally:
        if sample_img.exists():
            sample_img.unlink()

    print(f"\nSuccessfully extracted {len(results)} CandidateResult objects:")
    for res in results:
        print(f"\n[Rank {res.search_rank}] UUID: {res.candidate_id}")
        print(f"  URL:         {res.url}")
        print(f"  Image URL:   {res.image_url}")
        print(f"  Title:       {res.title}")
        print(f"  Snippet:     {res.snippet}")
        print(f"  Source:      {res.source}")

    # Validate output format
    assert len(results) == 2
    assert isinstance(results[0], CandidateResult)
    assert results[0].source == "TechSummit"
    assert results[1].source == "Twitter"
    print("\n[OK] MOCK DEMO PASSED: CandidateResult objects conform exactly to component data contract.")


def run_live_demo(image_path: str):
    """Execute live reverse image search via SerpApi API."""
    print("\n" + "=" * 60)
    print(f"RUNNING DEMO: [LIVE MODE] input image ({image_path}) -> SerpApi Google Lens -> candidate results")
    print("=" * 60)

    try:
        provider = SerpApiGoogleLensProvider()
        results = provider.search(image_input=image_path, max_results=10)

        if not results:
            print("No matching web results found for the input image.")
            return

        print(f"\nRetrieved {len(results)} live candidate results from SerpApi Google Lens:")
        for res in results:
            print(f"\n[Rank {res.search_rank}] ID: {res.candidate_id}")
            print(f"  URL:       {res.url}")
            print(f"  Image URL: {res.image_url}")
            print(f"  Title:     {res.title}")
            print(f"  Source:    {res.source}")
            print(f"  Snippet:   {res.snippet}")

    except ConfigurationError as err:
        logger.error(f"Configuration Error: {err}")
        print("\nTip: Set SERPAPI_API_KEY environment variable to test live API calls.")
        print("Falling back to mock mode verification...")
        run_mock_demo()
    except SearchError as err:
        logger.error(f"Search Execution Failed: {err}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--mock":
        run_mock_demo()
    elif len(sys.argv) > 1:
        run_live_demo(sys.argv[1])
    else:
        # Check if SERPAPI_API_KEY is available
        if os.getenv("SERPAPI_API_KEY"):
            print("SERPAPI_API_KEY detected. Provide an image path to test live search:")
            print("  python test_search.py <path_to_image>")
            print("\nRunning mock mode test by default...")
        run_mock_demo()
