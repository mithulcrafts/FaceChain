// SPDX-License-Identifier: MIT
pragma solidity ^0.8.25;

contract EvidenceRegistry {
    struct EvidenceRecord {
        bool exists;
        address submitter;
        uint64 timestamp;
        string source;
    }

    mapping(bytes32 => EvidenceRecord) private _records;

    event EvidenceAnchored(bytes32 indexed evidenceHash, uint64 timestamp, string source);

    error EmptyEvidenceHash();
    error EmptySource();
    error EvidenceAlreadyAnchored(bytes32 evidenceHash);

    function anchorEvidence(bytes32 evidenceHash, string calldata source) external returns (uint64 timestamp) {
        if (evidenceHash == bytes32(0)) {
            revert EmptyEvidenceHash();
        }
        if (bytes(source).length == 0) {
            revert EmptySource();
        }

        EvidenceRecord storage record = _records[evidenceHash];
        if (record.exists) {
            revert EvidenceAlreadyAnchored(evidenceHash);
        }

        timestamp = uint64(block.timestamp);
        _records[evidenceHash] = EvidenceRecord({
            exists: true,
            submitter: msg.sender,
            timestamp: timestamp,
            source: source
        });

        emit EvidenceAnchored(evidenceHash, timestamp, source);
    }

    function verifyEvidence(bytes32 evidenceHash) external view returns (bool anchored) {
        return _records[evidenceHash].exists;
    }

    function getEvidence(bytes32 evidenceHash)
        external
        view
        returns (bool exists, address submitter, uint64 timestamp, string memory source)
    {
        EvidenceRecord storage record = _records[evidenceHash];
        return (record.exists, record.submitter, record.timestamp, record.source);
    }
}
