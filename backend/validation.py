import requests
import os
import face_recognition

def download_candidate_image(url, save_path):
    print(f"[*] Attempting to download candidate image from: {url}")
    
    try:
        # We add a 'timeout' because if a website is broken, we don't 
        # want our hackathon pipeline to freeze forever waiting for it.
        # We also add a User-Agent header so websites don't block us thinking we are a malicious bot.
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=10)
        
        # Check if the website actually gave us an image (Status 200 = OK)
        response.raise_for_status()
        
        # PRODUCTION UPGRADE: Verify it's actually an image, not an HTML page
        content_type = response.headers.get('Content-Type', '')
        if not content_type.startswith('image/'):
            print(f"[-] ERROR: URL did not return an image. Returned: {content_type}")
            return False
        
        # Open a new file in 'wb' (Write Binary) mode
        with open(save_path, "wb") as file:
            # response.content contains the raw binary pixels
            file.write(response.content)
            
        print(f"[+] SUCCESS: Image saved to {save_path}")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"[-] ERROR: Failed to download image. Reason: {e}")
        return False

def get_face_encoding(image_path):
    """
    Helper function: Loads an image and returns the 128-D face encoding.
    Returns None if no face is found.
    """
    try:
        image = face_recognition.load_image_file(image_path)
        encodings = face_recognition.face_encodings(image)
        
        if not encodings:
            return None # No face detected
            
        return encodings[0]
    except Exception as e:
        print(f"[-] ERROR processing image {image_path}: {e}")
        return None

def verify_candidate_match(query_encoding, candidate_image_path):
    """
    Compares the original face encoding against the downloaded candidate image.
    Returns the mathematical distance and a boolean match result.
    """
    print(f"[*] Analyzing candidate biometric geometry...")
    
    candidate_encoding = get_face_encoding(candidate_image_path)
    if candidate_encoding is None:
        return {"match": False, "confidence": 0.0, "message": "No face found in candidate image."}
    
    # Calculate the mathematical distance (Lower is better, 0.6 is the strict threshold)
    face_distances = face_recognition.face_distance([query_encoding], candidate_encoding)
    distance = face_distances[0]
    
    # Calculate a simple 0-100 confidence score based on the 0.6 threshold
    # If distance is 0.6, confidence is 0%. If distance is 0.0, confidence is 100%.
    confidence_score = max(0.0, 1.0 - (distance / 0.6))
    is_match = distance <= 0.6
    
    return {
        "match": is_match,
        "distance": round(distance, 4),
        "confidence": round(confidence_score * 100, 2)
    }

if __name__ == "__main__":
    test_url = "https://upload.wikimedia.org/wikipedia/commons/a/a0/Bill_Gates_2018.jpg"
    test_save_path = "test_download.jpg"
    query_url = "https://upload.wikimedia.org/wikipedia/commons/e/ed/Elon_Musk_Royal_Society.jpg"
    query_save_path = "query_face.jpg"
    
    print("--- Starting AI Validation Test ---")
    
    # 1. Download Candidate Image (Bill Gates)
    success = download_candidate_image(test_url, test_save_path)
    
    # 2. Download Query Image (Elon Musk)
    print(f"\n[*] Downloading Query Face (Elon Musk)...")
    download_candidate_image(query_url, query_save_path)
    
    # 3. Test Math
    if success and os.path.exists(query_save_path):
        print("\n[*] Extracting fingerprint from query face...")
        query_encoding = get_face_encoding(query_save_path)
        
        if query_encoding is not None:
            print("[*] Testing Mathematical Similarity (Musk vs Gates)...")
            result = verify_candidate_match(query_encoding, test_save_path)
            print(f"\n[RESULT] {result}")
        else:
            print("[-] Failed to get encoding for query face.")
    else:
        print("[-] Download test failed. Cannot proceed with math test.")
