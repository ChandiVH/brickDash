import requests
from bs4 import BeautifulSoup
import time

# Arduino OPTA Web Server URL
URL = "http://192.168.20.75"

def fetch_data():
    try:
        # Send HTTP GET request
        response = requests.get(URL, timeout=2)
        response.raise_for_status()  # Raise error for bad responses

        # Parse HTML using BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        h1 = soup.find('h1')
        h2 = soup.find('h2')

        # Extract numbers
        bricks_cut = int(h1.text.strip().replace("Bricks Cut:", "").strip())
        bricks_per_min = float(h2.text.strip().replace("Speed:", "").replace("bricks/min", "").strip())

        return bricks_cut, bricks_per_min

    except Exception as e:
        print(f"[ERROR] {e}")
        return None, None

# Run this loop to see live data every second
if __name__ == "__main__":
    while True:
        bricks, speed = fetch_data()
        if bricks is not None:
            print(f"Bricks Cut: {bricks} | Speed: {speed:.2f} bricks/min")
        else:
            print("Waiting for Arduino...")
        time.sleep(1)
