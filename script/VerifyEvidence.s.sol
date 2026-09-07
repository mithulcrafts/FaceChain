// SPDX-License-Identifier: MIT
pragma solidity ^0.8.25;

import {EvidenceCanonicalizer} from "../src/EvidenceCanonicalizer.sol";
import {EvidenceRegistry} from "../src/EvidenceRegistry.sol";
import {ScriptBase} from "./ScriptBase.sol";

contract VerifyEvidence is ScriptBase {
    event VerificationResult(bytes32 indexed evidenceHash, bool anchored, uint64 timestamp, string sourceUrl);

    function run() external returns (bytes32 evidenceHash, bool anchored, uint64 timestamp, string memory sourceUrl) {
        EvidenceCanonicalizer.EvidenceInput memory input = EvidenceCanonicalizer.EvidenceInput({
            schemaVersion: vm.envString("EVIDENCE_SCHEMA_VERSION"),
            source: vm.envString("EVIDENCE_SOURCE"),
            sourceUrl: vm.envString("EVIDENCE_SOURCE_URL"),
            title: vm.envString("EVIDENCE_TITLE"),
            caption: vm.envString("EVIDENCE_CAPTION"),
            author: vm.envString("EVIDENCE_AUTHOR"),
            timestamp: vm.envString("EVIDENCE_TIMESTAMP"),
            imageSha256: vm.envString("EVIDENCE_IMAGE_SHA256")
        });

        bytes32 computedHash = EvidenceCanonicalizer.hash(input);
        bytes32 declaredHash = vm.envBytes32("EVIDENCE_HASH");
        require(computedHash == declaredHash, "EVIDENCE_HASH mismatch");

        address registryAddress = vm.envAddress("EVIDENCE_REGISTRY");
        EvidenceRegistry registry = EvidenceRegistry(registryAddress);

        anchored = registry.verifyEvidence(declaredHash);
        (bool exists, address submitter, uint64 storedTimestamp, string memory storedSource, string memory storedSourceUrl, string memory storedArchiveUri) =
            registry.getEvidenceWithArchive(declaredHash);
        require(exists, "NO_ANCHOR_FOUND");
        require(submitter != address(0), "NO_SUBMITTER");
        require(storedTimestamp != 0, "NO_TIMESTAMP");
        require(keccak256(bytes(storedSource)) == keccak256(bytes(input.source)), "SOURCE_MISMATCH");
        require(keccak256(bytes(storedSourceUrl)) == keccak256(bytes(input.sourceUrl)), "SOURCE_URL_MISMATCH");
        require(bytes(storedArchiveUri).length != 0, "ARCHIVE_MISSING");

        emit VerificationResult(declaredHash, anchored, storedTimestamp, storedSourceUrl);
        return (declaredHash, anchored, storedTimestamp, storedSourceUrl);
    }
}
