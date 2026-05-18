#!/usr/bin/env python3
import shutil
import subprocess
import sys
from pathlib import Path
import time
import tkinter as tk
from tkinter import ttk
from fabric.group import SerialGroup

from load_settings import load_pi_connections
from status_checker import PiStatus, check_pi_statuses

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
