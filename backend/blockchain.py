"""
Blockchain client for EvidenceRegistry.

Uses Foundry `cast` so the repo stays dependency-light.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


class BlockchainError(RuntimeError):
    pass


def _strip_0x(value: str) -> str:
    value = value.strip()
    return value[2:] if value.startswith("0x") else value


def _parse_bool(text: str) -> bool:
    stripped = text.strip().lower()
    if stripped in ("true", "1"):
        return True
    if stripped in ("false", "0"):
        return False
    raise BlockchainError(f"Could not parse bool from cast output: {text}")


def _parse_json_or_text(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        return ""
    try:
        return json.loads(stripped)
    except Exception:
        return stripped


def _parse_tuple(text: str) -> Tuple[str, ...]:
    stripped = text.strip()
    if not stripped:
        return tuple()

    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if len(lines) > 1:
        values: List[str] = []
        for line in lines:
            line = line.strip().rstrip(",")
            if line.startswith("(") and line.endswith(")"):
                line = line[1:-1].strip()
            if " [" in line:
                line = line.split(" [", 1)[0].strip()
            values.append(line.strip().strip('"'))
        return tuple(values)

    single = lines[0]
    if single.startswith("(") and single.endswith(")"):
        single = single[1:-1]
    reader = csv.reader([single], delimiter=",", quotechar='"', skipinitialspace=True)
    return tuple(next(reader))


def _receipt_succeeded(output: str) -> bool:
    """Return the EVM receipt status from human-readable cast output."""
    match = re.search(r"(?im)^\s*status\s+(0x[0-9a-f]+|[01]|success|failed)\b", output)
    if not match:
        raise BlockchainError(f"Could not find transaction status in cast receipt: {output}")

    status = match.group(1).lower()
    return status in {"1", "0x1", "success"}


def _run_cast(
    args: List[str],
    *,
    rpc_url: str,
    chain_id: int,
    private_key: Optional[str] = None,
    include_chain: bool = True,
) -> str:
    # Gracefully locate cast even if PATH hasn't refreshed
    cast_path = shutil.which("cast")
    if not cast_path:
        fallback_win = Path.home() / ".foundry" / "bin" / "cast.exe"
        fallback_nix = Path.home() / ".foundry" / "bin" / "cast"
        if fallback_win.exists():
            cast_path = str(fallback_win)
        elif fallback_nix.exists():
            cast_path = str(fallback_nix)
        else:
            cast_path = "cast"  # default to 'cast' to let standard error bubble up

    cmd = [cast_path, *args, "--rpc-url", rpc_url]
    if include_chain:
        cmd.extend(["--chain", str(chain_id)])
    if private_key:
        cmd.extend(["--private-key", private_key])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise BlockchainError(
            "cast command failed: "
            + (result.stderr.strip() or result.stdout.strip() or "unknown error")
        )
    return result.stdout.strip()


@dataclass
class AnchorResult:
    evidence_hash: str
    transaction_hash: str
    stored_timestamp: int
    stored_source: str
    stored_source_url: str = ""
    stored_archive_uri: str = ""


@dataclass
class VerificationResult:
    evidence_hash: str
    anchored: bool
    exists: bool
    submitter: str
    timestamp: int
    source_matches: bool
    hash_matches: bool
    source_url: str = ""
    archive_uri: str = ""
    archive_matches: bool = False


class EvidenceRegistryClient:
    """
    Thin client around EvidenceRegistry contract.
    """

    def __init__(
        self,
        registry_address: Optional[str] = None,
        rpc_url: Optional[str] = None,
        private_key: Optional[str] = None,
        chain_id: Optional[int] = None,
    ):
        self.registry_address = registry_address or os.getenv("EVIDENCE_REGISTRY", "")
        self.rpc_url = rpc_url or os.getenv("BASE_SEPOLIA_RPC_URL", "")
        self.private_key = private_key or os.getenv("PRIVATE_KEY", "")
        self.chain_id = int(chain_id or os.getenv("CHAIN_ID", "84532"))

        if not self.registry_address:
            raise BlockchainError("EVIDENCE_REGISTRY is not set")
        if not self.rpc_url:
            raise BlockchainError("BASE_SEPOLIA_RPC_URL is not set")

    def anchor_evidence(
        self,
        evidence_hash: str,
        source: str,
        source_url: str = "",
        archive_uri: str = "",
    ) -> AnchorResult:
        if not self.private_key:
            raise BlockchainError("PRIVATE_KEY is not set")
        tx_hash = ""
        try:
            tx_hash = _run_cast(
                [
                    "send",
                    self.registry_address,
                    "anchorEvidenceWithArchive(bytes32,string,string,string)(uint64)",
                    evidence_hash,
                    source,
                    source_url,
                    archive_uri,
                    "--async",
                ],
                rpc_url=self.rpc_url,
                chain_id=self.chain_id,
                private_key=self.private_key,
            )
            if not re.fullmatch(r"0x[a-fA-F0-9]{64}", tx_hash.strip()):
                match = re.search(r"0x[a-fA-F0-9]{64}", tx_hash)
                if not match:
                    raise BlockchainError(f"Could not parse transaction hash from cast send output: {tx_hash}")
                tx_hash = match.group(0)

            receipt = _run_cast(
                ["receipt", tx_hash],
                rpc_url=self.rpc_url,
                chain_id=self.chain_id,
                include_chain=False,
            )
            if not _receipt_succeeded(receipt):
                raise BlockchainError(f"Anchor transaction reverted: {tx_hash}")
        except BlockchainError as exc:
            if "EvidenceAlreadyAnchored" not in str(exc) and "0xd643e710" not in str(exc):
                raise
            logger.info("Evidence already anchored on-chain; reusing existing record.")

        # Some RPC providers expose the receipt before their read path catches up.
        # Retry briefly, while keeping the final result strictly read-back verified.
        exists = False
        submitter = ""
        timestamp = 0
        stored_source = ""
        stored_source_url = ""
        stored_archive_uri = ""
        for attempt in range(5):
            (
                exists,
                submitter,
                timestamp,
                stored_source,
                stored_source_url,
                stored_archive_uri,
            ) = self.get_evidence_with_archive(evidence_hash)
            if exists:
                break
            if attempt < 4:
                time.sleep(1)
        if not exists:
            raise BlockchainError(
                f"Anchor transaction mined but evidence missing from registry: {evidence_hash}"
            )

        return AnchorResult(
            evidence_hash=evidence_hash,
            transaction_hash=tx_hash or "already_anchored",
            stored_timestamp=timestamp,
            stored_source=stored_source,
            stored_source_url=stored_source_url,
            stored_archive_uri=stored_archive_uri,
        )

    def verify_evidence(
        self, 
        evidence_hash: str, 
        expected_source: Optional[str] = None,
        expected_source_url: Optional[str] = None
    ) -> VerificationResult:
        anchored = self.verify_anchor(evidence_hash)
        exists, submitter, timestamp, source, source_url, archive_uri = self.get_evidence_with_archive(evidence_hash)
        
        source_matches = True
        if expected_source is not None and source != expected_source:
            source_matches = False
        if expected_source_url is not None and source_url != expected_source_url:
            source_matches = False

        return VerificationResult(
            evidence_hash=evidence_hash,
            anchored=anchored,
            exists=exists,
            submitter=submitter,
            timestamp=timestamp,
            source_matches=source_matches,
            hash_matches=anchored and exists,
            source_url=source_url,
            archive_uri=archive_uri,
            archive_matches=bool(archive_uri),
        )

    def verify_anchor(self, evidence_hash: str) -> bool:
        output = _run_cast(
            [
                "call",
                self.registry_address,
                "verifyEvidence(bytes32)(bool)",
                evidence_hash,
            ],
            rpc_url=self.rpc_url,
            chain_id=self.chain_id,
        )
        return _parse_bool(output)

    def get_evidence(self, evidence_hash: str) -> Tuple[bool, str, int, str]:
        output = _run_cast(
            [
                "call",
                self.registry_address,
                "getEvidence(bytes32)(bool,address,uint64,string)",
                evidence_hash,
            ],
            rpc_url=self.rpc_url,
            chain_id=self.chain_id,
        )

        parsed = _parse_json_or_text(output)
        if isinstance(parsed, list) and len(parsed) == 4:
            exists, submitter, timestamp, source_url = parsed
        elif isinstance(parsed, str):
            parts = _parse_tuple(parsed)
            if len(parts) != 4:
                raise BlockchainError(f"Could not parse registry tuple: {output}")
            exists, submitter, timestamp, source_url = parts
        else:
            raise BlockchainError(f"Unexpected registry output: {output}")

        return (
            _parse_bool(str(exists)),
            str(submitter),
            int(str(timestamp), 0),
            str(source_url).strip('"'),
        )

    def get_evidence_with_archive(self, evidence_hash: str) -> Tuple[bool, str, int, str, str, str]:
        output = _run_cast(
            [
                "call",
                self.registry_address,
                "getEvidenceWithArchive(bytes32)(bool,address,uint64,string,string,string)",
                evidence_hash,
            ],
            rpc_url=self.rpc_url,
            chain_id=self.chain_id,
        )
        parts = _parse_tuple(output)
        if len(parts) == 4:
            exists, submitter, timestamp, source = parts
            return (
                _parse_bool(str(exists)),
                str(submitter),
                int(str(timestamp), 0),
                str(source).strip('"'),
                "",
                "",
            )
        if len(parts) != 6:
            raise BlockchainError(f"Could not parse registry archive tuple: {output}")
        exists, submitter, timestamp, source, source_url, archive_uri = parts
        return (
            _parse_bool(str(exists)),
            str(submitter),
            int(str(timestamp), 0),
            str(source).strip('"'),
            str(source_url).strip('"'),
            str(archive_uri).strip('"'),
        )
