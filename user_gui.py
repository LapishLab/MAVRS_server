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
from fabric import Connection

from load_settings import load_pi_connections
from path_config import PI_ADDRESS_FILE
from status_checker import PiStatus, RemoteFolderStatus, check_pi_statuses, check_remote_folders
from pi_sysemd import ENV, UNIT
from transfer_data import remote_directories

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
    command = ['sh', '-c', f'{sys.executable} {script_path}; echo "Press enter to close window..."; read dummy']

    if args == ["--command"]:
        terminal_args = [terminal] + args + [" ".join(command)]
    else:
        terminal_args = [terminal] + args + command

    subprocess.Popen(terminal_args, cwd=script_path.parent)


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

def run_user_gui(refresh_interval: int = 100) -> None:
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

    edit_pi_addresses_button = ttk.Button(
        button_frame,
        text="Edit Pi Addresses",
        command=open_pi_addresses_editor,
    )
    edit_pi_addresses_button.pack(side="left", padx=(8, 0))

    tree = ttk.Treeview(frame, columns=("host", "status"), show="headings", height=10)
    tree.heading("host", text="Pi Address")
    tree.heading("status", text="Status")
    tree.column("host", width=260, anchor="w")
    tree.column("status", width=120, anchor="center")
    tree.pack(fill="both", expand=True)

    tree.tag_configure(PiStatus.RUNNING.value, foreground="green")
    tree.tag_configure(PiStatus.REACHABLE.value, foreground="orange")
    tree.tag_configure(PiStatus.UNREACHABLE.value, foreground="red")

    other_tree = ttk.Treeview(frame, columns=("remote", "status"), show="headings", height=6)
    other_tree.heading("remote", text="Remote Folder")
    other_tree.heading("status", text="Status")
    other_tree.column("remote", width=360, anchor="w")
    other_tree.column("status", width=120, anchor="center")
    other_tree.pack(fill="both", expand=True)

    other_tree.tag_configure(RemoteFolderStatus.REACHABLE.value, foreground="green")
    other_tree.tag_configure(RemoteFolderStatus.RSYNC_ERROR.value, foreground="red")
    other_tree.tag_configure(RemoteFolderStatus.UNREACHABLE.value, foreground="red")
    other_tree.tag_configure(RemoteFolderStatus.UNKNOWN_ERROR.value, foreground="red")
    
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

    
    for connection in pi_group:
        tree.insert("", "end", values=(connection.host, "Checking..."), tags=("Checking...",))

    for label, remote_path in remote_directories().items():
        id = f"{label}({remote_path})"
        other_tree.insert("", "end", values=(id, "Checking..."), tags=("Checking...",))

    pi_status_queue: Queue[dict[str, PiStatus]] = Queue()
    other_status_queue: Queue[dict[str, RemoteFolderStatus]] = Queue()
    stop_event = threading.Event()

    def pi_status_worker() -> None:
        while not stop_event.is_set():
            statuses = check_pi_statuses(pi_group)
            pi_status_queue.put(statuses)
            if stop_event.wait(refresh_interval / 1000):
                break

    def other_status_worker() -> None:
        while not stop_event.is_set():
            statuses = check_remote_folders()
            other_status_queue.put(statuses)
            if stop_event.wait(refresh_interval / 1000):
                break

    def process_status_queues() -> None:
        while not pi_status_queue.empty():
            pi_statuses = pi_status_queue.get()
            for item in tree.get_children():
                tree.delete(item)
            for name, status in pi_statuses.items():
                tree.insert("", "end", values=(name, status.value), tags=(status.value,))

        while not other_status_queue.empty():
            other_statuses = other_status_queue.get()
            for item in other_tree.get_children():
                other_tree.delete(item)
            if other_statuses:
                for name, status in other_statuses.items():
                    other_tree.insert("", "end", values=(name, status.value), tags=(status.value,))
            else:
                other_tree.insert("", "end", values=("No remote folders configured", ""))

        if root.winfo_exists():
            root.after(200, process_status_queues)

    def on_closing() -> None:
        stop_event.set()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)

    threading.Thread(target=pi_status_worker, daemon=True).start()
    threading.Thread(target=other_status_worker, daemon=True).start()
    root.after(0, process_status_queues)
    root.mainloop()
