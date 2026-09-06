import time
import os
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# Import your custom AI and Cryptography modules
from backend.validation import get_face_encoding, download_candidate_image, verify_candidate_match
from backend.evidence import canonicalize_and_hash

console = Console()

def run_pipeline(query_image_path, candidate_list):
    console.print(Panel.fit("[bold cyan]HH GOA 2026: L2 Identity Verification Pipeline[/bold cyan]", border_style="cyan"))
    
    # --- STAGE 1: EXTRACT QUERY FINGERPRINT ---
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        progress.add_task(description="Extracting biometric fingerprint from input...", total=None)
        query_encoding = get_face_encoding(query_image_path)
        
    if query_encoding is None:
        console.print("[bold red]CRITICAL HALT: No face detected in input image.[/bold red]")
        return
    console.print("[bold green][OK] Input biometric fingerprint secured.[/bold green]")

    # --- STAGE 2: CANDIDATE VALIDATION LOOP ---
    best_candidate = None
    highest_confidence = 0.0
    second_highest = 0.0
    
    console.print("\n[*] Initializing Candidate Validation Engine...")
    
    # TODO: Create a loop that iterates over the 'candidate_list'
    for index, candidate in enumerate(candidate_list):
        # 1. Download the candidate's image to a temporary file (e.g., f"temp_candidate_{index}.jpg")
        temp_candidate_path = f"temp_candidate_{index}.jpg"
        console.print(f"[*] Processing candidate {index + 1}/{len(candidate_list)}: {candidate['title']}")
        
        success = download_candidate_image(candidate["image_url"], temp_candidate_path)
        
        if success:
            # 2. If download is successful, run 'verify_candidate_match' against 'query_encoding'
            result = verify_candidate_match(query_encoding, temp_candidate_path)
            confidence = result.get("confidence", 0.0)
            
            console.print(f"[+] Match confidence for {candidate['title']}: {confidence}%")
            
            # 3. If the 'confidence' is higher than 'highest_confidence', update 'second_highest', 'highest_confidence', and 'best_candidate'.
            if confidence > highest_confidence:
                second_highest = highest_confidence
                highest_confidence = confidence
                best_candidate = candidate
            elif confidence > second_highest:
                second_highest = confidence
                
            # Clean up the temporary file if desired, or leave it for debugging
            try:
                os.remove(temp_candidate_path)
            except OSError:
                pass
        
    # --- STAGE 3: CONFIDENCE MARGIN ENFORCEMENT ---
    # We require the top match to be at least 5% more confident than the runner up to avoid ambiguity
    margin = highest_confidence - second_highest
    
    if best_candidate is None or highest_confidence < 50.0:
        console.print("[bold red]CRITICAL HALT: No high-confidence matches found.[/bold red]")
        return
        
    if margin < 5.0:
        console.print(f"[bold red]CRITICAL HALT: Ambiguous match detected. Margin too low ({margin}%).[/bold red]")
        return
        
    console.print(f"[bold green][OK] Identity Match Locked. Confidence: {highest_confidence}% (Margin: {margin}%)[/bold green]")
    time.sleep(1)

    # --- STAGE 4: CANONICALIZATION & EXPORT ---
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        progress.add_task(description="Generating SHA-256 Evidence Fingerprint...", total=None)
        
        # Prepare the exact data structure Teammate 3 requested
        evidence_payload = {
            "url": best_candidate["url"],
            "image_url": best_candidate["image_url"],
            "title": best_candidate["title"],
            "source": best_candidate["source"],
            "published_at": str(int(time.time())) # Current timestamp
        }
        
        # Call your 'canonicalize_and_hash' function on the 'evidence_payload'
        evidence_hash = canonicalize_and_hash(evidence_payload)
        
    # FINAL OUTPUT - Handoff to Blockchain Layer
    console.print(Panel(
        f"[bold white]EVIDENCE PACKAGED FOR BASE SEPOLIA[/bold white]\n\n"
        f"Match URL: [underline]{evidence_payload['url']}[/underline]\n"
        f"SHA-256 Hash: [green]{evidence_hash}[/green]\n\n"
        f"To anchor on-chain, export these environment variables for Foundry:\n"
        f"export EVIDENCE_HASH={evidence_hash}\n"
        f"export EVIDENCE_SOURCE_URL={evidence_payload['url']}\n",
        title="[bold green]Pipeline Orchestration Complete[/bold green]",
        border_style="green"
    ))

if __name__ == "__main__":
    # Mocking Teammate 1's Search Output for the Demo
    # In a real run, this list would come directly from test_search.py
    mock_candidates = [
        {
            "candidate_id": "001",
            "url": "https://en.wikipedia.org/wiki/Mark_Zuckerberg",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/1/18/Mark_Zuckerberg_F8_2019_Keynote_%2832830578717%29_%28cropped%29.jpg",
            "title": "Mark Zuckerberg",
            "source": "Wikipedia"
        },
        {
            "candidate_id": "002",
            "url": "https://en.wikipedia.org/wiki/Elon_Musk",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/3/34/Elon_Musk_Royal_Society_%28crop2%29.jpg",
            "title": "Elon Musk",
            "source": "Wikipedia"
        }
    ]
    
    # You can change this to a local picture of Elon Musk to test!
    LOCAL_QUERY_IMAGE = "query_face.jpg" 
    
    run_pipeline(LOCAL_QUERY_IMAGE, mock_candidates)
