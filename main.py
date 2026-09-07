"""
HH GOA 2026: L2 Identity Verification Pipeline
Master orchestrator that ties together:
  - Person 1: Face detection + reverse image search (SerpApi Google Lens)
  - Person 2: Candidate validation (face similarity, image similarity, scoring)
  - Person 3: Evidence canonicalization + blockchain anchoring (Base Sepolia)

Usage:
  python main.py <path_to_face_image>
  python main.py query_face.jpg
  python main.py query_face.jpg --no-anchor      # skip blockchain
  python main.py query_face.jpg --summary         # concise output
"""

import sys
# Force UTF-8 encoding for Windows terminals to support rich cyberpunk UI
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

import os
import time
import json
import hashlib
import argparse
import logging
from pathlib import Path
from datetime import datetime

try:
    from dotenv import load_dotenv
    # Load from the same directory as this file (the project root)
    env_path = Path(__file__).parent.resolve() / '.env'
    load_dotenv(dotenv_path=env_path)
except ImportError:
    pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.rule import Rule
from rich.align import Align
from rich import box

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from backend.pipeline import FaceChainPipeline, FaceChainResult, Person1Pipeline
from backend.face import NoFaceDetectedError
from backend.search import ConfigurationError, SearchError

logging.basicConfig(level=logging.WARNING, format="%(message)s")
console = Console()

# ─── Cyberpunk Color Palette ─────────────────────────────────────────────────
NEON_CYAN = "bold bright_cyan"
NEON_GREEN = "bold green"
NEON_YELLOW = "bold yellow"
NEON_RED = "bold red"
NEON_MAGENTA = "bold magenta"
NEON_WHITE = "bold white"
DIM = "dim white"
ACCENT = "bold bright_cyan"


def _timestamp():
    """Return a formatted timestamp for log lines."""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _log(symbol, message, style=NEON_GREEN):
    """Print a cyberpunk-styled log line."""
    console.print(f"  [{DIM}]{_timestamp()}[/{DIM}]  [{style}]{symbol}[/{style}]  {message}")


def _log_ok(message):
    _log("✓", message, NEON_GREEN)


def _log_info(message):
    _log("→", message, NEON_CYAN)


def _log_warn(message):
    _log("⚠", message, NEON_YELLOW)


def _log_fail(message):
    _log("✗", message, NEON_RED)


def _log_data(label, value, value_style="green"):
    """Print a key-value data line."""
    console.print(f"  [{DIM}]{_timestamp()}[/{DIM}]  [{NEON_CYAN}]│[/{NEON_CYAN}]  {label}: [{value_style}]{value}[/{value_style}]")


def _stage_header(stage_num, title, subtitle=""):
    """Print a glowing stage header."""
    console.print()
    header = Text()
    header.append(f"  ◆ STAGE {stage_num} ", style="bold bright_cyan on grey11")
    header.append(f" {title} ", style="bold white on grey11")
    console.print(header)
    if subtitle:
        console.print(f"  [dim]  {subtitle}[/dim]")
    console.print()


def load_env_file():
    """Load backend/.env into os.environ if it exists."""
    env_path = Path(__file__).parent / "backend" / ".env"
    if not env_path.exists():
        return
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value:
                os.environ.setdefault(key, value)


