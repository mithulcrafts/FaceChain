// SPDX-License-Identifier: MIT
pragma solidity ^0.8.25;

import {EvidenceRegistry} from "../src/EvidenceRegistry.sol";

contract EvidenceRegistryTest {
    function testAnchorEvidenceStoresRecord() public {
        EvidenceRegistry registry = new EvidenceRegistry();
        bytes32 evidenceHash = keccak256("facechain-evidence");
        string memory sourceUrl = "https://example.com/post/123";

        uint64 anchoredAt = registry.anchorEvidence(evidenceHash, sourceUrl);
        (bool exists, address submitter, uint64 timestamp, string memory storedSourceUrl) =
            registry.getEvidence(evidenceHash);

        require(exists, "expected anchored evidence");
        require(submitter == address(this), "unexpected submitter");
        require(timestamp == anchoredAt, "timestamp mismatch");
        require(keccak256(bytes(storedSourceUrl)) == keccak256(bytes(sourceUrl)), "sourceUrl mismatch");
        require(registry.verifyEvidence(evidenceHash), "verification failed");
    }

    function testVerifyMissingEvidenceReturnsFalse() public {
        EvidenceRegistry registry = new EvidenceRegistry();
        bytes32 missingHash = keccak256("missing");

        require(!registry.verifyEvidence(missingHash), "unexpected anchor");
        (bool exists, address submitter, uint64 timestamp, string memory sourceUrl) = registry.getEvidence(missingHash);
        require(!exists, "missing evidence should not exist");
        require(submitter == address(0), "submitter should be zero");
        require(timestamp == 0, "timestamp should be zero");
        require(bytes(sourceUrl).length == 0, "sourceUrl should be empty");
    }

    function testAnchorEvidenceWithArchiveStoresRecoveryPointers() public {
        EvidenceRegistry registry = new EvidenceRegistry();
        bytes32 evidenceHash = keccak256("archived-facechain-evidence");
        string memory source = "wikipedia.org";
        string memory sourceUrl = "https://wikipedia.org/wiki/Example";
        string memory archiveUri = "ipfs://bafybeievidence";

        registry.anchorEvidenceWithArchive(evidenceHash, source, sourceUrl, archiveUri);
        (bool exists, address submitter, uint64 timestamp, string memory storedSource, string memory storedUrl, string memory storedArchive) =
            registry.getEvidenceWithArchive(evidenceHash);

        require(exists, "expected archived evidence");
        require(submitter == address(this), "unexpected submitter");
        require(timestamp != 0, "timestamp missing");
        require(keccak256(bytes(storedSource)) == keccak256(bytes(source)), "source mismatch");
        require(keccak256(bytes(storedUrl)) == keccak256(bytes(sourceUrl)), "url mismatch");
        require(keccak256(bytes(storedArchive)) == keccak256(bytes(archiveUri)), "archive mismatch");
    }

    function testDuplicateAnchorReverts() public {
        EvidenceRegistry registry = new EvidenceRegistry();
        bytes32 evidenceHash = keccak256("duplicate");
        string memory sourceUrl = "https://example.com/post/123";

        registry.anchorEvidence(evidenceHash, sourceUrl);

        (bool success, bytes memory data) =
            address(registry).call(abi.encodeCall(EvidenceRegistry.anchorEvidence, (evidenceHash, sourceUrl)));

        require(!success, "duplicate anchor should revert");
        require(data.length >= 4, "missing revert data");

        // forge-lint: disable-next-line(unsafe-typecast)
        bytes4 selector = bytes4(data);
        require(selector == EvidenceRegistry.EvidenceAlreadyAnchored.selector, "wrong revert selector");
    }

    function testEmptySourceReverts() public {
        EvidenceRegistry registry = new EvidenceRegistry();
        bytes32 evidenceHash = keccak256("empty-sourceUrl");

        (bool success, bytes memory data) =
            address(registry).call(abi.encodeCall(EvidenceRegistry.anchorEvidence, (evidenceHash, "")));

        require(!success, "empty sourceUrl should revert");
        require(data.length >= 4, "missing revert data");
        // forge-lint: disable-next-line(unsafe-typecast)
        bytes4 selector = bytes4(data);
        require(selector == EvidenceRegistry.EmptySourceUrl.selector, "wrong revert selector");
    }

    function testEmptyHashReverts() public {
        EvidenceRegistry registry = new EvidenceRegistry();

        (bool success, bytes memory data) =
            address(registry).call(abi.encodeCall(EvidenceRegistry.anchorEvidence, (bytes32(0), "https://example.com/post/123")));

        require(!success, "empty hash should revert");
        require(data.length >= 4, "missing revert data");
        // forge-lint: disable-next-line(unsafe-typecast)
        bytes4 selector = bytes4(data);
        require(selector == EvidenceRegistry.EmptyEvidenceHash.selector, "wrong revert selector");
    }
}
