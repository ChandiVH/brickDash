import tkinter as tk
from tkinter import ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

# Create main app window
root = tk.Tk()
root.title("Brick Cutting Monitor")
root.geometry("1000x800")

# Create a frame for the plot
plot_frame = ttk.Frame(root)
plot_frame.pack(fill=tk.BOTH, expand=True)

# Matplotlib Figure
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 8))
fig.tight_layout()

# Embed matplotlib figure in Tkinter
canvas = FigureCanvasTkAgg(fig, master=plot_frame)
canvas.draw()
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

# # Controls (buttons, labels etc.)
# control_frame = ttk.Frame(root)
# control_frame.pack(pady=10)
#
# start_btn = ttk.Button(control_frame, text="Start Monitoring")
# start_btn.pack(side=tk.LEFT, padx=5)
#
# stop_btn = ttk.Button(control_frame, text="Stop Monitoring")
# stop_btn.pack(side=tk.LEFT, padx=5)
#
# status_label = ttk.Label(control_frame, text="Status: Waiting...")
# status_label.pack(side=tk.LEFT, padx=10)

root.mainloop()