import json
import hashlib

def canonicalize_and_hash(evidence_data):
    """
    Takes an evidence dictionary, creates a deterministic JSON string,
    and returns its SHA-256 hash (the evidence fingerprint).
    """
    if not isinstance(evidence_data, dict):
        raise TypeError(f"Evidence data must be a dictionary. Received: {type(evidence_data)}")
    
    # 1. Canonicalize the JSON
    # - sort_keys=True ensures the keys are always alphabetical
    # - separators=(',', ':') removes all whitespace between keys and values
    # - ensure_ascii=False keeps special characters intact
    canonical_string = json.dumps(
        evidence_data,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False
    )
    
    # 2. Convert the string to bytes (required for hashing)
    encoded_string = canonical_string.encode('utf-8')
    
    # 3. Generate the SHA-256 hash
    evidence_hash = hashlib.sha256(encoded_string).hexdigest()
    
    # Prefix it with '0x' because smart contracts expect hex strings to look like this
    return f"0x{evidence_hash}"

if __name__ == "__main__":
    mock_evidence = {
        "url": "https://x.com/elonmusk/status/123",
        "title": "A great day!",
        "source": "Twitter",
        "timestamp": "1715000000"
    }
    
    print("--- Starting Canonicalization Test ---")
    fingerprint = canonicalize_and_hash(mock_evidence)
    print(f"Mock Evidence: {mock_evidence}")
    print(f"Canonical Hash Fingerprint: {fingerprint}")
