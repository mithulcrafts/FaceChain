import requests
import os

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
        
        # Open a new file in 'wb' (Write Binary) mode
        with open(save_path, "wb") as file:
            # response.content contains the raw binary pixels
            file.write(response.content)
            
        print(f"[+] SUCCESS: Image saved to {save_path}")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"[-] ERROR: Failed to download image. Reason: {e}")
        return False

if __name__ == "__main__":
    test_url = "https://upload.wikimedia.org/wikipedia/commons/a/a0/Bill_Gates_2018.jpg"
    test_save_path = "test_download.jpg"

    
    print("--- Starting Download Test ---")
    success = download_candidate_image(test_url, test_save_path)
    if success:
        print("Download test completed successfully.")
    else:
        print("Download test failed.")
