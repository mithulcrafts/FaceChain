// SPDX-License-Identifier: MIT
pragma solidity ^0.8.25;

library EvidenceCanonicalizer {
    struct EvidenceInput {
        string schemaVersion;
        string source;
        string sourceUrl;
        string title;
        string caption;
        string author;
        string timestamp;
        string imageSha256;
    }

    bytes16 private constant _HEX_SYMBOLS = "0123456789abcdef";

    function canonicalize(EvidenceInput memory input) internal pure returns (bytes memory) {
        return abi.encodePacked(
            "{\"schema_version\":",
            _jsonString(input.schemaVersion),
            ",\"source\":",
            _jsonString(input.source),
            ",\"source_url\":",
            _jsonString(input.sourceUrl),
            ",\"title\":",
            _jsonString(input.title),
            ",\"caption\":",
            _jsonString(input.caption),
            ",\"author\":",
            _jsonString(input.author),
            ",\"timestamp\":",
            _jsonString(input.timestamp),
            ",\"image_sha256\":",
            _jsonString(input.imageSha256),
            "}"
        );
    }

    function hash(EvidenceInput memory input) internal pure returns (bytes32) {
        return sha256(canonicalize(input));
    }

    function _jsonString(string memory value) private pure returns (bytes memory) {
        bytes memory raw = bytes(value);
        uint256 escapedLength = 2;

        for (uint256 i = 0; i < raw.length; i++) {
            uint8 b = uint8(raw[i]);
            if (b == 0x22 || b == 0x5c) {
                escapedLength += 2;
            } else if (b == 0x08 || b == 0x09 || b == 0x0a || b == 0x0c || b == 0x0d) {
                escapedLength += 2;
            } else if (b < 0x20) {
                escapedLength += 6;
            } else {
                escapedLength += 1;
            }
        }

        bytes memory out = new bytes(escapedLength);
        uint256 pos = 0;
        out[pos++] = bytes1(uint8(0x22));

        for (uint256 i = 0; i < raw.length; i++) {
            uint8 b = uint8(raw[i]);
            if (b == 0x22) {
                out[pos++] = bytes1(uint8(0x5c));
                out[pos++] = bytes1(uint8(0x22));
            } else if (b == 0x5c) {
                out[pos++] = bytes1(uint8(0x5c));
                out[pos++] = bytes1(uint8(0x5c));
            } else if (b == 0x08) {
                out[pos++] = bytes1(uint8(0x5c));
                out[pos++] = bytes1(uint8(0x62));
            } else if (b == 0x09) {
                out[pos++] = bytes1(uint8(0x5c));
                out[pos++] = bytes1(uint8(0x74));
            } else if (b == 0x0a) {
                out[pos++] = bytes1(uint8(0x5c));
                out[pos++] = bytes1(uint8(0x6e));
            } else if (b == 0x0c) {
                out[pos++] = bytes1(uint8(0x5c));
                out[pos++] = bytes1(uint8(0x66));
            } else if (b == 0x0d) {
                out[pos++] = bytes1(uint8(0x5c));
                out[pos++] = bytes1(uint8(0x72));
            } else if (b < 0x20) {
                out[pos++] = bytes1(uint8(0x5c));
                out[pos++] = bytes1(uint8(0x75));
                out[pos++] = bytes1(uint8(0x30));
                out[pos++] = bytes1(uint8(0x30));
                out[pos++] = _hexChar(b >> 4);
                out[pos++] = _hexChar(b & 0x0f);
            } else {
                out[pos++] = bytes1(b);
            }
        }

        out[pos] = bytes1(uint8(0x22));
        return out;
    }

    function _hexChar(uint8 nibble) private pure returns (bytes1) {
        return _HEX_SYMBOLS[nibble];
    }
}
