# FaceID_Verification

Foundry slice for FaceChain blockchain anchoring and verification.

## Scope

- Anchor evidence fingerprints on Base Sepolia.
- Store only hash, source, submitter, and timestamp.
- Verify anchored evidence on-chain.
- Fail closed on duplicate, empty source, or empty hash.
- Pair search-stage validation with deterministic evidence hashing.
- Keep off-chain data minimal. Save only what is needed to prove provenance.

## Contract

- `src/EvidenceRegistry.sol`

## Tests

```bash
forge test
```

## Deploy

Base Sepolia chain ID is `84532` and Base Sepolia RPC is `https://sepolia.base.org`. Use your own funded deployer key.

```bash
forge script script/DeployEvidenceRegistry.s.sol:DeployEvidenceRegistry \
  --rpc-url "$BASE_SEPOLIA_RPC_URL" \
  --private-key "$PRIVATE_KEY" \
  --broadcast \
  --verify
```

## Full pipeline

The backend pipeline is:

1. Face detect and embed input image.
2. Run genuine reverse-image search with SerpApi Google Lens on:
   - full input image
   - face crop
3. Merge and deduplicate candidates.
4. Validate top candidates with:
   - face embedding similarity
   - image similarity
   - source consistency
   - completeness
5. Canonicalize accepted evidence.
6. Compute `sha256` hash.
7. Anchor hash on-chain.
8. Re-read and verify on-chain record.

Main orchestrator:

- `backend.pipeline.FaceChainPipeline`

Run it from Python with your configured env:

```python
from pathlib import Path
from backend.pipeline import FaceChainPipeline

pipeline = FaceChainPipeline()
result = pipeline.run(Path("input.jpg"))
print(result.status)
print(result.reason)
```

## CLI

Run the project from command line:

```bash
python -m backend.cli run input.jpg --pretty --no-verify
```

Other commands:

```bash
python -m backend.cli person1 input.jpg --pretty
python -m backend.cli verify-evidence --evidence-hash "$EVIDENCE_HASH" --pretty
```

Flags:

- `run` does full search + validation + blockchain
- `--no-anchor` stops after evidence generation
- `--no-verify` anchors only
- `person1` runs only face processing + search
- `verify-evidence` reads already anchored evidence from chain

## Verify existing deployment

Foundry verification supports Etherscan-compatible explorers, including BaseScan. Set `ETHERSCAN_API_KEY`.

```bash
forge verify-contract \
  --chain 84532 \
  --verifier etherscan \
  --etherscan-api-key "$ETHERSCAN_API_KEY" \
  <DEPLOYED_ADDRESS> \
  src/EvidenceRegistry.sol:EvidenceRegistry
```

## Read evidence

```bash
cast call <DEPLOYED_ADDRESS> "verifyEvidence(bytes32)(bool)" <EVIDENCE_HASH> \
  --rpc-url "$BASE_SEPOLIA_RPC_URL"

cast call <DEPLOYED_ADDRESS> "getEvidence(bytes32)(bool,address,uint64,string)" <EVIDENCE_HASH> \
  --rpc-url "$BASE_SEPOLIA_RPC_URL"
```

## Verify evidence

The verification script rebuilds canonical JSON bytes from the upstream evidence fields, hashes them with `sha256`, checks that result against `EVIDENCE_HASH`, then queries the registry.

```bash
forge script script/VerifyEvidence.s.sol:VerifyEvidence \
  --fork-url "$BASE_SEPOLIA_RPC_URL" \
  --sig run
```

Required env:

- `EVIDENCE_REGISTRY`
- `EVIDENCE_HASH`
- `EVIDENCE_SCHEMA_VERSION`
- `EVIDENCE_SOURCE`
- `EVIDENCE_SOURCE_URL`
- `EVIDENCE_TITLE`
- `EVIDENCE_CAPTION`
- `EVIDENCE_AUTHOR`
- `EVIDENCE_TIMESTAMP`
- `EVIDENCE_IMAGE_SHA256`
- `BASE_SEPOLIA_RPC_URL`
- `PRIVATE_KEY`
- `CHAIN_ID`

## Env

Copy `.env.example` to `.env` and fill:

- `SERPAPI_API_KEY`
- `BASE_SEPOLIA_RPC_URL`
- `PRIVATE_KEY`
- `CHAIN_ID`
- `ETHERSCAN_API_KEY`
- `EVIDENCE_REGISTRY`
- `EVIDENCE_HASH`
- `EVIDENCE_SCHEMA_VERSION`
- `EVIDENCE_SOURCE`
- `EVIDENCE_SOURCE_URL`
- `EVIDENCE_TITLE`
- `EVIDENCE_CAPTION`
- `EVIDENCE_AUTHOR`
- `EVIDENCE_TIMESTAMP`
- `EVIDENCE_IMAGE_SHA256`

## Notes

- The upstream pipeline should canonicalize evidence off-chain, then pass the final `bytes32` hash here.
- Verification script rebuilds the canonical bytes, hashes them, and checks on-chain anchoring.
- Privacy stays intact because chain stores no face image, no face embedding, and no raw social post content.
- Only deterministic proof fields go on-chain.
