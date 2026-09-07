"""
verify.py — Tamper Detection Script for FaceChain

This script checks whether a piece of evidence that was previously anchored
on the blockchain has been tampered with since it was originally verified.

How it works:
  1. Reads the original evidence hash from the Base Sepolia blockchain.
  2. Goes back to the live web URL and re-downloads the current image.
  3. Rebuilds the evidence record from the current live data.
  4. Re-hashes it using the same deterministic SHA-256 canonicalization.
  5. Compares the NEW hash to the ORIGINAL hash stored on-chain.

     - If they match   → The evidence is pristine (untampered).
     - If they differ  → The source content has been altered.

Usage:
  python verify.py --evidence-hash 0xabc123... --source-url https://example.com/post
  python verify.py --evidence-hash 0xabc123... --source-url https://example.com/post --image-url https://example.com/photo.jpg
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlparse

import requests

# ─── Rich terminal output (optional, falls back to plain print) ──────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# ─── Import the project's own modules ───────────────────────────────────────
try:
    from backend.blockchain import EvidenceRegistryClient, BlockchainError
    from backend.evidence import EvidenceRecord
except ImportError:
    print("[!] ERROR: Could not import backend modules.")
    print("    Make sure you are running this from the project root directory:")
    print("      python verify.py --evidence-hash 0x... --source-url https://...")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Read the blockchain record
# ─────────────────────────────────────────────────────────────────────────────
def read_blockchain_record(evidence_hash: str) -> dict:
    """
    Query the Base Sepolia smart contract and retrieve the original
    evidence record (exists, submitter, timestamp, source).
    """
    client = EvidenceRegistryClient()
    exists, submitter, timestamp, source = client.get_evidence(evidence_hash)
    return {
        "exists": exists,
        "submitter": submitter,
        "timestamp": timestamp,
        "source": source,
    }


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Scrape the live web and re-download the current image
# ─────────────────────────────────────────────────────────────────────────────
def download_live_image(image_url: str) -> tuple[bytes | None, str]:
    """
    Download the current version of the image from the live web.
    Returns the raw bytes and the SHA-256 hash of those bytes.
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(image_url, headers=headers, timeout=20)
        response.raise_for_status()

        # MIME-type check: make sure the URL still returns an image
        content_type = response.headers.get("Content-Type", "")
        if not content_type.startswith("image/"):
            return None, ""

        image_bytes = response.content
        image_sha256 = hashlib.sha256(image_bytes).hexdigest()
        return image_bytes, image_sha256

    except requests.exceptions.RequestException as e:
        return None, ""


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Re-build the evidence record from live data and re-hash it
# ─────────────────────────────────────────────────────────────────────────────
def rebuild_evidence_hash(
    source_url: str,
    source: str,
    image_sha256: str,
    title: str = "",
    caption: str = "",
    author: str = "",
    timestamp: str = "",
) -> tuple[str, str]:
    """
    Rebuild the evidence record using the same deterministic canonicalization
    that was used during the original pipeline run, then compute SHA-256.

    Returns (canonical_json_string, evidence_hash_hex).
    """
    record = EvidenceRecord(
        schema_version="1.0",
        source=source,
        source_url=source_url,
        title=title,
        caption=caption,
        author=author,
        timestamp=timestamp,
        image_sha256=image_sha256,
    )
    canonical_json = record.canonical_bytes().decode("utf-8")
    evidence_hash = record.evidence_hash_hex()
    return canonical_json, evidence_hash


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: The Collision Test — compare hashes
# ─────────────────────────────────────────────────────────────────────────────
def compare_hashes(original_hash: str, new_hash: str) -> bool:
    """
    Compare the hash stored on the blockchain with the newly computed hash.
    Returns True if they match (evidence is pristine).
    """
    # Normalize both to lowercase with 0x prefix for fair comparison
    original = original_hash.lower().strip()
    new = new_hash.lower().strip()
    if not original.startswith("0x"):
        original = "0x" + original
    if not new.startswith("0x"):
        new = "0x" + new
    return original == new


