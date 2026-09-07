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
import json
import argparse
import subprocess
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from datetime import datetime
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.resolve() / '.env'
    load_dotenv(dotenv_path=env_path)
except ImportError:
    pass

import requests

# ─── Rich terminal output ────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.rule import Rule
    from rich import box

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


# ─── Cyberpunk UI helpers ───────────────────────────────────────────────────
NEON_CYAN = "bold bright_cyan"
NEON_GREEN = "bold green"
NEON_RED = "bold red"
NEON_YELLOW = "bold yellow"
DIM = "dim white"


def _ts():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _log(symbol, message, style=NEON_GREEN):
    if HAS_RICH:
        console.print(f"  [{DIM}]{_ts()}[/{DIM}]  [{style}]{symbol}[/{style}]  {message}")
    else:
        print(f"  [{_ts()}] {symbol}  {message}")


def _log_ok(msg):
    _log("✓", msg, NEON_GREEN)


def _log_info(msg):
    _log("→", msg, NEON_CYAN)


def _log_fail(msg):
    _log("✗", msg, NEON_RED)


def _log_data(label, value, style="green"):
    if HAS_RICH:
        console.print(f"  [{DIM}]{_ts()}[/{DIM}]  [{NEON_CYAN}]│[/{NEON_CYAN}]  {label}: [{style}]{value}[/{style}]")
    else:
        print(f"  [{_ts()}] │  {label}: {value}")


def _step_header(num, title):
    if HAS_RICH:
        console.print()
        header = Text()
        header.append(f"  ◆ STEP {num} ", style="bold bright_cyan on grey11")
        header.append(f" {title} ", style="bold white on grey11")
        console.print(header)
        console.print()
    else:
        print(f"\n  === STEP {num}: {title} ===\n")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Read the blockchain record
