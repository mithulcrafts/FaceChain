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

from backend.pipeline import Person1Pipeline, Person1Result
from backend.face import FaceProcessor, FaceDetectionResult, NoFaceDetectedError
from backend.search import (
    SerpApiGoogleLensProvider,
    CandidateResult,
    ConfigurationError,
    SearchError,
)

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
logger = logging.getLogger("TestPipeline")


def run_mock_demo():
    """Demonstrate Person 1 pipeline using mock SerpApi response and face processing."""
    print("\n" + "=" * 60)
    print("RUNNING DEMO: [MOCK MODE] Input Image -> Face Processing -> SerpApi Search -> Candidates")
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

    import cv2
    import numpy as np

    # Create synthetic test image with face features
    img = np.ones((300, 300, 3), dtype=np.uint8) * 255
    cv2.circle(img, (150, 150), 60, (100, 100, 100), -1)
    cv2.circle(img, (130, 130), 10, (0, 0, 0), -1)
    cv2.circle(img, (170, 130), 10, (0, 0, 0), -1)
    cv2.ellipse(img, (150, 170), (20, 10), 0, 0, 180, (0, 0, 0), 3)

    sample_img = Path("sample_face_input.jpg")
    cv2.imwrite(str(sample_img), img)

    mock_face_result = FaceDetectionResult(
        bbox=[50.0, 50.0, 200.0, 200.0],
        det_score=0.98,
        embedding=[0.012, -0.045, 0.123] + [0.0] * 509,
        landmarks=[[70, 80], [130, 80], [100, 110], [80, 140], [120, 140]],
        aligned_face_shape=[112, 112, 3],
    )

    try:
        provider = SerpApiGoogleLensProvider(api_key="mock_key")
        pipeline = Person1Pipeline(search_provider=provider)

        with patch("requests.post") as mock_post, \
             patch("requests.get") as mock_get, \
             patch.object(pipeline.face_processor, "process_image", return_value=[mock_face_result]):

            mock_post.return_value = MagicMock(status_code=200, ok=True, json=lambda: {"image_id": "mock_id"})
            mock_get.return_value = MagicMock(status_code=200, ok=True, json=lambda: mock_serpapi_response)

            result = pipeline.run(image_path=sample_img, results_per_search=30, max_candidates=50)
    finally:
        if sample_img.exists():
            sample_img.unlink()

    print("\n--- STEP 1: FACE PROCESSING COMPLETE ---")
    print(f"Faces Detected:         {result.detected_faces_count}")
    print(f"Primary Face Score:     {result.primary_face.det_score:.2f}")
    print(f"Face Bounding Box:      {result.primary_face.bbox}")
    print(f"ArcFace Embedding Dim:  {len(result.primary_face.embedding)} dimensions")
    print(f"Embedding Vector (1st 5): {result.primary_face.embedding[:5]}")

    print("\n--- STEP 2: DUAL WEB SEARCH (FULL IMAGE + FACE CROP) COMPLETE ---")
    print(f"Extracted {len(result.candidates)} merged CandidateResult objects:")
    for res in result.candidates:
        print(f"\n[Rank {res.search_rank}] UUID: {res.candidate_id}")
        print(f"  URL:              {res.url}")
        print(f"  Image URL:        {res.image_url}")
        print(f"  Title:            {res.title}")
        print(f"  Source:           {res.source}")
        print(f"  Discovery Method: {res.discovery_method}")

    assert len(result.candidates) == 2
    assert len(result.primary_face.embedding) == 512
    print("\n[OK] PERSON 1 PIPELINE DEMO PASSED: Dual-Search (Full Image + Face Crop) integrated successfully.")


def run_live_demo(image_path: str):
    """Execute Person 1 End-to-End Dual Search Pipeline (Face Processing + Live SerpApi Search)."""
    print("\n" + "=" * 60)
    print(f"RUNNING DEMO: [LIVE MODE] Person 1 Dual Search Pipeline ({image_path})")
    print("=" * 60)

    try:
        pipeline = Person1Pipeline()
        result = pipeline.run(image_path=image_path, results_per_search=30, max_candidates=50)

        print("\n--- STEP 1: FACE PROCESSING COMPLETE ---")
        print(f"Faces Detected:         {result.detected_faces_count}")
        print(f"Primary Face Score:     {result.primary_face.det_score:.2f}")
        print(f"Face Bounding Box:      {result.primary_face.bbox}")
        print(f"ArcFace Embedding Dim:  {len(result.primary_face.embedding)} dimensions")

        print("\n--- STEP 2: DUAL WEB SEARCH (FULL IMAGE + FACE CROP) COMPLETE ---")
        if not result.candidates:
            print("No matching web results found for the input image.")
            return

        print(f"Retrieved {len(result.candidates)} merged candidate results (max cap: 50):")
        for res in result.candidates:
            print(f"\n[Rank {res.search_rank}] Candidate ID: {res.candidate_id}")
            print(f"  URL:              {res.url}")
            print(f"  Image URL:        {res.image_url}")
            print(f"  Title:            {res.title}")
            print(f"  Source:           {res.source}")
            print(f"  Discovery Method: {res.discovery_method}")
            print(f"  Snippet:          {res.snippet}")

    except NoFaceDetectedError as err:
        logger.error(f"Face Processing Error: {err}")
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
