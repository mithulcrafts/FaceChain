"""
Unit tests for FaceID CLI.
"""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.cli import build_parser, cmd_run, cmd_verify_evidence


class TestCLI(unittest.TestCase):
    def test_parser_builds_run_command(self):
        parser = build_parser()
        args = parser.parse_args(["run", "input.jpg", "--no-anchor"])

        self.assertEqual(args.command, "run")
        self.assertEqual(args.image_path, Path("input.jpg"))
        self.assertTrue(args.no_anchor)
        self.assertIsNone(args.accept_score_floor)
        self.assertFalse(args.allow_score_floor_fallback)

    @patch("backend.cli.FaceChainPipeline")
    def test_run_command_prints_json(self, mock_pipeline_cls):
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = MagicMock(
            model_dump=lambda: {"status": "rejected", "reason": "no candidate"}
        )
        mock_pipeline_cls.return_value = mock_pipeline

        args = build_parser().parse_args(["run", "input.jpg", "--no-anchor"])
        with patch("builtins.print") as mock_print:
            exit_code = cmd_run(args)

        self.assertEqual(exit_code, 0)
        mock_pipeline.run.assert_called_once()
        printed = mock_print.call_args[0][0]
        self.assertEqual(json.loads(printed), {"status": "rejected", "reason": "no candidate"})

    @patch("backend.cli.FaceChainPipeline")
    def test_run_command_prints_human_summary(self, mock_pipeline_cls):
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = MagicMock(
            status="verified",
            reason="anchored and verified",
            accepted_candidate=None,
            evidence=None,
            anchor=None,
            verification=None,
        )
        mock_pipeline_cls.return_value = mock_pipeline

        args = build_parser().parse_args(["run", "input.jpg", "--summary"])
        with patch("builtins.print") as mock_print:
            exit_code = cmd_run(args)

        self.assertEqual(exit_code, 0)
        output = "\n".join(str(call.args[0]) for call in mock_print.call_args_list)
        self.assertIn("FaceID Verification", output)
        self.assertIn("Status: VERIFIED", output)
        self.assertIn("anchored and verified", output)

    @patch("backend.cli.EvidenceRegistryClient")
    def test_verify_evidence_command_uses_read_only_client(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.verify_evidence.return_value = MagicMock(
            model_dump=lambda: {
                "evidence_hash": "0x" + "a" * 64,
                "anchored": True,
                "exists": True,
                "submitter": "0x" + "1" * 40,
                "timestamp": 1,
                "source": "example.com",
                "source_matches": True,
                "hash_matches": True,
            }
        )
        mock_client_cls.return_value = mock_client

        args = build_parser().parse_args(
            ["verify-evidence", "--evidence-hash", "0x" + "a" * 64]
        )
        with patch("builtins.print") as mock_print:
            exit_code = cmd_verify_evidence(args)

        self.assertEqual(exit_code, 0)
        mock_client.verify_evidence.assert_called_once()
        self.assertIn("anchored", json.loads(mock_print.call_args[0][0]))
