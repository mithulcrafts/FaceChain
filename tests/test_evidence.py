"""
Unit tests for evidence canonicalization.
"""

import hashlib
import json
import unittest

from backend.evidence import EvidenceBuilder
from backend.search.models import CandidateResult


class TestEvidenceBuilder(unittest.TestCase):
    def test_build_creates_canonical_hash(self):
        candidate = CandidateResult(
            candidate_id="candidate-1",
            url="https://www.Example.com/post/1",
            image_url="https://example.com/image.jpg",
            title="Found Post",
            snippet="Matched caption",
            source="Example.com",
            metadata={
                "author": "Alice",
                "timestamp": "2026-09-06T12:00:00Z",
            },
        )

        package = EvidenceBuilder(schema_version="1.0").build(
            candidate=candidate,
            candidate_image_sha256="A1B2C3",
            source_url="https://example.com/post/1",
        )

        expected = {
            "schema_version": "1.0",
            "source": "example.com",
            "source_url": "https://example.com/post/1",
            "title": "Found Post",
            "caption": "Matched caption",
            "author": "Alice",
            "timestamp": "2026-09-06T12:00:00Z",
            "image_sha256": "a1b2c3",
        }

        self.assertEqual(package.record.canonical_dict(), expected)
        self.assertEqual(
            package.canonical_json,
            json.dumps(expected, separators=(",", ":"), ensure_ascii=False),
        )
        self.assertEqual(
            package.evidence_hash,
            "0x" + hashlib.sha256(package.canonical_json.encode("utf-8")).hexdigest(),
        )

