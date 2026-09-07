"""Evidence snapshot creation with local storage and optional Pinata/IPFS pinning."""

from __future__ import annotations

import hashlib
import json
import os
import logging
from pathlib import Path
from typing import Optional

import requests
from pydantic import BaseModel

from backend.evidence import EvidencePackage

logger = logging.getLogger(__name__)


class ArchiveError(RuntimeError):
    pass


class ArchivePackage(BaseModel):
    uri: str
    manifest_path: str
    manifest_sha256: str
    image_sha256: str
    image_uri: str = ""


class EvidenceArchiver:
    """Persist a manifest and image, optionally pinning them to public IPFS."""

    def __init__(
        self,
        archive_dir: Optional[Path] = None,
        pinata_jwt: Optional[str] = None,
        gateway_url: Optional[str] = None,
    ):
        self.archive_dir = Path(archive_dir or os.getenv("ARCHIVE_DIR", "artifacts/archives"))
        self.pinata_jwt = pinata_jwt or os.getenv("PINATA_JWT", "")
        self.gateway_url = (gateway_url or os.getenv("IPFS_GATEWAY_URL", "https://gateway.pinata.cloud/ipfs")).rstrip("/")

    def archive(self, evidence: EvidencePackage) -> ArchivePackage:
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        archive_key = evidence.evidence_hash.removeprefix("0x")
        image_bytes: Optional[bytes]
        try:
            image_bytes = self._download_image(evidence.candidate_image_url)
        except ArchiveError as exc:
            logger.warning("Candidate image could not be archived: %s", exc)
            image_bytes = None
        image_sha256 = hashlib.sha256(image_bytes).hexdigest() if image_bytes else evidence.candidate_image_sha256
        if image_bytes and image_sha256 != evidence.candidate_image_sha256:
            raise ArchiveError("Archived image hash does not match validated candidate hash")

        image_path = self.archive_dir / f"{archive_key}.jpg"
        manifest_path = self.archive_dir / f"{archive_key}.json"
        if image_bytes:
            image_path.write_bytes(image_bytes)
        manifest = {
            "schema_version": "archive-1.0",
            "evidence": evidence.record.model_dump(),
            "canonical_json": evidence.canonical_json,
            "evidence_hash": evidence.evidence_hash,
            "candidate_id": evidence.candidate_id,
            "original_url": evidence.candidate_url,
            "image_sha256": image_sha256,
            "image_file": image_path.name if image_bytes else "",
            "image_url": evidence.candidate_image_url,
        }
        manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        manifest_path.write_bytes(manifest_bytes)

        if self.pinata_jwt:
            image_cid = self._pin_file(image_path, f"{archive_key}.jpg")
            manifest["image_uri"] = f"ipfs://{image_cid}"
            manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            manifest_path.write_bytes(manifest_bytes)
            manifest_cid = self._pin_json(manifest, f"facechain-{archive_key}.json")
            return ArchivePackage(
                uri=f"ipfs://{manifest_cid}",
                manifest_path=str(manifest_path.resolve()),
                manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
                image_sha256=image_sha256,
                image_uri=f"ipfs://{image_cid}",
            )

        return ArchivePackage(
            uri=f"file://{manifest_path.resolve()}",
            manifest_path=str(manifest_path.resolve()),
            manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
            image_sha256=image_sha256,
            image_uri=f"file://{image_path.resolve()}" if image_bytes else "",
        )

    def gateway_url_for(self, uri: str) -> str:
        if uri.startswith("ipfs://"):
            return f"{self.gateway_url}/{uri.removeprefix('ipfs://')}"
        return uri

    @staticmethod
    def _download_image(url: str) -> bytes:
        if not url:
            raise ArchiveError("Candidate image URL is missing; cannot create archive")
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (FaceChain evidence archiver)"},
            timeout=30,
        )
        response.raise_for_status()
        if not response.content:
            raise ArchiveError("Candidate image download returned no content")
        return response.content

    def _pin_file(self, path: Path, name: str) -> str:
        response = requests.post(
            "https://api.pinata.cloud/pinning/pinFileToIPFS",
            headers={"Authorization": f"Bearer {self.pinata_jwt}"},
            files={"file": (name, path.open("rb"), "image/jpeg")},
            data={"pinataOptions": json.dumps({"cidVersion": 1}), "pinataMetadata": json.dumps({"name": name})},
            timeout=60,
        )
        if response.status_code >= 400:
            raise ArchiveError(f"Pinata image upload failed ({response.status_code})")
        try:
            return str(response.json()["IpfsHash"])
        except (KeyError, ValueError) as exc:
            raise ArchiveError("Pinata image upload returned no IPFS hash") from exc

    def _pin_json(self, content: dict, name: str) -> str:
        response = requests.post(
            "https://api.pinata.cloud/pinning/pinJSONToIPFS",
            headers={"Authorization": f"Bearer {self.pinata_jwt}", "Content-Type": "application/json"},
            json={
                "pinataOptions": {"cidVersion": 1},
                "pinataMetadata": {"name": name},
                "pinataContent": content,
            },
            timeout=60,
        )
        if response.status_code >= 400:
            raise ArchiveError(f"Pinata manifest upload failed ({response.status_code})")
        try:
            return str(response.json()["IpfsHash"])
        except (KeyError, ValueError) as exc:
            raise ArchiveError("Pinata manifest upload returned no IPFS hash") from exc