def print_banner():
    """Print the cyberpunk ASCII banner."""
    ascii_logo = """
███████╗ █████╗  ██████╗███████╗ ██████╗██╗  ██╗ █████╗ ██╗███╗   ██╗
██╔════╝██╔══██╗██╔════╝██╔════╝██╔════╝██║  ██║██╔══██╗██║████╗  ██║
█████╗  ███████║██║     █████╗  ██║     ███████║███████║██║██╔██╗ ██║
██╔══╝  ██╔══██║██║     ██╔══╝  ██║     ██╔══██║██╔══██║██║██║╚██╗██║
██║     ██║  ██║╚██████╗███████╗╚██████╗██║  ██║██║  ██║██║██║ ╚████║
╚═╝     ╚═╝  ╚═╝ ╚═════╝╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝"""

    title_text = Text.from_markup(
        f"[bold cyan]{ascii_logo}[/bold cyan]\n\n"
        "[bold white]L2 Identity Verification Pipeline[/bold white] — [bold cyan]HH Goa 2026[/bold cyan]\n"
        "[dim]Face Scan → Web Discovery → AI Validation → Blockchain Lock[/dim]",
        justify="center"
    )
    console.print(Panel(title_text, border_style="bright_cyan", padding=(1, 2)))
    console.print()

    # System info bar
    info_table = Table(show_header=False, box=None, padding=(0, 2))
    info_table.add_column(style="dim")
    info_table.add_column(style="bright_cyan")
    info_table.add_row("Network", "Base Sepolia (Chain ID: 84532)")
    info_table.add_row("AI Engine", "InsightFace ArcFace 512-D")
    info_table.add_row("Contract", "EvidenceRegistry.sol (Solidity 0.8.25)")
    info_table.add_row("Toolchain", "Foundry (forge + cast)")
    info_table.add_row("Session", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    console.print(Panel(info_table, border_style="bright_black", title="[dim]System Info[/dim]", title_align="left"))
    console.print()


def _compute_input_hash(path: Path) -> str:
    """Compute SHA-256 of the input image for deduplication."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def check_existing_evidence(input_image_sha256: str) -> dict | None:
    """Check if we already have evidence for this exact input image.
    Prevents duplicate blockchain entries when the same face is scanned twice."""
    evidence_dir = Path(__file__).parent / "evidence"
    if not evidence_dir.is_dir():
        return None
    for f in evidence_dir.glob("evidence_*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("input_image_sha256") == input_image_sha256:
                return data
        except (json.JSONDecodeError, OSError):
            continue
    return None


def auto_verify_evidence(evidence_file_path: str):
    """Automatically run the tamper detection pipeline after anchoring.
    This runs the full 4-step verify.py logic inline."""
    from verify import (
        read_blockchain_record,
        download_live_image,
        rebuild_evidence_hash,
        compare_hashes,
    )
    from backend.blockchain import BlockchainError

    with open(evidence_file_path, "r", encoding="utf-8") as f:
        evidence_data = json.load(f)

    evidence_hash = evidence_data.get("evidence_hash", "")
    source_url = evidence_data.get("source_url", "")
    image_url = source_url  # Use source URL as image URL

    # Try to get a direct image URL from matched candidate
    mc = evidence_data.get("matched_candidate", {})
    if mc.get("image_url"):
        image_url = mc["image_url"]
    elif mc.get("url"):
        image_url = mc["url"]

    _stage_header(6, "TAMPER DETECTION", "Re-download → Re-hash → Collision Test")

    # Step 1: Read blockchain
    _log_info(f"Step 1: Reading blockchain record for hash [dim]{evidence_hash[:20]}...[/dim]")
    try:
        record = read_blockchain_record(evidence_hash)
    except BlockchainError as e:
        _log_warn(f"Blockchain query failed: {e}")
        _log_data("Tamper check", "SKIPPED (blockchain unavailable)", "yellow")
        return

    if not record["exists"]:
        _log_warn("Evidence not yet confirmed on-chain. Tamper check skipped.")
        return

    _log_ok("Record found on-chain.")
    _log_data("Submitter", record["submitter"], "dim")
    _log_data("Timestamp", str(record["timestamp"]), "dim")
    console.print()

    # Step 2: Download live image
    _log_info(f"Step 2: Scraping live web content from [underline]{image_url}[/underline]")
    t0_v = time.perf_counter()
    image_bytes, live_image_sha256 = download_live_image(image_url)
    t1_v = time.perf_counter()

    if image_bytes is None:
        _log_warn("Source URL is no longer accessible or did not return an image.")
        console.print(Panel(
            "[bold yellow]⚠ UNAVAILABLE: Source content cannot be retrieved[/bold yellow]\n\n"
            "The URL did not return a valid image. This does [bold]NOT[/bold] mean tampering.\n"
            "Possible reasons: content deleted, server down, CAPTCHA, or blocking.",
            border_style="yellow",
            title="[bold yellow]◆ VERDICT: UNAVAILABLE ◆[/bold yellow]",
            padding=(1, 2),
        ))
        return

    _log_ok(f"Downloaded in {t1_v - t0_v:.1f}s ({len(image_bytes):,} bytes)")
    console.print()

    # Step 3: Re-hash
    _log_info("Step 3: Rebuilding canonical evidence and computing new SHA-256...")
    record_data = evidence_data.get("record", {})
    canonical_json, new_evidence_hash = rebuild_evidence_hash(
        source_url=source_url,
        image_sha256=live_image_sha256,
        title=record_data.get("title", ""),
        caption=record_data.get("caption", ""),
        author=record_data.get("author", ""),
        timestamp=record_data.get("timestamp", ""),
        source=record_data.get("source", ""),
    )
    _log_ok(f"New hash: [dim]{new_evidence_hash}[/dim]")
    console.print()

    # Step 4: Collision test
    _log_info("Step 4: Collision test — comparing blockchain hash vs. live hash...")
    is_pristine = compare_hashes(evidence_hash, new_evidence_hash)

    # Hash comparison table
    from rich import box as rbox
    cmp_table = Table(
        title="[bright_cyan]◆ Hash Comparison ◆[/bright_cyan]",
        show_lines=True,
        border_style="bright_black",
        box=rbox.HEAVY_HEAD,
        padding=(0, 2),
    )
    cmp_table.add_column("Source", style="white", width=25)
    cmp_table.add_column("SHA-256 Evidence Hash", width=50)

    if is_pristine:
        cmp_table.add_row("Blockchain (Original)", f"[green]{evidence_hash}[/green]")
        cmp_table.add_row("Live Web (Current)", f"[green]{new_evidence_hash}[/green]")
    else:
        cmp_table.add_row("Blockchain (Original)", f"[green]{evidence_hash}[/green]")
        cmp_table.add_row("Live Web (Current)", f"[bold red]{new_evidence_hash}  ← CHANGED[/bold red]")

    console.print(cmp_table)
    console.print()

    if is_pristine:
        console.print(Panel(
            "[bold green]✓ VERIFIED: Evidence is PRISTINE[/bold green]\n\n"
            "The live web content produces the [bold]exact same hash[/bold] as the blockchain.\n"
            "The source data has [bold]NOT[/bold] been altered since anchoring.",
            border_style="green",
            title="[bold green]◆ VERDICT: PRISTINE ◆[/bold green]",
            padding=(1, 2),
        ))
    else:
        console.print(Panel(
            "[bold red]✗ TAMPERED: Source evidence has been ALTERED[/bold red]\n\n"
            "The live web content produces a [bold]DIFFERENT hash[/bold] than the blockchain.\n"
            "The source data has been modified since the original verification.",
            border_style="red",
            title="[bold red]◆ VERDICT: TAMPERED ◆[/bold red]",
            padding=(1, 2),
        ))
    console.print()


def run_pipeline(image_path: str, anchor: bool = True, verify: bool = True):
    """Execute the full FaceChain pipeline with cyberpunk terminal UI."""

    print_banner()

    path = Path(image_path)
    if not path.is_file():
        _log_fail(f"CRITICAL HALT: Image file not found: [underline]{path}[/underline]")
        return None

    console.print(Rule(style="bright_black"))
    _log_info(f"Input image loaded: [underline]{path.resolve()}[/underline]")
    file_size = path.stat().st_size
    _log_data("File size", f"{file_size:,} bytes ({file_size / 1024:.1f} KB)")
    _log_data("Format", path.suffix.upper().replace(".", ""))

    # ─── Deduplication Check ─────────────────────────────────────────────
    input_image_sha256 = _compute_input_hash(path)
    _log_data("Input SHA-256", input_image_sha256[:16] + "...", "dim")
    existing = check_existing_evidence(input_image_sha256)
    if existing:
        _log_warn("This exact image was already processed!")
        _log_data("Existing evidence", existing.get("evidence_hash", "")[:20] + "...", "yellow")
        _log_data("Matched identity", existing.get("matched_candidate", {}).get("title", "unknown"), "yellow")
        _log_data("Source", existing.get("source_url", ""), "yellow")
        console.print(Panel(
            f"[bold yellow]⚠ DUPLICATE DETECTED[/bold yellow]\n\n"
            f"This input image has already been processed and anchored.\n\n"
            f"Evidence Hash: [green]{existing.get('evidence_hash', '')}[/green]\n"
            f"Source: {existing.get('source_url', '')}\n"
            f"Processed at: {existing.get('saved_at', 'unknown')}\n\n"
            f"[dim]To re-process, delete the existing evidence file first:\n"
            f"  Remove-Item evidence/evidence_{existing.get('evidence_hash', '')[:18]}.json[/dim]",
            border_style="yellow",
            title="[yellow]◆ Duplicate Prevention ◆[/yellow]",
            padding=(1, 3),
        ))
        return None
    console.print()

    # ═══════════════════════════════════════════════════════════════════════
    # STAGE 1: FACE DETECTION + REVERSE IMAGE SEARCH
    # ═══════════════════════════════════════════════════════════════════════
    _stage_header(1, "FACE DETECTION + WEB DISCOVERY", "InsightFace ArcFace → SerpApi Google Lens dual search")

    t0 = time.perf_counter()
    with Progress(
        SpinnerColumn(spinner_name="dots12", style="bright_cyan"),
        TextColumn("[bright_cyan]{task.description}[/bright_cyan]"),
        BarColumn(bar_width=30, style="bright_black", complete_style="bright_cyan", finished_style="green"),
        transient=True,
        console=console,
    ) as progress:
        task = progress.add_task("  Initializing face detection engine...", total=100)
        pipeline = FaceChainPipeline(
            allow_score_floor_fallback=True,
            accept_score_floor=0.85,
        )
        progress.update(task, completed=20, description="  Extracting 512-D ArcFace embedding...")
        result = pipeline.run(
            image_path=path,
            results_per_search=30,
            max_candidates=50,
            anchor_on_chain=anchor,
            verify_on_chain=verify,
        )
        progress.update(task, completed=100, description="  Discovery complete.")

    t1 = time.perf_counter()
    person1 = result.person1

    _log_ok(f"Face detected in [bold]{t1 - t0:.1f}s[/bold]")
    _log_data("Detection score", f"{person1.primary_face.det_score:.4f}")
    _log_data("Embedding dimensions", f"{len(person1.primary_face.embedding)}-D ArcFace vector")
    _log_data("Faces in image", str(person1.detected_faces_count))
    _log_data("Search candidates found", f"{len(person1.candidates)} results from dual search")
    console.print()

    # ═══════════════════════════════════════════════════════════════════════
    # STAGE 2: AI CANDIDATE VALIDATION
    # ═══════════════════════════════════════════════════════════════════════
    _stage_header(2, "AI CANDIDATE VALIDATION", "Cosine similarity + HSV histogram + source consistency")

    validation = result.validation

    if validation.ranked:
        table = Table(
            title="[bright_cyan]◆ Candidate Ranking Matrix[/bright_cyan]",
            show_lines=True,
            border_style="bright_black",
            title_style="bright_cyan",
            box=box.HEAVY_HEAD,
            padding=(0, 1),
        )
        table.add_column("#", style="bright_cyan", justify="center", width=3)
        table.add_column("Source", style="dim", width=15)
        table.add_column("Title", style="white", max_width=35, no_wrap=True)
        table.add_column("Face", justify="center", width=7)
        table.add_column("Image", justify="center", width=7)
        table.add_column("Score", justify="center", width=7, style="bold")
        table.add_column("Status", justify="center", width=10)

        for i, cr in enumerate(validation.ranked[:10], 1):
            # Color-code the scores
            face_color = "green" if cr.face_similarity >= 0.70 else "yellow" if cr.face_similarity >= 0.50 else "red"
            img_color = "green" if cr.image_similarity >= 0.50 else "yellow" if cr.image_similarity >= 0.30 else "red"
            score_color = "green" if cr.overall_score >= 0.70 else "yellow" if cr.overall_score >= 0.50 else "red"
            status = "[bold green]▓ MATCH[/bold green]" if cr.matched else "[dim red]░ REJECT[/dim red]"

            table.add_row(
                str(i),
                (cr.candidate.source or "—")[:15],
                (cr.candidate.title or "(untitled)")[:35],
                f"[{face_color}]{cr.face_similarity:.3f}[/{face_color}]",
                f"[{img_color}]{cr.image_similarity:.3f}[/{img_color}]",
                f"[{score_color}]{cr.overall_score:.3f}[/{score_color}]",
                status,
            )

        console.print(table)
        console.print()

        # Margin indicator
        margin_color = "green" if validation.margin >= 0.05 else "yellow" if validation.margin >= 0.02 else "red"
        _log_data("Confidence margin", f"{validation.margin:.4f}", margin_color)

        # Detect score-floor acceptance: validator rejected (ambiguous) but pipeline accepted
        is_score_floor_accepted = (
            validation.accepted is None
            and result.accepted_candidate is not None
            and result.status != "rejected"
        )

        if is_score_floor_accepted:
            _log_data("Decision", "ACCEPTED BY CONSENSUS (SCORE FLOOR)", "bold green")
            _log_data(
                "Reason",
                f"Top candidate scored {result.accepted_candidate.overall_score:.3f} (above floor 0.85) with strong individual match",
                "dim",
            )
        else:
            decision_color = "green" if validation.accepted else "red"
            _log_data("Decision", validation.reason.upper(), decision_color)
        console.print()
    else:
        _log_warn("No candidates were ranked.")
        console.print()

    # ═══════════════════════════════════════════════════════════════════════
    # STAGE 3: EVIDENCE CANONICALIZATION
    # ═══════════════════════════════════════════════════════════════════════
    if result.status == "rejected":
        _stage_header(3, "PIPELINE HALTED", "")
        _log_fail(f"Reason: {result.reason}")
        console.print(Panel(
            f"[bold red]✗ PIPELINE REJECTED[/bold red]\n\n"
            f"Reason: {result.reason}\n\n"
            f"[dim]No candidate met the required thresholds across all four metrics.\n"
            f"Try a higher-resolution image with a clear, front-facing face.[/dim]",
            border_style="red",
            title="[bold red]Result[/bold red]",
        ))
        return result

    if result.evidence:
        _stage_header(3, "EVIDENCE CANONICALIZATION", "Deterministic JSON → SHA-256 fingerprint")

        ev = result.evidence
        _log_ok("Evidence record built and hashed.")
        _log_data("Evidence hash", ev.evidence_hash, "green")
        _log_data("Image SHA-256", ev.candidate_image_sha256, "dim")
        _log_data("Source URL", f"[underline]{ev.candidate_url}[/underline]", "bright_cyan")
        _log_data("Source domain", ev.candidate_source)
        console.print()

    # ═══════════════════════════════════════════════════════════════════════
    # STAGE 4: BLOCKCHAIN ANCHOR
    # ═══════════════════════════════════════════════════════════════════════
    if result.anchor:
        _stage_header(4, "BLOCKCHAIN ANCHOR", "Base Sepolia (L2) via Foundry cast")

        _log_ok("Evidence anchored on-chain.")
        _log_data("TX hash", result.anchor.transaction_hash, "green")
        _log_data("Stored source", result.anchor.stored_source_url)
        _log_data("Block timestamp", str(result.anchor.stored_timestamp))
        console.print()

    # ═══════════════════════════════════════════════════════════════════════
    # STAGE 5: ON-CHAIN VERIFICATION
    # ═══════════════════════════════════════════════════════════════════════
    if result.verification:
        _stage_header(5, "ON-CHAIN VERIFICATION", "Read-back from Base Sepolia to confirm mining")

        v = result.verification
        exists_icon = "[bold green]✓ YES[/bold green]" if v.exists else "[bold red]✗ NO[/bold red]"
        hash_icon = "[bold green]✓ YES[/bold green]" if v.hash_matches else "[bold red]✗ NO[/bold red]"
        source_icon = "[bold green]✓ YES[/bold green]" if v.source_matches else "[bold red]✗ NO[/bold red]"

        verify_table = Table(show_header=False, box=box.SIMPLE, border_style="bright_black", padding=(0, 2))
        verify_table.add_column("Check", style="white", width=25)
        verify_table.add_column("Result", width=15)
        verify_table.add_row("Evidence exists on-chain", exists_icon)
        verify_table.add_row("Hash matches", hash_icon)
        verify_table.add_row("Source matches", source_icon)
        console.print(verify_table)
        console.print()

    # ═══════════════════════════════════════════════════════════════════════
    # FINAL RESULT PANEL
    # ═══════════════════════════════════════════════════════════════════════
    console.print(Rule(style="bright_black"))

    is_success = result.status in ("verified", "anchored", "evidence_ready")
    border_color = "green" if is_success else "red"
    status_icon = "✓" if is_success else "✗"

    # Build the result content
    lines = []
    lines.append(f"[bold {'green' if is_success else 'red'}]{status_icon} {result.status.upper()}[/bold {'green' if is_success else 'red'}]")
    lines.append(f"[dim]Reason: {result.reason}[/dim]")
    lines.append("")

    if result.evidence:
        lines.append(f"[bright_cyan]Evidence Fingerprint:[/bright_cyan]")
        lines.append(f"[green]{result.evidence.evidence_hash}[/green]")
        lines.append("")

    if result.accepted_candidate:
        ac = result.accepted_candidate
        lines.append(f"[bright_cyan]Matched Identity:[/bright_cyan]")
        lines.append(f"  Title:    {ac.candidate.title or '(untitled)'}")
        lines.append(f"  Source:   {ac.candidate.source or '—'}")
        lines.append(f"  URL:      [underline]{ac.candidate.url}[/underline]")
        lines.append(f"  Score:    [green]{ac.overall_score:.3f}[/green]")
        lines.append("")

    if result.anchor:
        lines.append(f"[bright_cyan]Blockchain Record:[/bright_cyan]")
        lines.append(f"  TX:       [green]{result.anchor.transaction_hash}[/green]")
        lines.append(f"  Network:  Base Sepolia (84532)")
        lines.append("")

    elapsed = time.perf_counter() - t0
    lines.append(f"[dim]Completed in {elapsed:.1f}s at {datetime.now().strftime('%H:%M:%S')}[/dim]")

    console.print(Panel(
        "\n".join(lines),
        title=f"[bold {'green' if is_success else 'red'}]◆ Pipeline Result ◆[/bold {'green' if is_success else 'red'}]",
        border_style=border_color,
        padding=(1, 3),
    ))
    console.print()

    # ═══════════════════════════════════════════════════════════════════════
    # SAVE EVIDENCE PACKAGE TO DISK
    # ═══════════════════════════════════════════════════════════════════════
    evidence_filepath = None
    if result.evidence and result.status != "rejected":
        evidence_filepath = save_evidence_package(result)

    # ═══════════════════════════════════════════════════════════════════════
    # STAGE 6: AUTO-VERIFY (TAMPER DETECTION)
    # ═══════════════════════════════════════════════════════════════════════
    if evidence_filepath and result.anchor:
        try:
            auto_verify_evidence(str(evidence_filepath))
        except Exception as e:
            _log_warn(f"Auto-verify skipped: {e}")

    return result


def save_evidence_package(result: FaceChainResult):
    """Persist the evidence package to evidence/ directory for later verification."""
    evidence_dir = Path(__file__).parent / "evidence"
    evidence_dir.mkdir(exist_ok=True)

    ev = result.evidence
    # Use short hash as filename for uniqueness
    short_hash = ev.evidence_hash[:18]  # 0x + 16 hex chars
    filename = f"evidence_{short_hash}.json"

    # Compute input image SHA-256 for deduplication
    input_path = Path(result.input_image_path)
    input_sha256 = _compute_input_hash(input_path) if input_path.is_file() else ""

    package = {
        "evidence_hash": ev.evidence_hash,
        "source_url": ev.candidate_url,
        "source_domain": ev.candidate_source,
        "image_sha256": ev.candidate_image_sha256,
        "input_image_sha256": input_sha256,
        "candidate_id": ev.candidate_id,
        "canonical_json": ev.canonical_json,
        "record": ev.record.model_dump(),
        "input_image": result.input_image_path,
        "pipeline_status": result.status,
        "pipeline_reason": result.reason,
        "saved_at": datetime.now().isoformat(),
    }

    if result.accepted_candidate:
        ac = result.accepted_candidate
        package["matched_candidate"] = {
            "title": ac.candidate.title,
            "url": ac.candidate.url,
            "image_url": ac.candidate.image_url,
            "source": ac.candidate.source,
            "face_similarity": ac.face_similarity,
            "image_similarity": ac.image_similarity,
            "overall_score": ac.overall_score,
        }

    if result.anchor:
        package["blockchain"] = {
            "tx_hash": result.anchor.transaction_hash,
            "stored_source": result.anchor.stored_source_url,
            "stored_timestamp": result.anchor.stored_timestamp,
        }

    filepath = evidence_dir / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(package, f, indent=2, ensure_ascii=False)

    _log_ok(f"Evidence saved: [underline]evidence/{filename}[/underline]")
    console.print()

    # Auto-display evidence package
    display_table = Table(
        title="[bright_cyan]◆ Evidence Package ◆[/bright_cyan]",
        show_lines=False,
        border_style="bright_black",
        box=box.SIMPLE_HEAVY,
        padding=(0, 2),
    )
    display_table.add_column("Field", style="bright_cyan", width=20)
    display_table.add_column("Value", style="white")
    display_table.add_row("Evidence Hash", f"[green]{package['evidence_hash']}[/green]")
    display_table.add_row("Source URL", f"[underline]{package['source_url']}[/underline]")
    display_table.add_row("Source Domain", package.get("source_domain", ""))
    display_table.add_row("Image SHA-256", f"[dim]{package['image_sha256']}[/dim]")
    if package.get("matched_candidate"):
        mc = package["matched_candidate"]
        display_table.add_row("Matched Title", mc.get("title", ""))
        display_table.add_row("Face Similarity", f"[green]{mc.get('face_similarity', 0):.3f}[/green]")
        display_table.add_row("Overall Score", f"[green]{mc.get('overall_score', 0):.3f}[/green]")
    if package.get("blockchain"):
        bc = package["blockchain"]
        display_table.add_row("TX Hash", f"[green]{bc.get('tx_hash', '')}[/green]")
    display_table.add_row("Saved At", package.get("saved_at", ""))
    console.print(display_table)
    console.print()

    return filepath


def main():
    parser = argparse.ArgumentParser(
        description="HH GOA 2026: L2 Identity Verification Pipeline"
    )
    parser.add_argument("image_path", type=str, help="Path to the input face image")
    parser.add_argument("--no-anchor", action="store_true",
                        help="Skip blockchain anchoring (stop after evidence generation)")
    parser.add_argument("--no-verify", action="store_true",
                        help="Skip on-chain verification after anchoring")

    args = parser.parse_args()

    # Load .env file for API keys and blockchain config
    load_env_file()

    # Check critical environment variables
    if not os.getenv("SERPAPI_API_KEY"):
        console.print(Panel(
            "[bold red]✗ SERPAPI_API_KEY not set[/bold red]\n\n"
            "[dim]Set it in backend/.env or as an environment variable:\n"
            "  export SERPAPI_API_KEY=your_key_here[/dim]",
            border_style="red",
            title="[red]Configuration Error[/red]",
        ))
        sys.exit(1)

    anchor = not args.no_anchor
    verify = not args.no_verify

    if anchor and not os.getenv("EVIDENCE_REGISTRY"):
        _log_warn("EVIDENCE_REGISTRY not set. Blockchain anchoring will fail. Use --no-anchor to skip.")
        console.print()

    try:
        run_pipeline(args.image_path, anchor=anchor, verify=verify)
    except NoFaceDetectedError as e:
        _log_fail(f"No face detected: {e}")
        sys.exit(1)
    except ConfigurationError as e:
        _log_fail(f"Configuration error: {e}")
        sys.exit(1)
    except SearchError as e:
        _log_fail(f"Search error: {e}")
        sys.exit(1)
    except Exception as e:
        _log_fail(f"Pipeline error: {e}")
        logging.exception("Unhandled pipeline error")
        sys.exit(1)


if __name__ == "__main__":
    main()
