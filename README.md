#  FaceChain — Face to Blockchain Verification Pipeline | HH Goa 2026

![Pipeline Status](https://img.shields.io/badge/Pipeline-Production_Ready-brightgreen)
![Network](https://img.shields.io/badge/Network-Base_Sepolia_(L2)-blue)
![AI Engine](https://img.shields.io/badge/AI_Engine-InsightFace_ArcFace-purple)
![Smart Contract](https://img.shields.io/badge/Smart_Contract-Solidity_0.8.25-orange)
![Toolchain](https://img.shields.io/badge/Toolchain-Foundry-red)

**A production-grade intelligence pipeline that takes a face scan, finds matching content across the web, mathematically verifies the identity, and anchors a tamper-proof cryptographic fingerprint to an Ethereum Layer 2 blockchain — fully automated, end to end.**

> Built for **Hacker House Goa 2026** — Shortlisting Task #3: Face Identification & Blockchain Verification.

---

## What Is This Project? 

If you're reading this for the first time, this section will explain everything in simple words.

### The Problem

How do you prove that a person is real?

Think about how a bank verifies your identity today: you walk in, show your face, and hand them your ID card. They match the two and say, *"Yes, this is you."*

Now imagine doing this **entirely online, without any ID card, using only a face photo and the public internet.** That is exactly what FaceChain does.

### The Solution 

FaceChain is an **automated identity verification system for Web3.** Here is the flow in the simplest terms:

1. **You give it a face photo.** This could be a selfie, a webcam capture, or any image with a clear face.

2. **It searches the internet for that face.** The system uses reverse image search (Google Lens) to scour social media, news sites, and public profiles. It finds web pages where this person's face appears — a LinkedIn photo, a Twitter profile picture, an Instagram post, etc.

3. **It mathematically verifies the match.** The system doesn't blindly trust search results. It downloads every candidate image, extracts a 512-dimensional mathematical "fingerprint" of the face (called an ArcFace embedding), and computes how similar the two faces are. Only if the math passes strict thresholds does it accept the match.

4. **It locks the proof onto a blockchain.** Once it finds and verifies a matching web profile, it takes all the metadata (the URL, the title, the image hash, the source) and creates a single SHA-256 fingerprint of that entire evidence package. That fingerprint is permanently written to the Base Sepolia blockchain — where it can never be changed or deleted by anyone.

**The result?** You now have a permanent, tamper-proof, on-chain record that says: *"On this date, at this time, we verified that this face belongs to a real person whose identity is documented at this URL, and the evidence fingerprint is locked on the blockchain."*

### Why Is This Useful?

- **KYC (Know Your Customer) for crypto:** Before opening a high-value wallet or DeFi account, the system can verify the person is real — not a bot, not a deepfake.
- **Anti-fraud:** If someone claims to be a certain person, the system can verify their face against public web records.
- **Permanent proof:** Even if the person deletes their social media account tomorrow, the blockchain record proves that the verification happened and what the evidence looked like at the time.

### The Tamper Check (What Are We Actually Verifying?)

This is often confusing for new users, so let's be crystal clear:

> **We are NOT checking if the input face photo is tampered.** We are checking whether the *web evidence* (the social media post we found) has been changed after we locked it into the blockchain.

Here is a real-world example:

**Day 1 — Verification:**
- You upload a photo of Alice.
- The system finds Alice's LinkedIn profile. It downloads the profile image, title, URL, and metadata.
- It hashes all of this into a fingerprint: `0xabc123...`
- It writes `0xabc123...` to the blockchain. Done.

**Day 30 — Tamper Check (Evidence is Pristine):**
- Someone wants to verify our work. They go to Alice's LinkedIn URL, download the current image and metadata.
- They hash it using the same method → they get `0xabc123...`
- They check the blockchain → it also says `0xabc123...`
- **The hashes match → ✓ VERIFIED.** The evidence hasn't been touched.

**Day 30 — Tamper Check (Evidence has been Altered):**
- But what if Alice secretly changed her LinkedIn profile photo between Day 1 and Day 30?
- When someone re-downloads and re-hashes the page, the new hash is `0xdef999...`
- They check the blockchain → it still says `0xabc123...`
- **The hashes DON'T match → ✗ TAMPERED.** The source evidence has been altered since the original verification.

### The TL;DR

| Step | What happens |
|------|-------------|
| **INPUT** | A random face photo |
| **DISCOVER** | Search the web to find the person's public profile |
| **VERIFY** | Use AI math (512-D embeddings) to guarantee the web face matches the input face |
| **LOCK** | Hash the evidence and anchor it on the blockchain permanently |
| **TAMPER CHECK** | Re-download + re-hash the live web post and compare against the blockchain hash |

We use the **web to discover** the identity, and we use the **blockchain to freeze** that discovery in time — so no one can secretly alter the evidence later without us knowing.

---

## Table of Contents

- [What Is This Project?](#what-is-this-project-start-here)
- [The Vision](#-the-vision-why-we-built-it-this-way)
- [System Architecture](#-system-architecture)
- [How It Works (Step by Step)](#-how-it-works-step-by-step)
- [Engineering Decisions & Justifications](#-engineering-decisions--justifications)
- [Fault-Tolerant Design](#-fault-tolerant-design)
- [Project Structure](#-project-structure)
- [How to Run](#-how-to-run)
- [Smart Contract](#-smart-contract)
- [Running the Tests](#-running-the-tests)
- [Tamper Detection — How to Verify Evidence](#-tamper-detection--how-to-verify-evidence-verifypy)
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
├── verify.py                        # Tamper detection script (re-hash & compare)
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
├── evidence/                        # Auto-saved evidence packages (JSON, gitignored)
│
├── foundry.toml                     # Foundry configuration (Base Sepolia)
└── .gitignore
```

---

##  How to Run

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

##  Running the Tests

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

## Tamper Detection — How to Verify Evidence (`verify.py`)

Once the pipeline has anchored evidence on the blockchain, the natural question is: **"How do I check later if the original social media post was changed or deleted?"**

We built a dedicated script — `verify.py` — that automates this entire tamper-detection process in one command.

### How the Tamper Check Works (Step by Step)

Here is the exact process `verify.py` follows:

#### Step 1 — Read the Blockchain
The script connects to the Base Sepolia smart contract and asks:
> *"Hey blockchain, do you have a record for this evidence hash? What was the original SHA-256 fingerprint, the submitter's wallet, the timestamp, and the source domain?"*

If the record exists, the script prints the on-chain data. If it doesn't exist, the script stops immediately and tells you the evidence was never anchored.

#### Step 2 — Scrape the Live Web
The script goes back to the **exact same URL** on the live internet and **re-downloads the current version** of the image. This is the "live" version — whatever exists on the web *right now*.

It also performs a MIME-type check to make sure the URL still returns an image (not an HTML error page or a CAPTCHA).

#### Step 3 — Re-Hash
The script takes the freshly downloaded image, computes its SHA-256 hash, rebuilds the evidence record using the **same deterministic canonicalization** that was used during the original pipeline run, and generates a **new evidence hash**.

This is the critical part: the canonicalization is deterministic. Same data → same JSON → same hash. Always.

#### Step 4 — The Collision Test
The script compares the **new hash** (from the live web) to the **original hash** (from the blockchain):

| Scenario | What it means |
|----------|---------------|
| **Hashes match** | The source content is **pristine**. Nothing has been changed since the original verification. |
| **Hashes differ** | The source content has been **tampered with**. Something changed — even a single pixel or letter is enough to produce a completely different hash. |

### Running the Tamper Check

#### Quick Check: Does the evidence exist on-chain?

This only queries the blockchain — no web scraping:

```bash
python verify.py --evidence-hash 0xYOUR_HASH_HERE --check-only
```

**What you'll see:**
```
╭─────────────────────────────────────────────╮
│    FaceChain Tamper Detection               │
│    Verifying evidence integrity...          │
╰─────────────────────────────────────────────╯

[Step 1] Reading the blockchain record from Base Sepolia...
  ✓ Record found on-chain!
    Submitter : 0xYourWalletAddress
    Timestamp : 1725667200
    Source    : twitter.com

  Evidence exists on the blockchain.
```

#### Full Tamper Check: Re-download + Re-hash + Compare

This goes back to the live web, re-downloads the image, and compares:

```bash
python verify.py \
  --evidence-hash 0xYOUR_HASH_HERE \
  --source-url "https://twitter.com/user/status/123" \
  --image-url "https://pbs.twimg.com/media/photo.jpg"
```

**If the evidence is PRISTINE (not tampered):**
```
[Step 4] Comparing blockchain hash vs. live web hash...

┌─────────────────────────────────────────────────┐
│           Hash Comparison                       │
├──────────────────────┬──────────────────────────┤
│ Blockchain (Original)│ 0xabc123...              │
│ Live Web (Current)   │ 0xabc123...              │
└──────────────────────┴──────────────────────────┘

╭──────────────────────────────────────────────────╮
│  ✓ VERIFIED: Evidence is PRISTINE.               │
│                                                  │
│  The live web content produces the exact same     │
│  hash as what was anchored on the blockchain.     │
│  The source data has NOT been altered.            │
╰──────────────────────────────────────────────────╯
```

**If the evidence has been TAMPERED WITH:**
```
[Step 4] Comparing blockchain hash vs. live web hash...

┌─────────────────────────────────────────────────┐
│           Hash Comparison                       │
├──────────────────────┬──────────────────────────┤
│ Blockchain (Original)│ 0xabc123...              │
│ Live Web (Current)   │ 0xdef999...   ← CHANGED │
└──────────────────────┴──────────────────────────┘

╭──────────────────────────────────────────────────╮
│  ✗ TAMPERED: Source evidence has been ALTERED.   │
│                                                  │
│  The live web content produces a DIFFERENT hash   │
│  than what was originally anchored on the         │
│  blockchain. The source has been modified.        │
╰──────────────────────────────────────────────────╯
```

### Where do I get the evidence hash?

When you run the main pipeline, it **automatically saves an evidence file** to the `evidence/` directory:

```
  ✓ Evidence saved: evidence/evidence_0x7a3b9f1234567890.json
  │  Tip: Use this file with verify.py: python verify.py --evidence-file evidence/evidence_0x7a3b9f1234567890.json
```

This JSON file contains everything needed for verification: the evidence hash, the source URL, the image hash, the matched candidate details, and the blockchain transaction info.

### End-to-End Example: Full Workflow

```bash
# Step 1: Run the pipeline (evidence file is auto-saved to evidence/)
python main.py my_photo.jpg
# Output: evidence/evidence_0x7a3b9f1234567890.json saved

# Step 2: Later, verify using the saved evidence file (easiest method)
python verify.py --evidence-file evidence/evidence_0x7a3b9f1234567890.json
# Output: ✓ VERIFIED or ✗ TAMPERED or ⚠ UNAVAILABLE

# Alternative: verify by hash (auto-discovers the evidence file)
python verify.py --evidence-hash 0x7a3b9f...

# Alternative: fully manual (no evidence file needed)
python verify.py \
  --evidence-hash 0x7a3b9f... \
  --source-url "https://twitter.com/user/post" \
  --image-url "https://pbs.twimg.com/media/photo.jpg"
```

### How Post Identity Works (Same Post vs. Different Post)

A common question: *"SHA-256 only tells us if the content changed — how do we know if it's the same post that was modified, or a completely different post?"*

**The answer: the URL is baked into the hash.**

The `source_url` is one of the fields inside the canonical evidence record. This means:

| Scenario | URL | Content | Result |
|---|---|---|---|
| Same post, same content | `twitter.com/post/123` | Unchanged | Same hash → **VERIFIED** |
| Same post, content changed | `twitter.com/post/123` | Photo swapped | Different hash → **TAMPERED** |
| Completely different post | `twitter.com/post/456` | Different post | Different hash, but different blockchain record |

When the pipeline runs again and finds a **different** post (Post B instead of Post A):
- Post A → `evidence_hash_A` → blockchain record A
- Post B → `evidence_hash_B` → blockchain record B (new, independent record)

The system **never overwrites** old records. Each verification is its own immutable entry on the blockchain. If Post A is deleted and Post B is found later, both records coexist independently on-chain.

---

## ✨ Why FaceChain Stands Out

While a generic solution might pipe an image through a search API and blindly dump a URL onto a testnet, **FaceChain** is engineered as a robust, enterprise-grade architecture:

1. **Trust-less Validation:** We do not blindly trust search results. Every candidate is downloaded, embedded using ArcFace (512-D), and mathematically verified against the input face.
2. **True Tamper-Proofing:** Storing a raw URL on-chain is vulnerable to link rot and content alteration. By canonicalizing and hashing the full evidence payload *before* anchoring, we ensure cryptographic permanence.
3. **Defensive Engineering:** Our pipeline actively guards against corrupt payloads with strict MIME-type checks, handles timeouts gracefully, prevents duplicate on-chain anchoring, and verifies successful mining via RPC polling.
4. **Separation of Concerns:** Our three-layer architecture (Discovery, Validation, Blockchain) uses clean, strictly-typed Pydantic schemas, making it modular, scalable, and easy to maintain.

---

## 🔮 Future Enhancements

1. **Zero-Knowledge Identity Proofs:** Implement zk-SNARKs to prove a face matches an on-chain identity record without revealing the face itself.
2. **Decentralized Storage:** Anchor the raw image and metadata to IPFS/Arweave and store only the CID on Base Sepolia for a fully decentralized stack.
3. **Real-time Video Processing:** Expand the pipeline to process video feeds, tracking and verifying multiple identities in real-time.
4. **Multi-Modal Verification:** Incorporate voice and behavioral biometrics alongside facial recognition for composite identity scores.

---

## --> Notes to Consider

- **Web Presence Dependency:** Search accuracy heavily depends on the individual's web footprint. If the person in the input image has minimal web presence, the reverse image search may return few or no candidates.
- **Strict Biometric Angles:** The localized facial recognition model is highly optimized for front-facing biometrics. Extreme side-profiles or heavy occlusions (such as masks or dark glasses) may result in encoding failures or reduced accuracy.

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

**The team who worked on this:**
- [Rohinth S](https://github.com/rohinths) 
- [Suyash Agarwal](https://github.com/SuyashAlphaC)
- [Mithul Nama](https://github.com/mithulcrafts)

---

*"Don't trust. Verify. Mathematically."*
