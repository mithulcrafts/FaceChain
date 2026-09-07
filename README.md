#  FaceChain — Face to Blockchain Verification Pipeline | HH Goa 2026

![Pipeline Status](https://img.shields.io/badge/Pipeline-Production_Ready-brightgreen)
![Network](https://img.shields.io/badge/Network-Base_Sepolia_(L2)-blue)
![AI Engine](https://img.shields.io/badge/AI_Engine-InsightFace_ArcFace-purple)
![Smart Contract](https://img.shields.io/badge/Smart_Contract-Solidity_0.8.25-orange)
![Toolchain](https://img.shields.io/badge/Toolchain-Foundry-red)

**A production-grade intelligence pipeline that takes a face scan, finds matching content across the web, mathematically verifies the identity, and anchors a tamper-proof cryptographic fingerprint to an Ethereum Layer 2 blockchain — fully automated, end to end.**

> Built for **Hacker House Goa 2026** — Shortlisting Task #3: Face Identification & Blockchain Verification.

---

## Table of Contents

- [The Vision](#-the-vision-why-we-built-it-this-way)
- [System Architecture](#-system-architecture)
- [How It Works (Step by Step)](#-how-it-works-step-by-step)
- [Engineering Decisions & Justifications](#-engineering-decisions--justifications)
- [Fault-Tolerant Design](#-fault-tolerant-design)
- [Project Structure](#-project-structure)
- [How to Run](#-how-to-run)
- [Smart Contract](#-smart-contract)
- [Running the Tests](#-running-the-tests)
- [Known Limitations](#-known-limitations)
- [Team](#-team)

---

##  The Vision: Why We Built It This Way

The task was straightforward: *take a face, find it online, put it on a blockchain.*

The easy route would be to call one API, grab the first URL, and dump it into a testnet. That would work, but it would be fragile, unreliable, and trivially breakable.

**We took a fundamentally different approach.** We engineered a multi-layered system built on three principles:

1. **Never trust a single source.** We run *two* independent reverse image searches (full image + cropped face) and merge the results, so we catch matches that a single search would miss.
2. **Mathematically verify, don't assume.** Search engines make mistakes. Instead of blindly trusting the top Google result, we download every candidate image, extract facial embeddings, and calculate mathematical similarity scores. A candidate only passes if it clears strict thresholds across *four* independent metrics.
3. **Hash the evidence, not just the URL.** A URL can be changed. An image can be swapped. We canonicalize the entire evidence object into a deterministic JSON string and compute its SHA-256 hash *before* anchoring on-chain. If a single character changes tomorrow, verification fails. That is real tamper-proofing.

---

##  System Architecture

The pipeline is split into three decoupled layers, each with a single responsibility:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        INPUT: Face Image                            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  LAYER 1: DISCOVERY ENGINE                               │
│                                                                      │
│  Face Detection ──► 512-D Embedding ──► Dual Reverse Image Search    │
│  (InsightFace)       (ArcFace)          (SerpApi Google Lens)        │
│                                                                      │
│  Output: List of candidate URLs with metadata                        │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  LAYER 2: AI VALIDATION ENGINE                      │
│                                                                      │
│  Download Candidates ──► Face Similarity  ──► Image Similarity       │
│                          (Cosine Distance)    (HSV Histogram)        │
│                                                                      │
│  ──► Source Consistency ──► Completeness ──► Weighted Overall Score   │
│                                                                      │
│  ──► Margin Enforcement ──► Accept / Reject                          │
│                                                                      │
│  Output: Best verified candidate + SHA-256 of downloaded image       │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  LAYER 3: BLOCKCHAIN VAULT                               │
│                                                                      │
│  Canonicalize Evidence ──► SHA-256 Hash ──► Anchor on Base Sepolia   │
│  (Deterministic JSON)                       (EvidenceRegistry.sol)   │
│                                                                      │
│  ──► On-Chain Verification (re-read and confirm)                     │
│                                                                      │
│  Output: Transaction hash + verified on-chain record                 │
└──────────────────────────────────────────────────────────────────────┘
```

Each layer is independently testable, independently deployable, and communicates through clean data models (Pydantic schemas). If any layer fails, the pipeline stops cleanly with a clear error message — it never silently produces a wrong result.

---

##  How It Works (Step by Step)

Here is exactly what happens when you run the pipeline with a face image:

### Step 1 — Face Detection & Embedding
The input image is passed to **InsightFace** (with an OpenCV Haar Cascade fallback). It detects the face, aligns it, and extracts a **512-dimensional ArcFace embedding vector** — a mathematical fingerprint of the face geometry.

### Step 2 — Dual Reverse Image Search
Two independent searches are fired through **SerpApi Google Lens**:
- **Full-image search** — finds pages containing the full photo.
- **Face-crop search** — crops just the face and searches again, catching profile pictures and headshots the full search might miss.

Results are **merged and deduplicated** by normalized URL. Candidates found by both searches are flagged as higher confidence.

### Step 3 — Multi-Factor Candidate Validation
Each candidate is scored across **four independent metrics**:

| Metric | Weight | What it measures |
|--------|--------|-----------------|
| **Face Similarity** | 55% | Cosine similarity between 512-D ArcFace embeddings of input vs. candidate |
| **Image Similarity** | 20% | HSV histogram correlation between the two images |
| **Source Consistency** | 15% | Whether the candidate's claimed source domain matches the actual URL |
| **Completeness** | 10% | How much metadata the candidate provides (title, snippet, source, URL) |

A candidate is only accepted if it passes **all three thresholds** (face, image, and overall score) AND beats the runner-up by a minimum **confidence margin** to prevent ambiguous matches.

### Step 4 — Evidence Canonicalization & Hashing
The accepted candidate's metadata is assembled into an `EvidenceRecord` with a fixed field ordering. This record is serialized to JSON using **deterministic canonicalization** (sorted keys, no whitespace, UTF-8 encoding) and hashed with **SHA-256**.

This means: same evidence data → same JSON string → same hash. Always. On any machine, in any language.

### Step 5 — Blockchain Anchoring
The `bytes32` evidence hash and source string are sent to the `EvidenceRegistry` smart contract on **Base Sepolia** via Foundry's `cast send`. The contract stores the hash, submitter address, timestamp, and source. It emits an `EvidenceAnchored` event and rejects duplicates.

### Step 6 — On-Chain Verification
Immediately after anchoring, the pipeline reads the record back from the blockchain using `cast call` and confirms that the stored data matches what was sent. This proves the record is genuinely on-chain and not just assumed from a successful broadcast.

---

##  Engineering Decisions & Justifications

### Why InsightFace with ArcFace (not face_recognition / dlib)?
The commonly used `face_recognition` library produces 128-D embeddings. **InsightFace ArcFace produces 512-D embeddings**, which gives us 4x the feature resolution for distinguishing between similar-looking faces. ArcFace also uses angular margin loss during training, which means it optimizes specifically for *separating* identities — exactly what we need.

### Why Dual Search (Full Image + Face Crop)?
A single reverse image search can miss results. If the input is a group photo, the full-image search finds the group photo online, but a face-crop search finds that person's individual profile pictures. By running both and merging, we dramatically increase recall without sacrificing precision.

### Why Cosine Similarity (not Euclidean Distance)?
For high-dimensional vectors like 512-D embeddings, cosine similarity is more robust because it measures the *angle* between vectors, not the magnitude. Two photos of the same person under different lighting will have different magnitudes but similar angles.

### Why Canonicalization Before Hashing?
Two JSON strings with identical data but different formatting produce completely different SHA-256 hashes. By enforcing a canonical form (alphabetically sorted keys, no whitespace, UTF-8), we guarantee that the same evidence always produces the same hash — regardless of which machine or language generates it. This is critical for independent verification.

### Why Base Sepolia (not Ethereum Mainnet)?
Base is an Ethereum Layer 2 rollup built on the OP Stack. It inherits Ethereum's security guarantees but with near-zero gas fees and fast block times. For a hackathon demo, this means we can anchor evidence instantly without paying real money, while the architecture is identical to a mainnet deployment.

### Why Foundry `cast` (not Web3.py)?
Foundry's `cast` is a battle-tested CLI tool that speaks directly to EVM nodes. Using `cast` instead of a Python Web3 library means zero additional Python dependencies for blockchain interactions, and the same commands work identically in CI/CD pipelines, shell scripts, and the Python orchestrator.

---

##  Fault-Tolerant Design

This pipeline was built to survive the wild internet:

| Feature | Why it matters |
|---------|---------------|
| **MIME-Type Validation** | The downloader checks `Content-Type` headers before saving. If a URL returns HTML (like a CAPTCHA page) instead of an image, it is rejected immediately — preventing the ML engine from crashing on corrupt input. |
| **Strict Timeout Enforcement** | Every HTTP request has a 10-20 second timeout. A broken link will never freeze the pipeline. |
| **Automatic Image Compression** | Images exceeding SerpApi's 500KB upload limit are automatically resized and compressed via PIL before upload. |
| **Duplicate Anchoring Guard** | The smart contract reverts with `EvidenceAlreadyAnchored` if the same hash is submitted twice. The Python client catches this gracefully and reuses the existing record. |
| **Receipt Polling with Retry** | After broadcasting a transaction, the pipeline polls the RPC node up to 5 times with 1-second delays to confirm the evidence was actually mined — not just broadcast. |
| **Graceful Fallback** | If InsightFace fails to initialize, the face processor falls back to OpenCV's Haar Cascade detector. The pipeline degrades gracefully instead of crashing. |
| **Privacy by Design** | No face image, no embedding vector, and no raw social media content is ever stored on-chain. Only the deterministic SHA-256 hash and a source reference go on-chain. |

---

## 📁 Project Structure

```
FaceID_Verification/
│
├── main.py                          # Rich terminal UI entry point (demo showcase)
├── test_search.py                   # Person 1 integration test (mock + live modes)
│
├── backend/
│   ├── __init__.py                  # Package exports
│   ├── cli.py                       # CLI entry point (JSON output)
│   ├── pipeline.py                  # Master orchestrator (Person1Pipeline + FaceChainPipeline)
│   ├── validation.py                # AI candidate validation & ranking
│   ├── evidence.py                  # Canonical JSON serialization + SHA-256 hashing
│   ├── blockchain.py                # EvidenceRegistry client (via Foundry cast)
│   ├── .env.example                 # Environment variable template
│   │
│   ├── face/                        # Face processing module
│   │   ├── processor.py             # InsightFace detection + 512-D ArcFace embeddings
│   │   ├── models.py                # FaceDetectionResult data model
│   │   └── exceptions.py            # Custom exceptions
│   │
│   └── search/                      # Web search module
│       ├── serpapi_lens.py           # SerpApi Google Lens reverse image search
│       ├── base.py                   # Abstract search provider interface
│       ├── models.py                 # CandidateResult data model
│       └── exceptions.py            # Custom exceptions
│
├── src/
│   └── EvidenceRegistry.sol         # Solidity smart contract (deployed on Base Sepolia)
│
├── script/
│   └── DeployEvidenceRegistry.s.sol # Foundry deployment script
│
├── test/                            # Solidity unit tests (forge test)
├── tests/                           # Python unit tests (pytest)
│
├── foundry.toml                     # Foundry configuration (Base Sepolia)
└── .gitignore
```

---

## 💻 How to Run

### Prerequisites

- **Python 3.10+**
- **Foundry** (`forge`, `cast`) — [Install Foundry](https://book.getfoundry.sh/getting-started/installation)
- **SerpApi API Key** — [Get one here](https://serpapi.com/)

### 1. Clone the Repository

```bash
git clone https://github.com/mithulcrafts/FaceID_Verification.git
cd FaceID_Verification
```

### 2. Install Python Dependencies

```bash
pip install requests opencv-python numpy insightface onnxruntime pydantic rich
```

### 3. Configure Environment Variables

Copy the example and fill in your keys:

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

```env
SERPAPI_API_KEY=your_serpapi_key_here
BASE_SEPOLIA_RPC_URL=https://sepolia.base.org
PRIVATE_KEY=your_wallet_private_key
CHAIN_ID=84532
EVIDENCE_REGISTRY=your_deployed_contract_address
```

> **Minimum requirement:** Only `SERPAPI_API_KEY` is needed to run search + validation. Blockchain keys are only needed for on-chain anchoring.

### 4. Run the Pipeline

There are **two ways** to run the pipeline. Both execute the same underlying `FaceChainPipeline`:

#### Option A: Rich Terminal UI (Recommended for Demo)

```bash
python main.py path/to/face.jpg --no-anchor
```

This produces a colorful, stage-by-stage terminal output with tables, spinners, and panels — ideal for live demos and screen recordings.

Flags:
- `--no-anchor` — Skip blockchain (useful if you only have SerpApi key)
- `--no-verify` — Anchor but skip on-chain verification read-back

#### Option B: CLI with JSON Output (Recommended for Scripting)

```bash
python -m backend.cli run path/to/face.jpg --summary
```

This produces clean, structured output — ideal for piping into other tools or for automated workflows.

Flags:
- `--summary` — Human-readable one-page result
- `--pretty` — Pretty-printed JSON output
- `--no-anchor` — Stop after evidence generation
- `--no-verify` — Anchor only, skip verification

#### Other CLI Commands

```bash
# Run only Person 1 (face detection + search, no validation)
python -m backend.cli person1 path/to/face.jpg --pretty

# Verify an existing evidence hash on-chain
python -m backend.cli verify-evidence --evidence-hash "0xabc123..." --pretty
```

---

## 📜 Smart Contract

**Contract:** [`src/EvidenceRegistry.sol`](src/EvidenceRegistry.sol)
**Network:** Base Sepolia (Chain ID: 84532)
**Solidity:** 0.8.25 with Cancun EVM target
**Toolchain:** Foundry (forge + cast)

### What It Stores

| Field | Type | Purpose |
|-------|------|---------|
| `evidenceHash` | `bytes32` | SHA-256 fingerprint of the canonical evidence JSON |
| `submitter` | `address` | Wallet that anchored the evidence |
| `timestamp` | `uint64` | Block timestamp when anchored |
| `source` | `string` | Normalized source domain (e.g., "twitter.com") |

### Key Design Choices

- **Hash-only storage.** No images, no text, no personal data on-chain. This keeps gas costs minimal and respects privacy.
- **Fail closed.** Empty hashes, empty sources, and duplicate submissions all revert with custom errors. The contract never stores garbage data.
- **Single event emission.** `EvidenceAnchored` is emitted on every successful anchor, making it trivial to index and monitor from off-chain.

### Deploy

```bash
forge script script/DeployEvidenceRegistry.s.sol:DeployEvidenceRegistry \
  --rpc-url "$BASE_SEPOLIA_RPC_URL" \
  --private-key "$PRIVATE_KEY" \
  --broadcast \
  --verify
```

### Verify On-Chain

```bash
# Check if evidence exists
cast call <CONTRACT_ADDRESS> "verifyEvidence(bytes32)(bool)" <EVIDENCE_HASH> \
  --rpc-url "$BASE_SEPOLIA_RPC_URL"

# Read full evidence record
cast call <CONTRACT_ADDRESS> "getEvidence(bytes32)(bool,address,uint64,string)" <EVIDENCE_HASH> \
  --rpc-url "$BASE_SEPOLIA_RPC_URL"
```

---

## 🧪 Running the Tests

### Solidity Tests (Smart Contract)

```bash
forge test
```

### Python Tests

```bash
python -m pytest tests/ -v
```

### Search Integration Test (Mock Mode)

```bash
python test_search.py --mock
```

### Search Integration Test (Live Mode)

```bash
export SERPAPI_API_KEY="your_key"
python test_search.py path/to/face.jpg
```

---

## ⚠️ Known Limitations

1. **SerpApi dependency.** The reverse image search relies on SerpApi's Google Lens API, which requires an API key and has rate limits on the free tier.
2. **InsightFace model download.** On first run, InsightFace downloads the `buffalo_l` model pack (~300MB). This requires internet access and may take a few minutes.
3. **No real-time streaming.** The pipeline processes one image at a time. It is not designed for real-time video feed processing.
4. **Testnet only.** The current deployment targets Base Sepolia (testnet). Mainnet deployment would require real ETH bridged to Base.
5. **Search accuracy depends on web presence.** If the person in the input image has minimal web presence, the reverse image search may return few or no candidates.

---

## 🏗️ Blockchain Used

**Base Sepolia** — An Ethereum Layer 2 testnet built on the OP Stack (Optimism).

- **Chain ID:** 84532
- **RPC:** `https://sepolia.base.org`
- **Explorer:** [BaseScan Sepolia](https://sepolia.basescan.org/)
- **Why L2?** Storing data on Ethereum L1 is expensive. Base gives us the same security model (data is posted to Ethereum) with sub-cent gas fees and 2-second block times. The smart contract code is byte-for-byte identical to what would run on mainnet.

---

## 👥 Team

Built for **Hacker House Goa 2026** — Task #3.

---

*"Don't trust. Verify. Mathematically."*
