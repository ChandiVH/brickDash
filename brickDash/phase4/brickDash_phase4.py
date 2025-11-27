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
import sys


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

    return csv_path


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

        # Threading control
        self.stop_event = threading.Event()
        self.logging_thread: threading.Thread | None = None
        self.data_lock = threading.Lock()

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

    # ---------- Utility: thread-safe status updates ----------

    def _set_status(self, msg: str) -> None:
        """
        Thread-safe way to update the status bar.
        Schedules the actual set() on the Tk main thread.
        """
        try:
            self.root.after(0, self.status_var.set, msg)
        except Exception:
            # Root might already be destroyed; ignore
            pass

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
            self._set_status(f"Connection error: {e}")
            return None

    def logging_loop(self) -> None:
        """
        Background loop that polls the PLC and updates internal state.
        Controlled via stop_event so we can shut it down quickly and cleanly.
        """
        while not self.stop_event.is_set():
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
                    self._set_status(
                        f"Reset {self.reset_count} detected at {timestamp_str}, continuing count"
                    )
                else:
                    # Normal update
                    self._set_status(
                        f"Last update {timestamp_str} | Bricks Cut (raw): {raw}"
                    )

                # Compute adjusted continuous count
                self.adjusted_bricks = self.offset + raw
                self.previous_raw = raw

                # Update console and in memory buffers
                print(
                    f"[Console Log] {timestamp_str} | Raw: {raw} | Adjusted: {self.adjusted_bricks} | Event: {event}"
                )

                # Update data used by the plots
                with self.data_lock:
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

            # Wait for the next poll interval, but wake up early if we're shutting down
            if self.stop_event.wait(POLL_INTERVAL_SECONDS):
                break

        # Optional: final status for debugging
        self._set_status("Logger stopped")

    def _start_logging_thread(self) -> None:
        """
        Start the logging thread as a non-daemon so that we control
        its lifetime explicitly and can join it on shutdown.
        """
        self.logging_thread = threading.Thread(
            target=self.logging_loop,
            name="BrickDashLogger",
            daemon=False,
        )
        self.logging_thread.start()

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

        # Handle window close event for clean shutdown
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- Shutdown handling ----------

    def initiate_shutdown(self) -> None:
        """
        Signal background work to stop and start GUI teardown.
        Safe to call multiple times.
        """
        if self.stop_event.is_set():
            # Already shutting down
            return

        self.stop_event.set()

        # Stop Matplotlib animation/timers so they don't keep scheduling callbacks
        if hasattr(self, "ani") and self.ani is not None:
            try:
                self.ani.event_source.stop()
            except Exception:
                # Not fatal if this fails; worst case the process exits anyway
                pass

        # Poll for the logging thread to finish without blocking Tk
        self._poll_logger_and_close()

    def _poll_logger_and_close(self) -> None:
        """
        Keep checking the logging thread; when it's done, destroy the root window.
        This avoids blocking the Tk event loop with a blocking join().
        """
        t = self.logging_thread
        if t is not None and t.is_alive():
            # Check again in 50 ms; Tk stays responsive during shutdown
            self.root.after(50, self._poll_logger_and_close)
        else:
            # All background work is done, safe to destroy Tk
            try:
                # Close the Matplotlib figure explicitly to release any global refs
                plt.close(self.fig)
            except Exception:
                pass
            self.root.destroy()

    def _on_close(self) -> None:
        """Handle GUI window close event and shut down cleanly."""
        self._set_status("Shutting down...")
        self.initiate_shutdown()

    # ---------- Plot updating ----------

    def update_plots(self, frame):
        with self.data_lock:
            if len(self.bricks_cut_values) == 0:
                return self.line1, self.line2

            # Plot 1: bricks cut
            recent_vals = self.bricks_cut_values[-MAX_POINTS:]
            x1 = range(len(recent_vals))
            y1 = list(recent_vals)

            # Plot 2: rate per hour
            recent_hour = self.bricks_cut_per_hour[-MAX_POINTS:]
            x2 = range(len(recent_hour))
            y2 = list(recent_hour)

            # Plot 3: 5 minute buckets
            bar_labels = list(self.bricks_per_5min.keys())[-10:]
            bar_data = list(self.bricks_per_5min.values())[-10:]

        # Now update the plots outside the lock so we don't hold it during drawing
        self.line1.set_data(x1, y1)
        self.ax1.set_xlim(0, max(len(y1), 10))
        self.ax1.set_ylim(min(y1) - 1, max(y1) + 1)

        self.line2.set_data(x2, y2)
        self.ax2.set_xlim(0, max(len(y2), 10))
        self.ax2.set_ylim(0, max(y2) + 10 if y2 else 10)

        # 5 minute buckets bar plot
        if bar_labels:
            bar_heights = []
            for bucket_vals in bar_data:
                if len(bucket_vals) > 1:
                    bar_heights.append(
                        (bucket_vals[-1] - bucket_vals[0]) / len(bucket_vals)
                    )
                else:
                    bar_heights.append(0)

            self.ax3.clear()
            self.ax3.bar(range(len(bar_labels)), bar_heights)
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
    try:
        root.mainloop()
    finally:
        # Defensive cleanup in case something bypassed the close handler
        app.stop_event.set()
        t = app.logging_thread
        if t is not None and t.is_alive():
            # Give the logger a short grace period to exit
            t.join(timeout=3)

    # Normal, clean interpreter shutdown (no need for os._exit here)
    sys.exit(0)


if __name__ == "__main__":
    main()
