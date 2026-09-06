"""
Command-line interface for FaceID Verification.

Usage:
  python -m backend.cli run path/to/image.jpg
  python -m backend.cli person1 path/to/image.jpg
  python -m backend.cli verify-evidence
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from backend.blockchain import BlockchainError, EvidenceRegistryClient
from backend.pipeline import FaceChainPipeline, Person1Pipeline


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    return value


def _print_payload(payload: Any, pretty: bool) -> None:
    if hasattr(payload, "model_dump"):
        data = payload.model_dump()
    else:
        data = payload

    if pretty:
        print(json.dumps(data, indent=2, ensure_ascii=False, default=_json_default))
    else:
        print(json.dumps(data, separators=(",", ":"), ensure_ascii=False, default=_json_default))


def _print_run_summary(result: Any) -> None:
    """Print the small set of facts needed to understand a completed run."""
    print("FaceID Verification")
    print(f"Status: {getattr(result, 'status', 'unknown').upper()}")
    print(f"Reason: {getattr(result, 'reason', '')}")

    accepted = getattr(result, "accepted_candidate", None)
    if accepted is not None:
        candidate = accepted.candidate
        print("\nMatched candidate")
        print(f"  Title: {candidate.title or '(untitled)'}")
        print(f"  Source: {candidate.source or '(unknown)'}")
        print(f"  URL: {candidate.url or '(unavailable)'}")
        print(f"  Face similarity: {accepted.face_similarity:.3f}")
        print(f"  Image similarity: {accepted.image_similarity:.3f}")
        print(f"  Overall score: {accepted.overall_score:.3f}")

    evidence = getattr(result, "evidence", None)
    if evidence is not None:
        print("\nEvidence")
        print(f"  Evidence hash: {evidence.evidence_hash}")
        print(f"  Image SHA-256: {evidence.candidate_image_sha256}")

    anchor = getattr(result, "anchor", None)
    if anchor is not None:
        print("\nBlockchain")
        print(f"  Transaction: {anchor.transaction_hash}")
        print(f"  Stored source: {anchor.stored_source}")
        print(f"  Stored timestamp: {anchor.stored_timestamp}")

    verification = getattr(result, "verification", None)
    if verification is not None:
        print("\nOn-chain verification")
        print(f"  Evidence exists: {'yes' if verification.exists else 'no'}")
        print(f"  Hash matches: {'yes' if verification.hash_matches else 'no'}")
        print(f"  Source matches: {'yes' if verification.source_matches else 'no'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="faceid", description="FaceID Verification CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run full face search, validation, and blockchain pipeline")
    run_parser.add_argument("image_path", type=Path, help="Input face image")
    run_parser.add_argument("--results-per-search", type=int, default=30)
    run_parser.add_argument("--max-candidates", type=int, default=50)
    run_parser.add_argument(
        "--accept-score-floor",
        type=float,
        default=None,
        help="Demo-only score floor; requires --allow-score-floor-fallback",
    )
    run_parser.add_argument(
        "--allow-score-floor-fallback",
        action="store_true",
        help="Allow demo fallback when ranking is ambiguous; strict mode is the default",
    )
    run_parser.add_argument("--no-anchor", action="store_true", help="Stop after evidence generation")
    run_parser.add_argument("--no-verify", action="store_true", help="Skip on-chain verification after anchor")
    run_parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a concise human-readable result instead of the full JSON payload",
    )
    run_parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    run_parser.set_defaults(func=cmd_run)

    person1_parser = subparsers.add_parser("person1", help="Run only face detection and reverse search")
    person1_parser.add_argument("image_path", type=Path, help="Input face image")
    person1_parser.add_argument("--results-per-search", type=int, default=30)
    person1_parser.add_argument("--max-candidates", type=int, default=50)
    person1_parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    person1_parser.set_defaults(func=cmd_person1)

    verify_parser = subparsers.add_parser("verify-evidence", help="Verify an existing evidence hash on-chain")
    verify_parser.add_argument("--evidence-hash", default=None, help="Override EVIDENCE_HASH from env")
    verify_parser.add_argument("--expected-source", default=None, help="Optional source check")
    verify_parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    verify_parser.set_defaults(func=cmd_verify_evidence)

    return parser


def cmd_run(args: argparse.Namespace) -> int:
    pipeline = FaceChainPipeline(
        accept_score_floor=args.accept_score_floor,
        allow_score_floor_fallback=args.allow_score_floor_fallback,
    )
    result = pipeline.run(
        args.image_path,
        results_per_search=args.results_per_search,
        max_candidates=args.max_candidates,
        anchor_on_chain=not args.no_anchor,
        verify_on_chain=not args.no_verify,
    )
    if args.summary:
        _print_run_summary(result)
    else:
        _print_payload(result, args.pretty)
    return 0


def cmd_person1(args: argparse.Namespace) -> int:
    pipeline = Person1Pipeline()
    result = pipeline.run(
        args.image_path,
        results_per_search=args.results_per_search,
        max_candidates=args.max_candidates,
    )
    _print_payload(result, args.pretty)
    return 0


def cmd_verify_evidence(args: argparse.Namespace) -> int:
    client = EvidenceRegistryClient()
    evidence_hash = args.evidence_hash
    if not evidence_hash:
        raise BlockchainError("Provide --evidence-hash or set EVIDENCE_HASH")

    result = client.verify_evidence(evidence_hash, expected_source=args.expected_source)
    _print_payload(result, args.pretty)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except BlockchainError as exc:
        parser.exit(status=1, message=f"error: {exc}\n")
    except Exception as exc:
        parser.exit(status=1, message=f"error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
