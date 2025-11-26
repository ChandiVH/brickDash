import tkinter as tk
from tkinter import ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import matplotlib.animation as animation

import requests
from bs4 import BeautifulSoup

from datetime import datetime, date
from pathlib import Path
import threading
import time
import csv
import os


# Configuration
DEFAULT_URL = "http://192.168.20.75"
POLL_INTERVAL_SECONDS = 60
MAX_POINTS = 60
LOG_DIR_NAME = "brickDash_logs"


def get_data_source_url() -> str:
    """
    Get the URL to poll for bricks cut.
    Allows override via BRICKDASH_URL env var.
    """
    return os.getenv("BRICKDASH_URL", DEFAULT_URL)


def init_log_file() -> Path:
    """
    Create a per user log directory in the home folder and
    return the CSV file path for today's log.
    """
    home_dir = Path.home()
    log_root = home_dir / LOG_DIR_NAME
    log_root.mkdir(parents=True, exist_ok=True)

    csv_path = log_root / f"brickdash_log_{date.today()}.csv"

    file_exists = csv_path.exists()
    with csv_path.open(mode="a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "raw_bricks", "adjusted_bricks", "event"])


class BrickDashApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.url = get_data_source_url()

        # Logging
        self.csv_path = init_log_file()
        self.previous_logged_bricks = None

        # Data buffers
        self.timestamps = []
        self.bricks_cut_values = []
        self.bricks_cut_per_hour = []
        self.bricks_per_5min = {}
        self.start_bricks = None

        # State machine for raw vs adjusted count
        self.previous_raw = None  # last raw brickCount from PLC
        self.offset = 0  # accumulated bricks before last reset
        self.adjusted_bricks = 0  # continuous, corrected count
        self.reset_count = 0  # number of resets detected this session

        # GUI setup
        self._build_gui()

        # Start background thread
        self._start_logging_thread()

        # Start animation
        self.ani = animation.FuncAnimation(
            self.fig,
            self.update_plots,
            interval=1000,
            cache_frame_data=False,
        )

    # ---------- Data layer ----------

    def fetch_data(self) -> int | None:
        try:
            response = requests.get(self.url, timeout=2)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            h1 = soup.find("h1")
            if h1 is None:
                raise ValueError("No <h1> element found in response")
            bricks_cut = int(h1.text.strip().replace("Bricks Cut:", "").strip())
            return bricks_cut
        except Exception as e:
            # Basic feedback in the GUI status label
            self.status_var.set(f"Connection error: {e}")
            return None

    def logging_loop(self) -> None:
        while True:
            raw = self.fetch_data()
            if raw is not None:
                now = datetime.now()
                timestamp_str = now.strftime("%H:%M:%S")

                # Detect resets or backwards jumps
                event = "NORMAL"
                if self.previous_raw is not None and raw < self.previous_raw:
                    # PLC has reset or moved backwards significantly
                    self.reset_count += 1
                    self.offset += self.previous_raw
                    event = "RESET_DETECTED"
                    self.status_var.set(
                        f"Reset {self.reset_count} detected at {timestamp_str}, continuing count"
                    )
                else:
                    # Normal update
                    self.status_var.set(
                        f"Last update {timestamp_str} | Bricks Cut (raw): {raw}"
                    )

                # Compute adjusted continuous count
                self.adjusted_bricks = self.offset + raw
                self.previous_raw = raw

                # Update console and in memory buffers
                print(
                    f"[Console Log] {timestamp_str} | Raw: {raw} | Adjusted: {self.adjusted_bricks} | Event: {event}"
                )

                # For plotting, use adjusted count
                self.timestamps.append(timestamp_str)
                self.bricks_cut_values.append(self.adjusted_bricks)

                # Rate per hour
                if len(self.bricks_cut_values) >= 2:
                    diff = (
                            self.bricks_cut_values[-1]
                            - self.bricks_cut_values[-2]
                    )
                    self.bricks_cut_per_hour.append(diff * 60)
                else:
                    self.bricks_cut_per_hour.append(0)

                # 5 minute bucket
                minute = now.minute - (now.minute % 5)
                bucket = f"{now.hour:02d}:{minute:02d}"
                if bucket not in self.bricks_per_5min:
                    self.bricks_per_5min[bucket] = []
                self.bricks_per_5min[bucket].append(self.adjusted_bricks)

                # Log to CSV if raw changed
                if self.previous_logged_bricks != raw:
                    with self.csv_path.open(mode="a", newline="") as f:
                        writer = csv.writer(f)
                        writer.writerow(
                            [
                                now.strftime("%Y-%m-%d %H:%M:%S"),
                                raw,
                                self.adjusted_bricks,
                                event,
                            ]
                        )
                    self.previous_logged_bricks = raw

            time.sleep(POLL_INTERVAL_SECONDS)

    def _start_logging_thread(self) -> None:
        t = threading.Thread(target=self.logging_loop, daemon=True)
        t.start()

    # ---------- GUI layer ----------

    def _build_gui(self) -> None:
        self.root.title("BrickDash Phase 4 – Brick Cutting Monitor")
        self.root.geometry("1100x850")

        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Waiting for first data point...")
        status_label = ttk.Label(
            self.root,
            textvariable=self.status_var,
            anchor="w",
            relief=tk.SUNKEN,
        )
        status_label.pack(side=tk.BOTTOM, fill=tk.X)

        # Matplotlib figure
        self.fig, (self.ax1, self.ax2, self.ax3) = plt.subplots(
            3, 1, figsize=(10, 8)
        )
        self.fig.tight_layout()

        self.line1, = self.ax1.plot([], [], "o-", lw=2)
        self.ax1.set_title("Live Bricks Cut")
        self.ax1.set_ylabel("Bricks")
        self.ax1.grid(True)

        self.line2, = self.ax2.plot([], [], "r-", lw=2)
        self.ax2.set_title("Extrapolated Bricks Per Hour")
        self.ax2.set_ylabel("Bricks/hour")
        self.ax2.grid(True)

        self.ax3.set_title("Bricks/min in 5 Minute Intervals")
        self.ax3.set_ylabel("Avg Bricks/min")
        self.ax3.set_xlabel("Time Blocks")
        self.ax3.grid(True)

        canvas = FigureCanvasTkAgg(self.fig, master=main_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    # ---------- Plot updating ----------

    def update_plots(self, frame):
        if len(self.bricks_cut_values) == 0:
            return self.line1, self.line2

        # Plot 1: bricks cut
        recent_vals = self.bricks_cut_values[-MAX_POINTS:]
        self.line1.set_data(range(len(recent_vals)), recent_vals)
        self.ax1.set_xlim(0, max(len(recent_vals), 10))
        self.ax1.set_ylim(
            min(recent_vals) - 1,
            max(recent_vals) + 1,
        )

        # Plot 2: rate per hour
        recent_hour = self.bricks_cut_per_hour[-MAX_POINTS:]
        self.line2.set_data(range(len(recent_hour)), recent_hour)
        self.ax2.set_xlim(0, max(len(recent_hour), 10))
        self.ax2.set_ylim(
            0,
            max(recent_hour) + 10 if recent_hour else 10,
        )

        # Plot 3: 5 minute buckets
        bar_labels = list(self.bricks_per_5min.keys())[-10:]
        bar_data = list(self.bricks_per_5min.values())[-10:]
        bar_heights = [
            (bucket_vals[-1] - bucket_vals[0]) / len(bucket_vals)
            if len(bucket_vals) > 1
            else 0
            for bucket_vals in bar_data
        ]

        self.ax3.clear()
        self.ax3.bar(bar_labels, bar_heights)
        self.ax3.set_title("Bricks/min in 5 Minute Intervals")
        self.ax3.set_ylabel("Avg Bricks/min")
        self.ax3.set_xlabel("Time Blocks")
        self.ax3.set_xticks(range(len(bar_labels)))
        self.ax3.set_xticklabels(bar_labels, rotation=30, ha="right")
        self.ax3.grid(True)

        return self.line1, self.line2


def main():
    root = tk.Tk()
    app = BrickDashApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
