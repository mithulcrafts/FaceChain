"""
Evidence package builder.

Builds deterministic evidence JSON, computes SHA-256 fingerprint, and keeps
field ordering aligned with Solidity canonicalization.
"""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from backend.search.models import CandidateResult


def _normalize_source(source: str, url: str = "") -> str:
    if source:
        return source.strip().lower().replace("www.", "")
    if not url:
        return ""
    parsed = urlparse(url)
    return parsed.netloc.lower().replace("www.", "")


def _pick_first(metadata: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = metadata.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


class EvidenceRecord(BaseModel):
    schema_version: str = Field(default="1.0")
    source: str = Field(default="")
    source_url: str = Field(default="")
    title: str = Field(default="")
    caption: str = Field(default="")
    author: str = Field(default="")
    timestamp: str = Field(default="")
    image_sha256: str = Field(default="")

    def canonical_dict(self) -> "OrderedDict[str, str]":
        return OrderedDict(
            [
                ("schema_version", self.schema_version),
                ("source", self.source),
                ("source_url", self.source_url),
                ("title", self.title),
                ("caption", self.caption),
                ("author", self.author),
                ("timestamp", self.timestamp),
                ("image_sha256", self.image_sha256),
            ]
        )

    def canonical_bytes(self) -> bytes:
        return json.dumps(self.canonical_dict(), separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    def evidence_hash(self) -> bytes:
        return hashlib.sha256(self.canonical_bytes()).digest()

    def evidence_hash_hex(self) -> str:
        return "0x" + hashlib.sha256(self.canonical_bytes()).hexdigest()


class EvidencePackage(BaseModel):
    record: EvidenceRecord
    canonical_json: str
    evidence_hash: str
    candidate_id: str
    candidate_url: str
    candidate_source: str
    candidate_image_sha256: str
    candidate_image_url: str = ""
    archive_uri: Optional[str] = None


class EvidenceBuilder:
    """
    Build deterministic evidence from accepted search candidate.
    """

    def __init__(self, schema_version: str = "1.0"):
        self.schema_version = schema_version

    def build(
        self,
        candidate: CandidateResult,
        candidate_image_sha256: str,
        source_url: Optional[str] = None,
    ) -> EvidencePackage:
        metadata = candidate.metadata or {}
        record = EvidenceRecord(
            schema_version=self.schema_version,
            source=_normalize_source(candidate.source, candidate.url),
            source_url=(source_url or candidate.url or "").strip(),
            title=(candidate.title or "").strip(),
            caption=(candidate.snippet or "").strip(),
            author=_pick_first(metadata, ("author", "creator", "username", "handle", "owner")),
            timestamp=_pick_first(metadata, ("timestamp", "published_date", "date", "datetime", "posted_at")),
            image_sha256=candidate_image_sha256.lower().strip(),
        )

        canonical_json = record.canonical_bytes().decode("utf-8")
        evidence_hash = record.evidence_hash_hex()

        return EvidencePackage(
            record=record,
            canonical_json=canonical_json,
            evidence_hash=evidence_hash,
            candidate_id=candidate.candidate_id,
            candidate_url=candidate.url,
            candidate_source=record.source,
            candidate_image_sha256=candidate_image_sha256.lower().strip(),
            candidate_image_url=candidate.image_url or "",
        )

    @staticmethod
    def from_image_hash(
        candidate: CandidateResult,
        candidate_image_sha256: str,
        schema_version: str = "1.0",
        source_url: Optional[str] = None,
    ) -> EvidencePackage:
        return EvidenceBuilder(schema_version=schema_version).build(
            candidate=candidate,
            candidate_image_sha256=candidate_image_sha256,
            source_url=source_url,
        )
