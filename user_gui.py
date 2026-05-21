#!/usr/bin/env python3
import shutil
import subprocess
import sys
from pathlib import Path
import time
import tkinter as tk
from tkinter import ttk
import threading
from queue import Queue
from fabric.group import SerialGroup
from fabric import Connection

from load_settings import load_pi_connections
from status_checker import PiStatus, check_pi_statuses
from pi_sysemd import ENV, UNIT

def find_terminal_emulator():
    candidates = [
        ("x-terminal-emulator", ["-e"]),
        ("gnome-terminal", ["--"]),
        ("konsole", ["-e"]),
        ("xfce4-terminal", ["--command"]),
        ("xterm", ["-e"]),
    ]
    for exe, args in candidates:
        if shutil.which(exe):
            return exe, args
    raise RuntimeError(
        "No terminal emulator found. Install xterm, gnome-terminal, konsole, xfce4-terminal, or x-terminal-emulator."
    )

def launch_script_in_terminal(script_name: str) -> None:
    terminal, args = find_terminal_emulator()
    script_path = Path(__file__).resolve().parent / script_name
    command = [sys.executable, str(script_path)]

    if args == ["--command"]:
        terminal_args = [terminal] + args + [" ".join(command)]
    else:
        terminal_args = [terminal] + args + command

    subprocess.Popen(terminal_args, cwd=script_path.parent)

def get_pi_status_rows(pi_group: SerialGroup):
    hosts = [connection.host for connection in pi_group]
    statuses = check_pi_statuses(pi_group)
    return list(zip(hosts, statuses))

def stream_pi_output(connection: Connection, output_queue: Queue, host: str) -> None:
    """Periodically fetch and stream the systemd journal output from a single Pi."""
    seen_lines = set()
    
    try:
        while True:
            try:
                # Fetch recent journal entries
                result = connection.run(
                    f"{ENV} journalctl --user -u {UNIT}.service --no-pager -n 100",
                    warn=True,
                    hide=True
                )
                
                if hasattr(result, 'stdout') and result.stdout:
                    lines = result.stdout.strip().splitlines()
                    # Send only new lines we haven't seen before
                    for line in lines:
                        if line and line not in seen_lines:
                            output_queue.put((host, line))
                            seen_lines.add(line)
                            # Keep seen_lines from growing too large
                            if len(seen_lines) > 500:
                                # Keep only the last 300 entries
                                seen_lines = set(list(seen_lines)[-300:])

                time.sleep(1)  # Check every second
                
            except Exception as e:
                output_queue.put((host, f"[Error fetching output: {e}]"))
                time.sleep(2)
                
    except Exception as e:
        output_queue.put((host, f"[Error streaming from {host}: {e}]"))

def open_output_stream_window(host: str, connection: Connection) -> None:
    """Open a new window with streaming output for a specific Pi."""
    output_queue: Queue = Queue()
    
    # Create new window
    stream_window = tk.Toplevel()
    stream_window.title(f"Output Stream - {host}")
    stream_window.geometry("800x600")
    
    frame = ttk.Frame(stream_window, padding=8)
    frame.pack(fill="both", expand=True)
    
    # Title label
    title_label = ttk.Label(frame, text=f"Output Stream: {host}", font=("", 11, "bold"))
    title_label.pack(fill="x", pady=(0, 8))
    
    # Text widget with scrollbar
    text_frame = ttk.Frame(frame)
    text_frame.pack(fill="both", expand=True)
    
    scrollbar = ttk.Scrollbar(text_frame)
    scrollbar.pack(side="right", fill="y")
    
    text_widget = tk.Text(
        text_frame,
        wrap="word",
        yscrollcommand=scrollbar.set,
        font=("Courier", 9),
        bg="#f0f0f0"
    )
    text_widget.pack(side="left", fill="both", expand=True)
    scrollbar.config(command=text_widget.yview)
    
    # Status label
    status_label = ttk.Label(frame, text="Streaming...", font=("", 9))
    status_label.pack(fill="x", pady=(8, 0))
    
    def update_output() -> None:
        """Update text widget with queued output."""
        while not output_queue.empty():
            _, line = output_queue.get()
            text_widget.insert("end", line + "\n")
            text_widget.see("end")
            # Keep only last 1000 lines to avoid memory issues
            line_count = int(text_widget.index("end-1c").split(".")[0])
            if line_count > 1000:
                text_widget.delete("1.0", "2.0")
        
        if stream_window.winfo_exists():
            stream_window.after(500, update_output)
    
    def on_closing():
        # Thread will naturally die when window is closed
        stream_window.destroy()
    
    stream_window.protocol("WM_DELETE_WINDOW", on_closing)
    
    # Start streaming thread as daemon so it closes with window
    thread = threading.Thread(
        target=stream_pi_output,
        args=(connection, output_queue, host),
        daemon=True
    )
    thread.start()
    
    # Start updating output
    update_output()

def run_user_gui(refresh_interval: int = 5000) -> None:
    pi_group = load_pi_connections()
    root = tk.Tk()
    root.title("MAVRS User GUI")

    frame = ttk.Frame(root, padding=12)
    frame.pack(fill="both", expand=True)

    button_frame = ttk.Frame(frame)
    button_frame.pack(fill="x", pady=(0, 8))

    start_button = ttk.Button(
        button_frame,
        text="Start Experiment",
        command=lambda: launch_script_in_terminal("start_experiment.py"),
    )
    stop_button = ttk.Button(
        button_frame,
        text="Stop Experiment",
        command=lambda: launch_script_in_terminal("stop_experiment.py"),
    )
    start_button.pack(side="left", padx=(0, 8))
    stop_button.pack(side="left")

    tree = ttk.Treeview(frame, columns=("host", "status"), show="headings", height=10)
    tree.heading("host", text="Pi Host")
    tree.heading("status", text="Status")
    tree.column("host", width=260, anchor="w")
    tree.column("status", width=120, anchor="center")
    tree.pack(fill="both", expand=True)

    tree.tag_configure(PiStatus.RUNNING.value, foreground="green")
    tree.tag_configure(PiStatus.REACHABLE.value, foreground="orange")
    tree.tag_configure(PiStatus.UNREACHABLE.value, foreground="red")

    def on_tree_double_click(event):
        """Open output stream window when a row is double-clicked."""
        item = tree.selection()[0] if tree.selection() else None
        if item:
            values = tree.item(item, "values")
            host = values[0]
            # Find the connection object for this host
            for connection in pi_group:
                if connection.host == host:
                    open_output_stream_window(host, connection)
                    break

    tree.bind("<Double-1>", on_tree_double_click)

    status_label = ttk.Label(frame, text="Last updated: never")
    status_label.pack(fill="x", pady=(8, 0))

    def refresh() -> None:
        rows = get_pi_status_rows(pi_group)
        for item in tree.get_children():
            tree.delete(item)

        for host, status in rows:
            tree.insert("", "end", values=(host, status.value), tags=(status.value,))

        status_label.config(text=f"Last updated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        root.after(refresh_interval, refresh)

    refresh()
    root.mainloop()

def main() -> None:
    run_user_gui()

if __name__ == "__main__":
    main()