def open_pi_addresses_editor() -> None:
    editor_window = tk.Toplevel()
    editor_window.title("Edit Pi Addresses")
    editor_window.geometry("560x420")

    frame = ttk.Frame(editor_window, padding=10)
    frame.pack(fill="both", expand=True)

    label = ttk.Label(
        frame,
        text=f"Edit Pi addresses file: {PI_ADDRESS_FILE}",
        font=("", 10, "bold"),
    )
    label.pack(fill="x", pady=(0, 8))

    # Load file content
    try:
        with open(PI_ADDRESS_FILE, "r") as f:
            raw_lines = f.read().splitlines()
    except FileNotFoundError:
        raw_lines = []
    except Exception as exc:
        raw_lines = [f"# Error reading file: {exc}"]

    # Scrolling frame to hold rows of (checkbox, main, comment)
    rows_container = ttk.Frame(frame)
    rows_container.pack(fill="both", expand=True)

    canvas = tk.Canvas(rows_container)
    v_scroll = ttk.Scrollbar(rows_container, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=v_scroll.set)
    v_scroll.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    inner_frame = ttk.Frame(canvas)
    canvas.create_window((0, 0), window=inner_frame, anchor="nw")

    def _on_canvas_config(event):
        canvas.configure(scrollregion=canvas.bbox("all"))

    inner_frame.bind("<Configure>", _on_canvas_config)

    # Header
    hdr_chk = ttk.Label(inner_frame, text=" ", width=3)
    hdr_main = ttk.Label(inner_frame, text="Address ", width=40, anchor="w")
    hdr_cmt = ttk.Label(inner_frame, text="Comment", width=40, anchor="w")
    hdr_chk.grid(row=0, column=0, padx=3, pady=2)
    hdr_main.grid(row=0, column=1, padx=3, pady=2, sticky="w")
    hdr_cmt.grid(row=0, column=2, padx=3, pady=2, sticky="w")

    # Store row widgets and state
    editor_rows = []  # list of (var, entry_main, entry_comment)

    def parse_line(line: str):
        line = line.strip()
        # Detect commented lines (starting with '#', possibly with leading spaces)
        if line.startswith("#"):
            checked = False
            line = line.lstrip("#").strip()
        else:   
            checked = True
        # Split remaining portion by next instance of '#'
        main, _ ,comment = line.partition('#')
        return checked, main, comment

    def add_row(checked: bool, main: str, comment: str):
        row_idx = len(editor_rows) + 1
        var = tk.IntVar(value=1 if checked else 0)
        chk = tk.Checkbutton(inner_frame, variable=var)
        chk.grid(row=row_idx, column=0, padx=3, pady=2)

        entry_main = ttk.Entry(inner_frame, width=80)
        entry_main.insert(0, main)
        entry_main.grid(row=row_idx, column=1, padx=3, pady=2, sticky="we")

        entry_cmt = ttk.Entry(inner_frame, width=40)
        entry_cmt.insert(0, comment)
        entry_cmt.grid(row=row_idx, column=2, padx=3, pady=2, sticky="we")

        editor_rows.append((var, entry_main, entry_cmt))

    # Populate rows
    for raw in raw_lines:
        if raw.strip():
            checked, main, comment = parse_line(raw)
            add_row(checked, main, comment)

    status_label = ttk.Label(frame, text="")
    status_label.pack(fill="x", pady=(8, 0))

    def build_lines_from_rows():
        out_lines = []
        for var, entry_main, entry_cmt in editor_rows:
            checked = bool(var.get())
            main = entry_main.get().rstrip()
            comment = entry_cmt.get().strip()
            if not main and not comment:
                out_lines.append("")
                continue
            if comment:
                line = f"{main} # {comment}" if main else f"# {comment}"
            else:
                line = main
            if not checked:
                if not line.startswith("#"):
                    line = f"# {line}"
            out_lines.append(line)
        return out_lines

    def save_addresses() -> None:
        try:
            lines = build_lines_from_rows()
            with open(PI_ADDRESS_FILE, "w") as f:
                f.write("\n".join(lines) + "\n")
            status_label.config(text="Saved successfully.")
        except Exception as exc:
            status_label.config(text=f"Failed to save: {exc}")

    button_frame = ttk.Frame(frame)
    button_frame.pack(fill="x", pady=(8, 0))

    add_button = ttk.Button(button_frame, text="Add Row", command=lambda: add_row(True, "", ""))
    save_button = ttk.Button(button_frame, text="Save", command=save_addresses)
    close_button = ttk.Button(button_frame, text="Close", command=editor_window.destroy)
    add_button.pack(side="left")
    save_button.pack(side="left", padx=(8, 0))
    close_button.pack(side="left", padx=(8, 0))

    def on_closing() -> None:
        editor_window.destroy()

    editor_window.protocol("WM_DELETE_WINDOW", on_closing)
    return

def main() -> None:
    run_user_gui()

if __name__ == "__main__":
    main()
