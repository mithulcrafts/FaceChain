import sys
sys.path.insert(0, ".")
from verify import rebuild_evidence_hash
import json
import glob

ev_files = glob.glob("evidence/evidence_*.json")
with open(ev_files[0], "r") as f:
    evidence_data = json.load(f)

record_data = evidence_data.get("record", {})
canonical_json, new_evidence_hash = rebuild_evidence_hash(
    source_url=record_data.get("source_url", ""),
    image_sha256=record_data.get("image_sha256", ""),
    title=record_data.get("title", ""),
    caption=record_data.get("caption", ""),
    author=record_data.get("author", ""),
    timestamp=record_data.get("timestamp", ""),
    source=record_data.get("source", ""),
)

print("original hash:", evidence_data["evidence_hash"])
print("new hash:", new_evidence_hash)
print("match:", evidence_data["evidence_hash"].lower() == new_evidence_hash.lower())
print("canonical original:", evidence_data["canonical_json"])
print("canonical new:", canonical_json)