# ─────────────────────────────────────────────────────────────────────────────
# Rich output helpers
# ─────────────────────────────────────────────────────────────────────────────
def print_header():
    if HAS_RICH:
        console.print(
            Panel(
                "[bold cyan]FaceChain Tamper Detection[/bold cyan]\n"
                "[dim]Verifying evidence integrity against the blockchain[/dim]",
                border_style="cyan",
            )
        )
    else:
        print("=" * 60)
        print("  FaceChain Tamper Detection")
        print("  Verifying evidence integrity against the blockchain")
        print("=" * 60)


def print_step(number: int, description: str):
    if HAS_RICH:
        console.print(f"\n[bold yellow]Step {number}:[/bold yellow] {description}")
    else:
        print(f"\n[Step {number}] {description}")


def print_result_verified(blockchain_hash: str, live_hash: str):
    if HAS_RICH:
        table = Table(title="Hash Comparison", show_header=True)
        table.add_column("Source", style="cyan")
        table.add_column("SHA-256 Hash", style="green")
        table.add_row("Blockchain (Original)", blockchain_hash)
        table.add_row("Live Web (Current)", live_hash)
        console.print(table)
        console.print(
            Panel(
                "[bold green]✓ VERIFIED: Evidence is PRISTINE.[/bold green]\n\n"
                "The live web content produces the exact same hash as what was\n"
                "anchored on the blockchain. The source data has NOT been altered.",
                border_style="green",
            )
        )
    else:
        print(f"\n  Blockchain Hash : {blockchain_hash}")
        print(f"  Live Web Hash   : {live_hash}")
        print("\n  [✓] VERIFIED: Evidence is PRISTINE.")
        print("      The source data has NOT been altered.")


def print_result_tampered(blockchain_hash: str, live_hash: str):
    if HAS_RICH:
        table = Table(title="Hash Comparison", show_header=True)
        table.add_column("Source", style="cyan")
        table.add_column("SHA-256 Hash")
        table.add_row("Blockchain (Original)", f"[green]{blockchain_hash}[/green]")
        table.add_row("Live Web (Current)", f"[red]{live_hash}[/red]")
        console.print(table)
        console.print(
            Panel(
                "[bold red]✗ TAMPERED: Source evidence has been ALTERED.[/bold red]\n\n"
                "The live web content produces a DIFFERENT hash than what was\n"
                "originally anchored on the blockchain. The source data has\n"
                "been modified, deleted, or replaced since the original verification.",
                border_style="red",
            )
        )
    else:
        print(f"\n  Blockchain Hash : {blockchain_hash}")
        print(f"  Live Web Hash   : {live_hash}")
        print("\n  [✗] TAMPERED: Source evidence has been ALTERED.")
        print("      The source data has been modified since original verification.")


