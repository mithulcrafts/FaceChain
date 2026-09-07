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
import os
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime

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
    banner_text = """
╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║   ███████╗ █████╗  ██████╗███████╗ ██████╗██╗  ██╗ █████╗ ██╗███╗ ║
║   ██╔════╝██╔══██╗██╔════╝██╔════╝██╔════╝██║  ██║██╔══██╗██║████║║
║   █████╗  ███████║██║     █████╗  ██║     ███████║███████║██║██╔█║║
║   ██╔══╝  ██╔══██║██║     ██╔══╝  ██║     ██╔══██║██╔══██║██║██║║║║
║   ██║     ██║  ██║╚██████╗███████╗╚██████╗██║  ██║██║  ██║██║██║╚║║
║   ╚═╝     ╚═╝  ╚═╝ ╚═════╝╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═║
║                                                                   ║
║   L2 Identity Verification Pipeline — HH Goa 2026                ║
║   Face Scan → Web Discovery → AI Validation → Blockchain Lock    ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝"""

    console.print(banner_text, style="bright_cyan")
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
        pipeline = FaceChainPipeline()
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
        _log_data("Decision", validation.reason.upper(), "bright_cyan")
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
        _log_data("Stored source", result.anchor.stored_source)
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

    return result


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