# ─────────────────────────────────────────────────────────────────────────────
def read_blockchain_record(evidence_hash: str) -> dict:
    """
    Query the Base Sepolia smart contract and retrieve the original
    evidence record (exists, submitter, timestamp, source_url).
    """
    client = EvidenceRegistryClient()
    exists, submitter, timestamp, source_url = client.get_evidence(evidence_hash)
    return {
        "exists": exists,
        "submitter": submitter,
        "timestamp": timestamp,
        "source_url": source_url,
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

    except requests.exceptions.RequestException:
        return None, ""


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Re-build the evidence record from live data and re-hash it
# ─────────────────────────────────────────────────────────────────────────────
def rebuild_evidence_hash(
    source_url: str,
    image_sha256: str,
    title: str = "",
    caption: str = "",
    author: str = "",
    timestamp: str = "",
    source: str = "",
) -> tuple[str, str]:
    """
    Rebuild the evidence record using the same deterministic canonicalization
    that was used during the original pipeline run, then compute SHA-256.

    Returns (canonical_json_string, evidence_hash_hex).
    """
    from urllib.parse import urlparse
    parsed = urlparse(source_url)
    domain = source or parsed.netloc.lower().replace("www.", "")

    record = EvidenceRecord(
        schema_version="1.0",
        source=domain,
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
    original = original_hash.lower().strip()
    new = new_hash.lower().strip()
    if not original.startswith("0x"):
        original = "0x" + original
    if not new.startswith("0x"):
        new = "0x" + new
    return original == new


# ─────────────────────────────────────────────────────────────────────────────
# Evidence file loader
# ─────────────────────────────────────────────────────────────────────────────
def load_evidence_file(filepath: str) -> dict:
    """Load a saved evidence package JSON file."""
    path = Path(filepath)
    if not path.is_file():
        # Try relative to project root
        alt = Path(__file__).parent / filepath
        if alt.is_file():
            path = alt
        else:
            return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_evidence_file_by_hash(evidence_hash: str) -> dict:
    """Auto-discover an evidence file in evidence/ directory by hash prefix."""
    evidence_dir = Path(__file__).parent / "evidence"
    if not evidence_dir.is_dir():
        return {}
    for f in evidence_dir.glob("evidence_*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("evidence_hash", "").lower() == evidence_hash.lower():
                return data
        except (json.JSONDecodeError, OSError):
            continue
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="FaceChain Tamper Detection — verify if blockchain-anchored evidence has been altered.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Easiest: load everything from a saved evidence file
  python verify.py --evidence-file evidence/evidence_0x7a3b9f1234567890.json

  # Manual: specify hash and URLs directly
  python verify.py --evidence-hash 0xabc123... --source-url https://twitter.com/user/post --image-url https://pbs.twimg.com/media/photo.jpg

  # Quick blockchain lookup (does it exist?)
  python verify.py --evidence-hash 0xabc123... --check-only
        """,
    )
    parser.add_argument("--evidence-hash", default="", help="The 0x-prefixed SHA-256 evidence hash anchored on-chain.")
    parser.add_argument("--evidence-file", default="", help="Path to a saved evidence JSON file (auto-fills hash, URLs).")
    parser.add_argument("--source-url", default="", help="The original source URL of the social media post.")
    parser.add_argument("--image-url", default="", help="The direct URL to the image.")
    parser.add_argument("--check-only", action="store_true", help="Only check if the evidence exists on-chain.")

    args = parser.parse_args()

    # ── Load evidence file if provided ───────────────────────────────────
    evidence_data = {}
    if args.evidence_file:
        evidence_data = load_evidence_file(args.evidence_file)
        if not evidence_data:
            _log_fail(f"Could not load evidence file: {args.evidence_file}")
            sys.exit(1)
        _log_ok(f"Loaded evidence file: [underline]{args.evidence_file}[/underline]")

    # Fill in missing args from evidence file
    if not args.evidence_hash and evidence_data:
        args.evidence_hash = evidence_data.get("evidence_hash", "")
    if not args.source_url and evidence_data:
        args.source_url = evidence_data.get("source_url", "")
    if not args.image_url and evidence_data:
        # Try to get the image URL from the matched candidate
        mc = evidence_data.get("matched_candidate", {})
        args.image_url = mc.get("image_url", "") or mc.get("url", "") or evidence_data.get("source_url", "")

    # Auto-discover evidence file by hash if no file was provided
    if not evidence_data and args.evidence_hash:
        evidence_data = find_evidence_file_by_hash(args.evidence_hash)
        if evidence_data:
            _log_ok("Auto-discovered saved evidence file for this hash.")
            if not args.source_url:
                args.source_url = evidence_data.get("source_url", "")
            if not args.image_url:
                mc = evidence_data.get("matched_candidate", {})
                args.image_url = mc.get("image_url", "") or mc.get("url", "") or evidence_data.get("source_url", "")

    if not args.evidence_hash:
        _log_fail("No evidence hash provided. Use --evidence-hash or --evidence-file.")
        sys.exit(1)

    # ── BANNER ───────────────────────────────────────────────────────────
    if HAS_RICH:
        banner = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ████████╗ █████╗ ███╗   ███╗██████╗ ███████╗██████╗       ║
║   ╚══██╔══╝██╔══██╗████╗ ████║██╔══██╗██╔════╝██╔══██╗      ║
║      ██║   ███████║██╔████╔██║██████╔╝█████╗  ██████╔╝      ║
║      ██║   ██╔══██║██║╚██╔╝██║██╔═══╝ ██╔══╝  ██╔══██╗      ║
║      ██║   ██║  ██║██║ ╚═╝ ██║██║     ███████╗██║  ██║      ║
║      ╚═╝   ╚═╝  ╚═╝╚═╝     ╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝      ║
║                                                              ║
║   FaceChain Tamper Detection Engine                          ║
║   Blockchain Hash ↔ Live Web Comparison                      ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝"""
        console.print(banner, style="bright_cyan")
        console.print()

        info_table = Table(show_header=False, box=None, padding=(0, 2))
        info_table.add_column(style="dim")
        info_table.add_column(style="bright_cyan")
        info_table.add_row("Mode", "Tamper Verification")
        info_table.add_row("Network", "Base Sepolia (Chain ID: 84532)")
        info_table.add_row("Session", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        console.print(Panel(info_table, border_style="bright_black", title="[dim]System Info[/dim]", title_align="left"))
        console.print()
    else:
        print("=" * 60)
        print("  FaceChain Tamper Detection Engine")
        print("  Blockchain Hash ↔ Live Web Comparison")
        print("=" * 60)

    # ── STEP 1: Read the blockchain ──────────────────────────────────────
    _step_header(1, "READING BLOCKCHAIN RECORD")
    _log_info(f"Querying Base Sepolia for hash: [dim]{args.evidence_hash[:20]}...[/dim]")

    try:
        record = read_blockchain_record(args.evidence_hash)
    except BlockchainError as e:
        _log_fail(f"Blockchain connection failed: {e}")
        sys.exit(1)

    if not record["exists"]:
        _log_fail("No record found on-chain for this evidence hash.")
        if HAS_RICH:
            console.print(Panel(
                f"[bold red]✗ NOT FOUND[/bold red]\n\n"
                f"Evidence hash: [dim]{args.evidence_hash}[/dim]\n\n"
                f"[dim]This hash was never anchored to the blockchain.\n"
                f"Either the hash is incorrect or the evidence was never verified.[/dim]",
                border_style="red",
                title="[red]◆ Result ◆[/red]",
                padding=(1, 3),
            ))
        sys.exit(1)

    _log_ok("Record found on-chain!")
    _log_data("Submitter", record["submitter"], "dim")
    _log_data("Timestamp", str(record["timestamp"]), "dim")
    _log_data("Source URL", record["source_url"], "bright_cyan")

    # Fallback to the blockchain's source URL if one wasn't explicitly provided
    if not args.source_url and record["source_url"]:
        args.source_url = record["source_url"]

    # If --check-only, stop here
    if args.check_only:
        if HAS_RICH:
            console.print()
            console.print(Panel(
                "[bold green]✓ EVIDENCE EXISTS ON-CHAIN[/bold green]\n\n"
                f"Hash:       [green]{args.evidence_hash}[/green]\n"
                f"Submitter:  [dim]{record['submitter']}[/dim]\n"
                f"Source URL: {record['source_url']}\n"
                f"Timestamp:  {record['timestamp']}\n\n"
                "[dim]Use without --check-only to perform a full tamper check.[/dim]",
                border_style="green",
                title="[green]◆ Result ◆[/green]",
                padding=(1, 3),
            ))
        sys.exit(0)

    # ── STEP 2: Download the live image ──────────────────────────────────
    image_url = args.image_url or args.source_url
    if not image_url:
        _log_fail("No URL provided. Use --source-url or --image-url for live tamper check.")
        sys.exit(1)

    _step_header(2, "SCRAPING LIVE WEB")
    _log_info(f"Downloading current image from:")
    _log_data("URL", f"[underline]{image_url}[/underline]", "bright_cyan")

    t0 = time.perf_counter()
    image_bytes, live_image_sha256 = download_live_image(image_url)
    t1 = time.perf_counter()

    if image_bytes is None:
        _log_fail("Source URL is no longer accessible or did not return an image.")
        if HAS_RICH:
            console.print(Panel(
                "[bold yellow]⚠ UNAVAILABLE: Source content cannot be retrieved[/bold yellow]\n\n"
                "The URL did not return a valid image. This does [bold]NOT[/bold] necessarily\n"
                "mean the evidence was tampered with. Possible reasons:\n\n"
                "  • The content was deleted by the owner\n"
                "  • The server is temporarily down\n"
                "  • The URL is behind a login wall or CAPTCHA\n"
                "  • The website is blocking automated requests\n\n"
                f"[dim]URL: {image_url}\n"
                f"Checked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]",
                border_style="yellow",
                title="[bold yellow]◆ VERDICT: UNAVAILABLE ◆[/bold yellow]",
                padding=(1, 3),
            ))
        else:
            print("\n  [⚠] UNAVAILABLE: Source content cannot be retrieved.")
            print("      This does NOT necessarily mean the evidence was tampered with.")
        sys.exit(3)

    _log_ok(f"Downloaded in [bold]{t1 - t0:.1f}s[/bold]")
    _log_data("Payload size", f"{len(image_bytes):,} bytes ({len(image_bytes) / 1024:.1f} KB)")
    _log_data("Live image SHA-256", live_image_sha256, "dim")

    # ── STEP 3: Re-hash ──────────────────────────────────────────────────
    _step_header(3, "RE-HASHING EVIDENCE")
    _log_info("Rebuilding canonical evidence record from live data...")

    record_data = evidence_data.get("record", {})
    canonical_json, new_evidence_hash = rebuild_evidence_hash(
        source_url=args.source_url,
        image_sha256=live_image_sha256,
        title=record_data.get("title", ""),
        caption=record_data.get("caption", ""),
        author=record_data.get("author", ""),
        timestamp=record_data.get("timestamp", ""),
        source=record_data.get("source", ""),
    )

    _log_ok("Canonical JSON rebuilt with deterministic serialization.")
    _log_data("New evidence hash", new_evidence_hash, "bright_cyan")

    # ── STEP 4: The Collision Test ───────────────────────────────────────
    _step_header(4, "COLLISION TEST")
    _log_info("Comparing blockchain hash vs. live web hash...")

    is_pristine = compare_hashes(args.evidence_hash, new_evidence_hash)

    if HAS_RICH:
        console.print()

        # Hash comparison table
        cmp_table = Table(
            title="[bright_cyan]◆ Hash Comparison ◆[/bright_cyan]",
            show_lines=True,
            border_style="bright_black",
            box=box.HEAVY_HEAD,
            padding=(0, 2),
        )
        cmp_table.add_column("Source", style="white", width=25)
        cmp_table.add_column("SHA-256 Evidence Hash", width=50)

        if is_pristine:
            cmp_table.add_row("Blockchain (Original)", f"[green]{args.evidence_hash}[/green]")
            cmp_table.add_row("Live Web (Current)", f"[green]{new_evidence_hash}[/green]")
        else:
            cmp_table.add_row("Blockchain (Original)", f"[green]{args.evidence_hash}[/green]")
            cmp_table.add_row("Live Web (Current)", f"[bold red]{new_evidence_hash}  ← CHANGED[/bold red]")

        console.print(cmp_table)
        console.print()

        # Final verdict
        if is_pristine:
            console.print(Panel(
                "[bold green]✓ VERIFIED: Evidence is PRISTINE[/bold green]\n\n"
                "The live web content produces the [bold]exact same hash[/bold] as what was\n"
                "anchored on the blockchain. The source data has [bold]NOT[/bold] been altered.\n\n"
                f"[dim]Hash: {args.evidence_hash}\n"
                f"Verified at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]",
                border_style="green",
                title="[bold green]◆ VERDICT: PRISTINE ◆[/bold green]",
                padding=(1, 3),
            ))
        else:
            console.print(Panel(
                "[bold red]✗ TAMPERED: Source evidence has been ALTERED[/bold red]\n\n"
                "The live web content produces a [bold]DIFFERENT hash[/bold] than what was\n"
                "originally anchored on the blockchain. The source data has been\n"
                "modified, deleted, or replaced since the original verification.\n\n"
                f"[dim]Original hash: {args.evidence_hash}\n"
                f"Current hash:  {new_evidence_hash}\n"
                f"Checked at:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]",
                border_style="red",
                title="[bold red]◆ VERDICT: TAMPERED ◆[/bold red]",
                padding=(1, 3),
            ))
    else:
        print(f"\n  Blockchain Hash : {args.evidence_hash}")
        print(f"  Live Web Hash   : {new_evidence_hash}")
        if is_pristine:
            print("\n  [✓] VERIFIED: Evidence is PRISTINE.")
        else:
            print("\n  [✗] TAMPERED: Source evidence has been ALTERED.")

    console.print() if HAS_RICH else print()
    sys.exit(0 if is_pristine else 2)


if __name__ == "__main__":
    main()