def print_not_found(evidence_hash: str):
    if HAS_RICH:
        console.print(
            Panel(
                f"[bold red]✗ NOT FOUND: No record exists on-chain for:[/bold red]\n"
                f"[dim]{evidence_hash}[/dim]\n\n"
                "This evidence hash was never anchored to the blockchain.\n"
                "Either the hash is incorrect, or the evidence was never verified.",
                border_style="red",
            )
        )
    else:
        print(f"\n  [✗] NOT FOUND: No record on-chain for {evidence_hash}")
        print("      This evidence was never anchored to the blockchain.")


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="FaceChain Tamper Detection — verify if blockchain-anchored evidence has been altered.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check if evidence is still pristine (image-only check):
  python verify.py --evidence-hash 0xabc123... --source-url https://twitter.com/user/post --image-url https://pbs.twimg.com/media/photo.jpg

  # Quick blockchain lookup (does the record exist?):
  python verify.py --evidence-hash 0xabc123... --check-only
        """,
    )
    parser.add_argument(
        "--evidence-hash",
        required=True,
        help="The 0x-prefixed SHA-256 evidence hash that was anchored on-chain.",
    )
    parser.add_argument(
        "--source-url",
        default="",
        help="The original source URL of the social media post or web page.",
    )
    parser.add_argument(
        "--image-url",
        default="",
        help="The direct URL to the image. If not provided, uses source-url.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check if the evidence exists on the blockchain (no live web scrape).",
    )

    args = parser.parse_args()

    print_header()

    # ── Step 1: Read the blockchain ──────────────────────────────────────
    print_step(1, "Reading the blockchain record from Base Sepolia...")

    try:
        record = read_blockchain_record(args.evidence_hash)
    except BlockchainError as e:
        if HAS_RICH:
            console.print(f"[red]Error connecting to blockchain: {e}[/red]")
        else:
            print(f"  ERROR: Could not connect to blockchain: {e}")
        sys.exit(1)

    if not record["exists"]:
        print_not_found(args.evidence_hash)
        sys.exit(1)

    if HAS_RICH:
        console.print(f"  [green]✓[/green] Record found on-chain!")
        console.print(f"    Submitter : [dim]{record['submitter']}[/dim]")
        console.print(f"    Timestamp : [dim]{record['timestamp']}[/dim]")
        console.print(f"    Source    : [dim]{record['source']}[/dim]")
    else:
        print(f"  ✓ Record found on-chain!")
        print(f"    Submitter : {record['submitter']}")
        print(f"    Timestamp : {record['timestamp']}")
        print(f"    Source    : {record['source']}")

    # If --check-only, stop here
    if args.check_only:
        if HAS_RICH:
            console.print(
                Panel(
                    "[green]Evidence exists on the blockchain.[/green]\n"
                    "Use without --check-only to perform a full tamper check.",
                    border_style="green",
                )
            )
        else:
            print("\n  Evidence exists on the blockchain.")
            print("  Use without --check-only to perform a full tamper check.")
        sys.exit(0)

    # ── Step 2: Download the live image from the web ─────────────────────
    image_url = args.image_url or args.source_url
    if not image_url:
        if HAS_RICH:
            console.print("[red]Error: Provide --source-url or --image-url for live tamper check.[/red]")
        else:
            print("  ERROR: Provide --source-url or --image-url for live tamper check.")
        sys.exit(1)

    print_step(2, f"Downloading the CURRENT image from the live web...\n         URL: {image_url}")

    image_bytes, live_image_sha256 = download_live_image(image_url)
    if image_bytes is None:
        if HAS_RICH:
            console.print("[red]  ✗ Failed to download live image. The URL may be broken or blocked.[/red]")
        else:
            print("  ✗ Failed to download live image. The URL may be broken or blocked.")
        sys.exit(1)

    if HAS_RICH:
        console.print(f"  [green]✓[/green] Downloaded {len(image_bytes):,} bytes")
        console.print(f"    Live image SHA-256: [dim]{live_image_sha256}[/dim]")
    else:
        print(f"  ✓ Downloaded {len(image_bytes):,} bytes")
        print(f"    Live image SHA-256: {live_image_sha256}")

    # ── Step 3: Re-build the evidence and re-hash it ─────────────────────
    print_step(3, "Re-building evidence record and computing fresh SHA-256 hash...")

    source_domain = record["source"] or ""
    canonical_json, new_evidence_hash = rebuild_evidence_hash(
        source_url=args.source_url,
        source=source_domain,
        image_sha256=live_image_sha256,
    )

    if HAS_RICH:
        console.print(f"  [green]✓[/green] Canonical JSON rebuilt")
        console.print(f"    New evidence hash: [dim]{new_evidence_hash}[/dim]")
    else:
        print(f"  ✓ Canonical JSON rebuilt")
        print(f"    New evidence hash: {new_evidence_hash}")

    # ── Step 4: The Collision Test ───────────────────────────────────────
    print_step(4, "Comparing blockchain hash vs. live web hash...")

    is_pristine = compare_hashes(args.evidence_hash, new_evidence_hash)

    if is_pristine:
        print_result_verified(args.evidence_hash, new_evidence_hash)
        sys.exit(0)
    else:
        print_result_tampered(args.evidence_hash, new_evidence_hash)
        sys.exit(2)


if __name__ == "__main__":
    main()
