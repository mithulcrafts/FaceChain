// SPDX-License-Identifier: MIT
pragma solidity ^0.8.25;

contract EvidenceRegistry {
    struct EvidenceRecord {
        bool exists;
        address submitter;
        uint64 timestamp;
        string source;
        string sourceUrl;
        string archiveUri;
    }

    mapping(bytes32 => EvidenceRecord) private _records;

    event EvidenceAnchored(
        bytes32 indexed evidenceHash,
        uint64 timestamp,
        string source,
        string sourceUrl,
        string archiveUri
    );

    error EmptyEvidenceHash();
    error EmptySource();
    error EmptySourceUrl();
    error EmptyArchiveUri();
    error EvidenceAlreadyAnchored(bytes32 evidenceHash);

    function anchorEvidence(bytes32 evidenceHash, string calldata source) external returns (uint64 timestamp) {
        return _anchorEvidence(evidenceHash, source, "", "");
    }

    function anchorEvidenceWithArchive(
        bytes32 evidenceHash,
        string calldata source,
        string calldata sourceUrl,
        string calldata archiveUri
    ) external returns (uint64 timestamp) {
        if (bytes(sourceUrl).length == 0) revert EmptySourceUrl();
        if (bytes(archiveUri).length == 0) revert EmptyArchiveUri();
        return _anchorEvidence(evidenceHash, source, sourceUrl, archiveUri);
    }

    function _anchorEvidence(
        bytes32 evidenceHash,
        string calldata source,
        string memory sourceUrl,
        string memory archiveUri
    ) internal returns (uint64 timestamp) {
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
            source: source,
            sourceUrl: sourceUrl,
            archiveUri: archiveUri
        });

        emit EvidenceAnchored(evidenceHash, timestamp, source, sourceUrl, archiveUri);
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

    function getEvidenceWithArchive(bytes32 evidenceHash)
        external
        view
        returns (
            bool exists,
            address submitter,
            uint64 timestamp,
            string memory source,
            string memory sourceUrl,
            string memory archiveUri
        )
    {
        EvidenceRecord storage record = _records[evidenceHash];
        return (record.exists, record.submitter, record.timestamp, record.source, record.sourceUrl, record.archiveUri);
    }
}
