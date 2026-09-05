"""
Unit tests for backend/search module.
"""

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from backend.search import (
    SerpApiGoogleLensProvider,
    CandidateResult,
    ConfigurationError,
    ImageNotFoundError,
    APIResponseError,
)


class TestSearchModule(unittest.TestCase):

    def test_missing_api_key_raises_configuration_error(self):
        with patch.dict("os.environ", {}, clear=True):
            provider = SerpApiGoogleLensProvider(api_key=None)
            with self.assertRaises(ConfigurationError):
                provider.search("non_existent_file.jpg")

    def test_missing_local_file_raises_image_not_found_error(self):
        provider = SerpApiGoogleLensProvider(api_key="test_key")
        with self.assertRaises(ImageNotFoundError):
            provider.search("definitely_non_existent_file_98765.jpg")

    @patch("requests.get")
    @patch("requests.post")
    def test_successful_local_image_search_parsing(self, mock_post, mock_get):
        # Mock upload POST response
        mock_upload_resp = MagicMock()
        mock_upload_resp.status_code = 200
        mock_upload_resp.ok = True
        mock_upload_resp.json.return_value = {"image_id": "test_img_id_123"}
        mock_post.return_value = mock_upload_resp

        # Mock search GET response
        mock_search_resp = MagicMock()
        mock_search_resp.status_code = 200
        mock_search_resp.ok = True
        mock_search_resp.json.return_value = {
            "visual_matches": [
                {
                    "position": 1,
                    "title": "Match Title 1",
                    "link": "https://example.com/post1",
                    "source": "example.com",
                    "thumbnail": "https://example.com/thumb1.jpg",
                    "original": "https://example.com/img1.jpg",
                    "snippet": "Test snippet 1"
                }
            ]
        }
        mock_get.return_value = mock_search_resp

        # Create a dummy image file for testing
        test_img_path = Path("test_dummy.jpg")
        test_img_path.write_bytes(b"fake image data")

        try:
            provider = SerpApiGoogleLensProvider(api_key="valid_key")
            results = provider.search(test_img_path, max_results=5)

            self.assertEqual(len(results), 1)
            candidate = results[0]
            self.assertIsInstance(candidate, CandidateResult)
            self.assertEqual(candidate.url, "https://example.com/post1")
            self.assertEqual(candidate.image_url, "https://example.com/img1.jpg")
            self.assertEqual(candidate.title, "Match Title 1")
            self.assertEqual(candidate.source, "example.com")
            self.assertEqual(candidate.search_rank, 1)
            self.assertIsNotNone(candidate.candidate_id)

        finally:
            if test_img_path.exists():
                test_img_path.unlink()

    @patch("requests.get")
    def test_url_input_search(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {
            "visual_matches": [
                {
                    "position": 1,
                    "title": "URL Match Title",
                    "link": "https://instagram.com/p/12345",
                    "source": "Instagram",
                    "thumbnail": "https://instagram.com/thumb.jpg",
                    "snippet": "Insta post"
                }
            ]
        }
        mock_get.return_value = mock_response

        provider = SerpApiGoogleLensProvider(api_key="valid_key")
        results = provider.search("https://example.com/input.jpg")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].source, "Instagram")

    @patch("requests.post")
    def test_api_error_response_handling(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.ok = False
        mock_response.json.return_value = {"error": "Invalid engine specified"}
        mock_post.return_value = mock_response

        test_img_path = Path("test_err_dummy.jpg")
        test_img_path.write_bytes(b"fake image data")

        try:
            provider = SerpApiGoogleLensProvider(api_key="valid_key")
            with self.assertRaises(APIResponseError):
                provider.search(test_img_path)
        finally:
            if test_img_path.exists():
                test_img_path.unlink()


if __name__ == "__main__":
    unittest.main()
