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

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from backend.pipeline import FaceChainPipeline, FaceChainResult, Person1Pipeline
from backend.face import NoFaceDetectedError
from backend.search import ConfigurationError, SearchError

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
console = Console()


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


def run_pipeline(image_path: str, anchor: bool = True, verify: bool = True):
    """Execute the full FaceChain pipeline with rich terminal UI."""

    console.print(Panel.fit(
        "[bold cyan]HH GOA 2026: L2 Identity Verification Pipeline[/bold cyan]\n"
        "[dim]Face Search -> AI Validation -> Evidence Hash -> Base Sepolia[/dim]",
        border_style="cyan"
    ))

    path = Path(image_path)
    if not path.is_file():
        console.print(f"[bold red]CRITICAL HALT: Image file not found: {path}[/bold red]")
        return None

    console.print(f"[*] Input image: [underline]{path.resolve()}[/underline]\n")

    # --- STAGE 1: PERSON 1 - FACE DETECTION + REVERSE SEARCH ---
    console.print("[bold yellow]-- STAGE 1: Face Detection + Reverse Image Search --[/bold yellow]")
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        progress.add_task(description="Detecting face and running dual web search via SerpApi...", total=None)
        pipeline = FaceChainPipeline()
        result = pipeline.run(
            image_path=path,
            results_per_search=30,
            max_candidates=50,
            anchor_on_chain=anchor,
            verify_on_chain=verify,
        )

    person1 = result.person1
    console.print(f"[bold green][OK] Face detected.[/bold green] Score: {person1.primary_face.det_score:.2f}, "
                  f"Embedding: {len(person1.primary_face.embedding)}-D")
    console.print(f"[bold green][OK] Reverse search complete.[/bold green] "
                  f"Found {len(person1.candidates)} candidate(s)\n")

    # --- STAGE 2: PERSON 2 - CANDIDATE VALIDATION ---
    console.print("[bold yellow]-- STAGE 2: AI Candidate Validation --[/bold yellow]")
    validation = result.validation

    if validation.ranked:
        table = Table(title="Candidate Ranking", show_lines=True)
        table.add_column("Rank", style="cyan", justify="center")
        table.add_column("Title", style="white")
        table.add_column("Source", style="dim")
        table.add_column("Face Sim", justify="center")
        table.add_column("Image Sim", justify="center")
        table.add_column("Overall", justify="center", style="bold")
        table.add_column("Matched", justify="center")

        for i, candidate_result in enumerate(validation.ranked[:10], 1):
            matched_str = "[green]YES[/green]" if candidate_result.matched else "[red]NO[/red]"
            table.add_row(
                str(i),
                (candidate_result.candidate.title or "(untitled)")[:40],
                (candidate_result.candidate.source or "?")[:20],
                f"{candidate_result.face_similarity:.3f}",
                f"{candidate_result.image_similarity:.3f}",
                f"{candidate_result.overall_score:.3f}",
                matched_str,
            )
        console.print(table)
        console.print(f"Margin: {validation.margin:.3f} | Decision: {validation.reason}\n")
    else:
        console.print("[dim]No candidates were ranked.[/dim]\n")

    # --- STAGE 3: EVIDENCE + BLOCKCHAIN ---
    if result.status == "rejected":
        console.print(f"[bold red]PIPELINE HALTED: {result.reason}[/bold red]")
        return result

    if result.evidence:
        console.print("[bold yellow]-- STAGE 3: Evidence Canonicalization --[/bold yellow]")
        ev = result.evidence
        console.print(f"  Evidence Hash:  [green]{ev.evidence_hash}[/green]")
        console.print(f"  Image SHA-256:  {ev.candidate_image_sha256}")
        console.print(f"  Source URL:     [underline]{ev.candidate_url}[/underline]")
        console.print(f"  Source:         {ev.candidate_source}\n")

    if result.anchor:
        console.print("[bold yellow]-- STAGE 4: Blockchain Anchor (Base Sepolia) --[/bold yellow]")
        console.print(f"  TX Hash:        [green]{result.anchor.transaction_hash}[/green]")
        console.print(f"  Stored Source:  {result.anchor.stored_source}")
        console.print(f"  Timestamp:      {result.anchor.stored_timestamp}\n")

    if result.verification:
        console.print("[bold yellow]-- STAGE 5: On-Chain Verification --[/bold yellow]")
        v = result.verification
        exists_str = "[green]YES[/green]" if v.exists else "[red]NO[/red]"
        hash_str = "[green]YES[/green]" if v.hash_matches else "[red]NO[/red]"
        source_str = "[green]YES[/green]" if v.source_matches else "[red]NO[/red]"
        console.print(f"  Evidence Exists: {exists_str}")
        console.print(f"  Hash Matches:    {hash_str}")
        console.print(f"  Source Matches:  {source_str}\n")

    # --- FINAL STATUS PANEL ---
    status_color = "green" if result.status in ("verified", "anchored", "evidence_ready") else "red"
    panel_content = (
        f"[bold white]STATUS: {result.status.upper()}[/bold white]\n"
        f"Reason: {result.reason}\n"
    )
    if result.evidence:
        panel_content += f"\nSHA-256 Evidence Hash:\n[green]{result.evidence.evidence_hash}[/green]\n"
    if result.accepted_candidate:
        ac = result.accepted_candidate
        panel_content += (
            f"\nMatched: {ac.candidate.title or '(untitled)'}\n"
            f"URL: [underline]{ac.candidate.url}[/underline]\n"
            f"Overall Score: {ac.overall_score:.3f}\n"
        )

    console.print(Panel(panel_content, title="[bold]Pipeline Result[/bold]", border_style=status_color))
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
        console.print("[bold red]ERROR: SERPAPI_API_KEY not set.[/bold red]")
        console.print("Set it in backend/.env or as an environment variable.")
        sys.exit(1)

    anchor = not args.no_anchor
    verify = not args.no_verify

    if anchor and not os.getenv("EVIDENCE_REGISTRY"):
        console.print("[bold yellow]WARNING: EVIDENCE_REGISTRY not set. "
                      "Blockchain anchoring will fail. Use --no-anchor to skip.[/bold yellow]\n")

    try:
        run_pipeline(args.image_path, anchor=anchor, verify=verify)
    except NoFaceDetectedError as e:
        console.print(f"[bold red]No face detected: {e}[/bold red]")
        sys.exit(1)
    except ConfigurationError as e:
        console.print(f"[bold red]Configuration error: {e}[/bold red]")
        sys.exit(1)
    except SearchError as e:
        console.print(f"[bold red]Search error: {e}[/bold red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Pipeline error: {e}[/bold red]")
        logging.exception("Unhandled pipeline error")
        sys.exit(1)


if __name__ == "__main__":
    main()
