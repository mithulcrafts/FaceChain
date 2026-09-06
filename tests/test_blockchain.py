"""
Unit tests for Foundry cast blockchain client.
"""

import unittest
from subprocess import CompletedProcess
from unittest.mock import patch

from backend.blockchain import BlockchainError, EvidenceRegistryClient


class TestBlockchainClient(unittest.TestCase):
    @patch("subprocess.run")
    def test_anchor_evidence_runs_cast_and_parses_output(self, mock_run):
        mock_run.side_effect = [
            CompletedProcess(args=[], returncode=0, stdout="0x" + "1" * 64 + "\n", stderr=""),
            CompletedProcess(args=[], returncode=0, stdout="status 1\n", stderr=""),
            CompletedProcess(
                args=[],
                returncode=0,
                stdout='(true, 0x2222222222222222222222222222222222222222, 1700000000, "example.com")\n',
                stderr="",
            ),
        ]

        client = EvidenceRegistryClient(
            registry_address="0x1234567890abcdef1234567890abcdef12345678",
            rpc_url="http://127.0.0.1:8545",
            private_key="0x" + "2" * 64,
            chain_id=84532,
        )
        result = client.anchor_evidence("0x" + "a" * 64, "example.com")

        self.assertEqual(result.transaction_hash, "0x" + "1" * 64)
        self.assertEqual(result.stored_source, "example.com")
        self.assertEqual(result.stored_timestamp, 1700000000)
        self.assertEqual(mock_run.call_count, 3)
        receipt_cmd = mock_run.call_args_list[1].args[0]
        self.assertIn("receipt", receipt_cmd)
        self.assertNotIn("--chain", receipt_cmd)

    @patch("subprocess.run")
    def test_anchor_rejects_reverted_transaction(self, mock_run):
        mock_run.side_effect = [
            CompletedProcess(args=[], returncode=0, stdout="0x" + "1" * 64 + "\n", stderr=""),
            CompletedProcess(args=[], returncode=0, stdout="status 0\n", stderr=""),
        ]

        client = EvidenceRegistryClient(
            registry_address="0x1234567890abcdef1234567890abcdef12345678",
            rpc_url="http://127.0.0.1:8545",
            private_key="0x" + "2" * 64,
            chain_id=84532,
        )
        with self.assertRaisesRegex(BlockchainError, "Anchor transaction reverted"):
            client.anchor_evidence("0x" + "a" * 64, "example.com")
        self.assertEqual(mock_run.call_count, 2)

    @patch("subprocess.run")
    def test_verify_evidence_parses_registry_output(self, mock_run):
        mock_run.side_effect = [
            CompletedProcess(args=[], returncode=0, stdout="true\n", stderr=""),
            CompletedProcess(
                args=[],
                returncode=0,
                stdout='(true, 0x2222222222222222222222222222222222222222, 1700000000, "example.com")\n',
                stderr=""),
        ]

        client = EvidenceRegistryClient(
            registry_address="0x1234567890abcdef1234567890abcdef12345678",
            rpc_url="http://127.0.0.1:8545",
            private_key="0x" + "2" * 64,
            chain_id=84532,
        )
        result = client.verify_evidence("0x" + "a" * 64, expected_source="example.com")

        self.assertTrue(result.anchored)
        self.assertTrue(result.exists)
        self.assertTrue(result.source_matches)
        self.assertTrue(result.hash_matches)
        self.assertEqual(result.submitter, "0x2222222222222222222222222222222222222222")
        self.assertEqual(mock_run.call_count, 2)

    @patch("subprocess.run")
    def test_anchor_evidence_handles_already_anchored(self, mock_run):
        mock_run.side_effect = [
            CompletedProcess(args=[], returncode=1, stdout="", stderr="Error: EvidenceAlreadyAnchored(0xabc)"),
            CompletedProcess(
                args=[],
                returncode=0,
                stdout='(true, 0x2222222222222222222222222222222222222222, 1700000000, "example.com")\n',
                stderr="",
            ),
        ]

        client = EvidenceRegistryClient(
            registry_address="0x1234567890abcdef1234567890abcdef12345678",
            rpc_url="http://127.0.0.1:8545",
            private_key="0x" + "2" * 64,
            chain_id=84532,
        )
        result = client.anchor_evidence("0x" + "a" * 64, "example.com")

        self.assertEqual(result.transaction_hash, "already_anchored")
        self.assertEqual(result.stored_source, "example.com")
        self.assertEqual(mock_run.call_count, 2)

    def test_parse_tuple_handles_multiline_cast_output(self):
        text = 'true\n0x335E58172fC8895Bc380471972A22Ea921152F6d\n1788714400 [1.788e9]\n"hindustan times"'
        parsed = __import__("backend.blockchain", fromlist=["_parse_tuple"])._parse_tuple(text)
        self.assertEqual(
            parsed,
            (
                "true",
                "0x335E58172fC8895Bc380471972A22Ea921152F6d",
                "1788714400",
                "hindustan times",
            ),
        )
