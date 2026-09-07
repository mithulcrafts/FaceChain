import sys
import re

files_with_conflicts = [
    "README.md",
    "backend/blockchain.py",
    "backend/pipeline.py",
    "script/VerifyEvidence.s.sol",
    "src/EvidenceRegistry.sol"
]

def resolve_keeping_upstream(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # We want to keep everything between <<<<<<< Updated upstream and =======
    # and discard everything between ======= and >>>>>>> Stashed changes
    
    # regex to match the conflict blocks
    pattern = re.compile(r'<<<<<<< Updated upstream\n(.*?)=======\n.*?>>>>>>> Stashed changes\n', re.DOTALL)
    
    resolved_content = pattern.sub(r'\1', content)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(resolved_content)

for file in files_with_conflicts:
    resolve_keeping_upstream(file)
    print(f"Resolved {file}")
