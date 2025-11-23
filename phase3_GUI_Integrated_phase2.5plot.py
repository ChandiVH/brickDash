import tkinter as tk
from tkinter import ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import threading
import time

# --- Phase 2.5 Setup ---
URL = "http://192.168.20.75"
MAX_POINTS = 60

timestamps = []
bricks_cut_values = []
bricks_cut_per_hour = []
bricks_per_5min = {}
start_time = None

# --- Fetch from Web Interface ---
def fetch_data():
    try:
        response = requests.get(URL, timeout=2)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        h1 = soup.find('h1')
        bricks_cut = int(h1.text.strip().replace("Bricks Cut:", "").strip())
        return bricks_cut
    except:
        return None

# --- Logging Thread (Every 60s) ---
def log_to_console():
    global start_time
    while True:
        bricks = fetch_data()
        if bricks is not None:
            now = datetime.now()
            print(f"[Console Log] {now.strftime('%H:%M:%S')} | Bricks Cut: {bricks}")
            timestamps.append(now.strftime('%H:%M:%S'))
            bricks_cut_values.append(bricks)

            if start_time is None:
                start_time = bricks

            if len(bricks_cut_values) >= 2:
                diff = bricks_cut_values[-1] - bricks_cut_values[-2]
                bricks_cut_per_hour.append(diff * 60)
            else:
                bricks_cut_per_hour.append(0)

            minute = now.minute - (now.minute % 5)
            bucket = f"{now.hour:02d}:{minute:02d}"
            if bucket not in bricks_per_5min:
                bricks_per_5min[bucket] = []
            bricks_per_5min[bucket].append(bricks)

        time.sleep(60)

# --- Tkinter GUI ---
root = tk.Tk()
root.title("Brick Cutting Monitor")
root.geometry("1000x800")

plot_frame = ttk.Frame(root)
plot_frame.pack(fill=tk.BOTH, expand=True)

fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 8))
fig.tight_layout()

line1, = ax1.plot([], [], 'o-', lw=2)
ax1.set_title("Live Bricks Cut")
ax1.set_ylabel("Bricks")
ax1.grid(True)

line2, = ax2.plot([], [], 'r-', lw=2)
ax2.set_title("Extrapolated Bricks Per Hour")
ax2.set_ylabel("Bricks/hour")
ax2.grid(True)

ax3.set_title("Bricks/min in 5-Minute Intervals")
ax3.set_ylabel("Avg Bricks/min")
ax3.set_xlabel("Time Blocks")
ax3.grid(True)

canvas = FigureCanvasTkAgg(fig, master=plot_frame)
canvas.draw()
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

# --- Real-time Update Function ---
def update(frame):
    if len(bricks_cut_values) == 0:
        return line1, line2

    # Subplot 1
    recent_vals = bricks_cut_values[-MAX_POINTS:]
    line1.set_data(range(len(recent_vals)), recent_vals)
    ax1.set_xlim(0, MAX_POINTS)
    ax1.set_ylim(min(recent_vals) - 1, max(recent_vals) + 1)

    # Subplot 2
    recent_hour = bricks_cut_per_hour[-MAX_POINTS:]
    line2.set_data(range(len(recent_hour)), recent_hour)
    ax2.set_xlim(0, MAX_POINTS)
    ax2.set_ylim(0, max(recent_hour) + 10)

    # Subplot 3
    bar_labels = list(bricks_per_5min.keys())[-10:]
    bar_data = list(bricks_per_5min.values())[-10:]
    bar_heights = [
        (bucket[-1] - bucket[0]) / len(bucket) if len(bucket) > 1 else 0
        for bucket in bar_data
    ]
    ax3.clear()
    ax3.bar(bar_labels, bar_heights)
    ax3.set_title("Bricks/min in 5-Minute Intervals")
    ax3.set_ylabel("Avg Bricks/min")
    ax3.set_xlabel("Time Blocks")
    ax3.set_xticks(range(len(bar_labels)))
    ax3.set_xticklabels(bar_labels, rotation=30, ha='right')
    ax3.grid(True)

    return line1, line2

# --- Animation ---
ani = animation.FuncAnimation(fig, update, interval=1000, cache_frame_data=False)

# --- Auto Start Background Thread ---
threading.Thread(target=log_to_console, daemon=True).start()

root.mainloop()
