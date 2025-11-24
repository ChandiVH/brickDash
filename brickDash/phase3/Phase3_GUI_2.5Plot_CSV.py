import tkinter as tk
from tkinter import ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date

import threading
import time

import csv
import os

# Set up logging path to use the existing brickDash/logs directory
base_dir = os.path.dirname(os.path.abspath(__file__))

# First assume logs folder is next to this script
log_dir = os.path.join(base_dir, "logs")

# If that does not exist, fall back to brickDash/logs one level up
if not os.path.isdir(log_dir):
    log_dir = os.path.join(os.path.dirname(base_dir), "logs")

csv_filename = os.path.join(log_dir, f"brickdash_log_{date.today()}.csv")
previous_logged_bricks = None

# Create the file with headers only if it does not exist
file_exists = os.path.exists(csv_filename)
with open(csv_filename, mode="a", newline="") as file:
    writer = csv.writer(file)
    if not file_exists:
        writer.writerow(["timestamp", "brick_count"])


# Phase 2.5 setup
URL = "http://192.168.20.75"
MAX_POINTS = 60

timestamps = []
bricks_cut_values = []
bricks_cut_per_hour = []
bricks_per_5min = {}
start_time = None


# Fetch from web interface
def fetch_data():
    try:
        response = requests.get(URL, timeout=2)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        h1 = soup.find("h1")
        bricks_cut = int(h1.text.strip().replace("Bricks Cut:", "").strip())
        return bricks_cut
    except Exception:
        return None


# Logging thread (every 60 seconds)
def log_to_console():
    global start_time
    while True:
        bricks = fetch_data()
        if bricks is not None:
            now = datetime.now()
            print(f"[Console Log] {now.strftime('%H:%M:%S')} | Bricks Cut: {bricks}")
            timestamps.append(now.strftime("%H:%M:%S"))
            bricks_cut_values.append(bricks)

            global previous_logged_bricks
            if previous_logged_bricks != bricks:
                with open(csv_filename, mode="a", newline="") as file:
                    writer = csv.writer(file)
                    writer.writerow([now.strftime("%Y-%m-%d %H:%M:%S"), bricks])
                previous_logged_bricks = bricks

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


# Tkinter GUI
root = tk.Tk()
root.title("Brick Cutting Monitor")
root.geometry("1000x800")

plot_frame = ttk.Frame(root)
plot_frame.pack(fill=tk.BOTH, expand=True)

fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 8))
fig.tight_layout()

line1, = ax1.plot([], [], "o-", lw=2)
ax1.set_title("Live Bricks Cut")
ax1.set_ylabel("Bricks")
ax1.grid(True)

line2, = ax2.plot([], [], "r-", lw=2)
ax2.set_title("Extrapolated Bricks Per Hour")
ax2.set_ylabel("Bricks/hour")
ax2.grid(True)

ax3.set_title("Bricks/min in 5 Minute Intervals")
ax3.set_ylabel("Avg Bricks/min")
ax3.set_xlabel("Time Blocks")
ax3.grid(True)

canvas = FigureCanvasTkAgg(fig, master=plot_frame)
canvas.draw()
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)


# Real time update function
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
    ax2.set_ylim(0, max(recent_hour) + 10 if recent_hour else 10)

    # Subplot 3
    bar_labels = list(bricks_per_5min.keys())[-10:]
    bar_data = list(bricks_per_5min.values())[-10:]
    bar_heights = [
        (bucket[-1] - bucket[0]) / len(bucket) if len(bucket) > 1 else 0
        for bucket in bar_data
    ]
    ax3.clear()
    ax3.bar(bar_labels, bar_heights)
    ax3.set_title("Bricks/min in 5 Minute Intervals")
    ax3.set_ylabel("Avg Bricks/min")
    ax3.set_xlabel("Time Blocks")
    ax3.set_xticks(range(len(bar_labels)))
    ax3.set_xticklabels(bar_labels, rotation=30, ha="right")
    ax3.grid(True)

    return line1, line2


# Animation
ani = animation.FuncAnimation(fig, update, interval=1000, cache_frame_data=False)

# Auto start background thread
threading.Thread(target=log_to_console, daemon=True).start()

root.mainloop()
