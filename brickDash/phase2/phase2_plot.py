import requests
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import threading
import time
from datetime import datetime

URL = "http://192.168.20.75"

def fetch_data():
    try:
        response = requests.get(URL, timeout=2)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        h1 = soup.find('h1')
        bricks_cut = int(h1.text.strip().replace("Bricks Cut:", "").strip())
        return bricks_cut
    except Exception as e:
        print(f"[ERROR] {e}")
        return None

# ---- Console logger runs in background ----
def log_to_console():
    while True:
        bricks = fetch_data()
        if bricks is not None:
            print(f"[Console Log] Bricks Cut: {bricks}")
        else:
            print("[Console Log] Waiting for Arduino...")
        time.sleep(1)

# Start logging thread
threading.Thread(target=log_to_console, daemon=True).start()

# ---- Real-time Plotting ----
timestamps = []
bricks_cut_values = []

fig, ax = plt.subplots()
line, = ax.plot([], [], lw=2)
ax.set_title("Bricks Cut Over Time")
ax.set_xlabel("Time")
ax.set_ylabel("Bricks Cut")

def update(frame):
    bricks = fetch_data()
    if bricks is not None:
        timestamps.append(datetime.now().strftime('%H:%M:%S'))
        bricks_cut_values.append(bricks)

        if len(timestamps) > 60:
            timestamps.pop(0)
            bricks_cut_values.pop(0)

        line.set_data(range(len(bricks_cut_values)), bricks_cut_values)
        ax.set_xlim(0, len(bricks_cut_values))
        ax.set_xticks(range(len(timestamps)))
        ax.set_xticklabels(timestamps, rotation=45, ha='right')
        ax.set_ylim(min(bricks_cut_values) - 1, max(bricks_cut_values) + 1)
        ax.relim()
        ax.autoscale_view()

    return line,

ani = animation.FuncAnimation(
    fig,
    update,
    interval=1000,
    cache_frame_data=False  # suppress warning
)

plt.tight_layout()
plt.show()
