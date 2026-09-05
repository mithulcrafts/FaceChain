// SPDX-License-Identifier: MIT
pragma solidity ^0.8.25;

import {EvidenceRegistry} from "../src/EvidenceRegistry.sol";

contract EvidenceRegistryTest {
    function testAnchorEvidenceStoresRecord() public {
        EvidenceRegistry registry = new EvidenceRegistry();
        bytes32 evidenceHash = keccak256("facechain-evidence");
        string memory source = "example.com";

        uint64 anchoredAt = registry.anchorEvidence(evidenceHash, source);
        (bool exists, address submitter, uint64 timestamp, string memory storedSource) =
            registry.getEvidence(evidenceHash);

        require(exists, "expected anchored evidence");
        require(submitter == address(this), "unexpected submitter");
        require(timestamp == anchoredAt, "timestamp mismatch");
        require(keccak256(bytes(storedSource)) == keccak256(bytes(source)), "source mismatch");
        require(registry.verifyEvidence(evidenceHash), "verification failed");
    }

    function testVerifyMissingEvidenceReturnsFalse() public {
        EvidenceRegistry registry = new EvidenceRegistry();
        bytes32 missingHash = keccak256("missing");

        require(!registry.verifyEvidence(missingHash), "unexpected anchor");
        (bool exists, address submitter, uint64 timestamp, string memory source) = registry.getEvidence(missingHash);
        require(!exists, "missing evidence should not exist");
        require(submitter == address(0), "submitter should be zero");
        require(timestamp == 0, "timestamp should be zero");
        require(bytes(source).length == 0, "source should be empty");
    }

    function testDuplicateAnchorReverts() public {
        EvidenceRegistry registry = new EvidenceRegistry();
        bytes32 evidenceHash = keccak256("duplicate");
        string memory source = "example.com";

        registry.anchorEvidence(evidenceHash, source);

        (bool success, bytes memory data) =
            address(registry).call(abi.encodeCall(EvidenceRegistry.anchorEvidence, (evidenceHash, source)));

        require(!success, "duplicate anchor should revert");
        require(data.length >= 4, "missing revert data");

        // forge-lint: disable-next-line(unsafe-typecast)
        bytes4 selector = bytes4(data);
        require(selector == EvidenceRegistry.EvidenceAlreadyAnchored.selector, "wrong revert selector");
    }

    function testEmptySourceReverts() public {
        EvidenceRegistry registry = new EvidenceRegistry();
        bytes32 evidenceHash = keccak256("empty-source");

        (bool success, bytes memory data) =
            address(registry).call(abi.encodeCall(EvidenceRegistry.anchorEvidence, (evidenceHash, "")));

        require(!success, "empty source should revert");
        require(data.length >= 4, "missing revert data");
        // forge-lint: disable-next-line(unsafe-typecast)
        bytes4 selector = bytes4(data);
        require(selector == EvidenceRegistry.EmptySource.selector, "wrong revert selector");
    }

    function testEmptyHashReverts() public {
        EvidenceRegistry registry = new EvidenceRegistry();

        (bool success, bytes memory data) =
            address(registry).call(abi.encodeCall(EvidenceRegistry.anchorEvidence, (bytes32(0), "example.com")));

        require(!success, "empty hash should revert");
        require(data.length >= 4, "missing revert data");
        // forge-lint: disable-next-line(unsafe-typecast)
        bytes4 selector = bytes4(data);
        require(selector == EvidenceRegistry.EmptyEvidenceHash.selector, "wrong revert selector");
    }
}
