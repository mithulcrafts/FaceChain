# FaceID_Verification

Foundry slice for FaceChain blockchain anchoring and verification.

## Scope

- Anchor evidence fingerprints on Base Sepolia.
- Store only hash, source, submitter, and timestamp.
- Verify anchored evidence on-chain.
- Fail closed on duplicate, empty source, or empty hash.

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

## Env

Copy `.env.example` to `.env` and fill:

- `BASE_SEPOLIA_RPC_URL`
- `PRIVATE_KEY`
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
