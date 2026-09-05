// SPDX-License-Identifier: MIT
pragma solidity ^0.8.25;

import {EvidenceCanonicalizer} from "../src/EvidenceCanonicalizer.sol";

contract EvidenceCanonicalizerTest {
    function testCanonicalizeBuildsDeterministicJson() public pure {
        EvidenceCanonicalizer.EvidenceInput memory input = EvidenceCanonicalizer.EvidenceInput({
            schemaVersion: "1.0",
            source: "example.com",
            sourceUrl: "https://example.com/post/123",
            title: "Hello",
            caption: "Caption",
            author: "Alice",
            timestamp: "2026-09-05T06:00:00Z",
            imageSha256: "abc123"
        });

        string memory expected =
            "{\"schema_version\":\"1.0\",\"source\":\"example.com\",\"source_url\":\"https://example.com/post/123\",\"title\":\"Hello\",\"caption\":\"Caption\",\"author\":\"Alice\",\"timestamp\":\"2026-09-05T06:00:00Z\",\"image_sha256\":\"abc123\"}";

        require(
            keccak256(EvidenceCanonicalizer.canonicalize(input)) == keccak256(bytes(expected)),
            "canonical json mismatch"
        );
    }

    function testHashChangesWhenInputChanges() public pure {
        EvidenceCanonicalizer.EvidenceInput memory base = EvidenceCanonicalizer.EvidenceInput({
            schemaVersion: "1.0",
            source: "example.com",
            sourceUrl: "https://example.com/post/123",
            title: "Hello",
            caption: "Caption",
            author: "Alice",
            timestamp: "2026-09-05T06:00:00Z",
            imageSha256: "abc123"
        });

        EvidenceCanonicalizer.EvidenceInput memory changed = EvidenceCanonicalizer.EvidenceInput({
            schemaVersion: base.schemaVersion,
            source: base.source,
            sourceUrl: base.sourceUrl,
            title: base.title,
            caption: "Caption updated",
            author: base.author,
            timestamp: base.timestamp,
            imageSha256: base.imageSha256
        });

        require(EvidenceCanonicalizer.hash(base) != EvidenceCanonicalizer.hash(changed), "hash should change");
    }
}
