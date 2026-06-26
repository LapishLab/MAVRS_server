#!/usr/bin/env python3
""" PySide6 GUI scaffold for MAVRS.

Provides:
- Main window with a `QTreeView` for Pi statuses
- Background `QThread` worker that emits status updates
- Log stream window scaffold using `QTextEdit`
- Editor dialog for reading/writing `PI_ADDRESS_FILE`

"""
from __future__ import annotations

import shutil
import sys
import subprocess
import time
from pathlib import Path
from typing import Optional

from fabric import Connection
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtCore import QObject, Signal, Slot, QThread
from PySide6.QtGui import QStandardItemModel, QStandardItem

from config import ENV, UNIT
from load_settings import load_pi_connections
from path_config import PI_ADDRESS_FILE
from status_checker import get_pi_statuses, PiStatus, check_other_folders_statuses, RemoteFolderStatus


def find_terminal_emulator() -> tuple[str, list[str]]:
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


def launch_script_in_terminal(script_path: Path) -> None:
	terminal, args = find_terminal_emulator()
	command = [
		"sh",
		"-c",
		f'{sys.executable} "{script_path}"; echo "Press enter to close window..."; read dummy',
	]
	if args == ["--command"]:
		terminal_args = [terminal] + args + [" ".join(command)]
	else:
		terminal_args = [terminal] + args + command
	subprocess.Popen(terminal_args, cwd=script_path.parent)


class PiStatusWorker(QObject):
	statuses_updated = Signal(dict)
	stopped = False

	@Slot()
	def run(self) -> None:
		"""Continuously fetch real Pi statuses and emit them."""
		# Initially set statuses to unknown (so something displays while waiting for update)
		pi_group = load_pi_connections()
		statuses = {str(c.host): PiStatus.UNKNOWN for c in pi_group}
		self.statuses_updated.emit(statuses)

		# Start update loop
		while not self.stopped:
			try:
				statuses = get_pi_statuses()
				self.statuses_updated.emit(statuses)
			except Exception:
				pass
			time.sleep(2)

	def stop(self) -> None:
		self.stopped = True


class FolderStatusWorker(QObject):
	folder_statuses_updated = Signal(dict)
	stopped = False

	@Slot()
	def run(self) -> None:
		"""Continuously fetch remote folder statuses and emit them."""
		while not self.stopped:
			try:
				folder_statuses = check_other_folders_statuses()
				self.folder_statuses_updated.emit(folder_statuses)
			except Exception:
				pass
			time.sleep(2)

	def stop(self) -> None:
		self.stopped = True


class LogStreamWorker(QObject):
	new_line = Signal(str)
	finished = Signal()

	def __init__(self, connection: Connection, host: str) -> None:
		super().__init__()
		self.connection = connection
		self.host = host
		self.stopped = False
		self._buffer = ""
		self._promise = None

	def write(self, data: str) -> None:
		if isinstance(data, bytes):
			data = data.decode("utf-8", errors="replace")
		self._buffer += data
		while "\n" in self._buffer:
			line, self._buffer = self._buffer.split("\n", 1)
			if line:
				self.new_line.emit(line)

	def flush(self) -> None:
		if self._buffer:
			self.new_line.emit(self._buffer)
			self._buffer = ""

	def isatty(self) -> bool:
		return False

	@Slot()
	def run(self) -> None:
		try:
			self._promise = self.connection.run(
				f"{ENV} journalctl --user -u {UNIT}.service -f --no-pager",
				warn=True,
				hide=True,
				asynchronous=True,
				out_stream=self,
				err_stream=self,
				pty=False,
			)
			# Block until the remote journal stream exits or is cancelled.
			self._promise.join()
		except Exception as exc:
			self.new_line.emit(f"[Error streaming output from {self.host}: {exc}]")
		finally:
			self.finished.emit()

	def stop(self) -> None:
		self.stopped = True
		if self._promise is not None:
			try:
				if hasattr(self._promise, "runner") and hasattr(self._promise.runner, "kill"):
					self._promise.runner.kill()
				else:
					self._promise.join()
			except Exception:
				pass


class LogStreamWindow(QtWidgets.QWidget):
	closed = Signal(str)

	def __init__(self, host: str, connection: Connection, parent: QtWidgets.QWidget | None = None) -> None:
		super().__init__(parent, QtCore.Qt.WindowType.Window)
		self.host = host
		self.connection = connection
		self.setWindowTitle(f"Output Stream - {host}")
		self.resize(800, 600)
		layout = QtWidgets.QVBoxLayout(self)
		self.text = QtWidgets.QTextEdit()
		self.text.setReadOnly(True)
		layout.addWidget(self.text)

		self.worker = LogStreamWorker(connection, host)
		self.worker_thread = QThread(self)
		self.worker.moveToThread(self.worker_thread)
		self.worker.new_line.connect(self.append_line)
		self.worker.finished.connect(self.worker_thread.quit)
		self.worker_thread.started.connect(self.worker.run)
		self.worker_thread.start()

	def append_line(self, line: str) -> None:
		self.text.append(line)
		self.text.ensureCursorVisible()

	def closeEvent(self, event: QtGui.QCloseEvent) -> None:
		self.worker.stop()
		self.worker_thread.quit()
		self.worker_thread.wait(2000)
		self.closed.emit(self.host)
		super().closeEvent(event)


class PiEditorDialog(QtWidgets.QDialog):
	def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
		super().__init__(parent)
		self.setWindowTitle("Edit Pi Addresses")
		self.resize(1400, 700)
		layout = QtWidgets.QVBoxLayout(self)

		self.scroll_area = QtWidgets.QScrollArea()
		self.scroll_area.setWidgetResizable(True)
		self.container = QtWidgets.QWidget()
		self.grid = QtWidgets.QGridLayout(self.container)
		# self.grid.setContentsMargins(8, 8, 8, 8)
		# self.grid.setHorizontalSpacing(10)
		# self.grid.setVerticalSpacing(6)
		self.grid.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
		self.grid.setColumnStretch(1, 1)
		self.grid.setColumnStretch(2, 1)
		self.scroll_area.setWidget(self.container)
		layout.addWidget(self.scroll_area)

		# header row for address editor
		# head_label = QtWidgets.QLabel("")
		address_label = QtWidgets.QLabel("Pi Address")
		comment_label = QtWidgets.QLabel("Comment")
		# head_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop)
		# address_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop)
		# comment_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop)
		font = address_label.font()
		font.setBold(True)
		# head_label.setFont(font)
		address_label.setFont(font)
		comment_label.setFont(font)
		# self.grid.addWidget(head_label, 0, 0)
		self.grid.addWidget(address_label, 0, 1)
		self.grid.addWidget(comment_label, 0, 2)

		# buttons
		btn_layout = QtWidgets.QHBoxLayout()
		self.btn_add = QtWidgets.QPushButton("Add Row")
		self.btn_save = QtWidgets.QPushButton("Save")
		self.btn_close = QtWidgets.QPushButton("Close")
		btn_layout.addWidget(self.btn_add)
		btn_layout.addWidget(self.btn_save)
		btn_layout.addWidget(self.btn_close)
		layout.addLayout(btn_layout)

		self.rows: list[tuple[QtWidgets.QCheckBox, QtWidgets.QLineEdit, QtWidgets.QLineEdit]] = []
		self.btn_add.clicked.connect(self.add_row)
		self.btn_save.clicked.connect(self.save)
		self.btn_close.clicked.connect(self.close)

		self.load_file()

	def load_file(self) -> None:
		p = Path(PI_ADDRESS_FILE)
		lines: list[str] = []
		if p.exists():
			lines = p.read_text().splitlines()
		for line in lines:
			checked, main, comment = self.parse_line(line)
			self.add_row(checked, main, comment)

	def parse_line(self, line: str) -> tuple[bool, str, str]:
		raw = line.strip()
		if raw.startswith("#"):
			checked = False
			raw = raw.lstrip("#").strip()
		else:
			checked = True
		main, _sep, comment = raw.partition('#')
		return checked, main.strip(), comment.strip()

	def add_row(self, checked: bool = True, main: str = "", comment: str = "") -> None:
		row = len(self.rows) + 1
		chk = QtWidgets.QCheckBox()
		chk.setChecked(checked)
		# chk.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
		edt_main = QtWidgets.QLineEdit(main)
		# edt_main.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
		edt_cmt = QtWidgets.QLineEdit(comment)
		# edt_cmt.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
		self.grid.addWidget(chk, row, 0)
		self.grid.addWidget(edt_main, row, 1)
		self.grid.addWidget(edt_cmt, row, 2)
		self.rows.append((chk, edt_main, edt_cmt))

	def save(self) -> None:
		out_lines: list[str] = []
		for chk, edt_main, edt_cmt in self.rows:
			main = edt_main.text().rstrip()
			c = edt_cmt.text().strip()
			if not main and not c:
				out_lines.append("")
				continue
			if c:
				line = f"{main} # {c}" if main else f"# {c}"
			else:
				line = main
			if not chk.isChecked():
				if not line.startswith("#"):
					line = f"# {line}"
			out_lines.append(line)
		Path(PI_ADDRESS_FILE).write_text("\n".join(out_lines) + "\n")


class MainWindow(QtWidgets.QMainWindow):
	def __init__(self) -> None:
		super().__init__()
		self.setWindowTitle("MAVRS server GUI")
		self.resize(1500, 720)

		central = QtWidgets.QWidget()
		self.setCentralWidget(central)
		layout = QtWidgets.QVBoxLayout(central)

		# top buttons
		btn_layout = QtWidgets.QHBoxLayout()
		self.btn_start = QtWidgets.QPushButton("Start Experiment")
		self.btn_stop = QtWidgets.QPushButton("Stop Experiment")
		self.btn_edit = QtWidgets.QPushButton("Edit Pi Addresses")
		btn_layout.addWidget(self.btn_start)
		btn_layout.addWidget(self.btn_stop)
		btn_layout.addWidget(self.btn_edit)
		layout.addLayout(btn_layout)

		# tree view for pi statuses
		self.tree = QtWidgets.QTreeView()
		self.model = QStandardItemModel(0, 2)
		self.model.setHeaderData(0, QtCore.Qt.Orientation.Horizontal, "Pi Address")
		self.model.setHeaderData(1, QtCore.Qt.Orientation.Horizontal, "Status")
		self.tree.setModel(self.model)
		self.tree.setRootIsDecorated(False)
		layout.addWidget(self.tree)

		# set equal initial column widths for the main tree and allow interactive resizing
		head = self.tree.header()
		head.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
		initial_width = int(self.width() / 2)
		self.tree.setColumnWidth(0, initial_width)
		self.tree.setColumnWidth(1, initial_width)

		# other tree (remote folders)
		self.other_tree = QtWidgets.QTreeView()
		self.other_model = QStandardItemModel(0, 2)
		self.other_model.setHeaderData(0, QtCore.Qt.Orientation.Horizontal, "Remote Folder")
		self.other_model.setHeaderData(1, QtCore.Qt.Orientation.Horizontal, "Status")
		self.other_tree.setModel(self.other_model)
		# match behavior for the other tree as well
		other_head = self.other_tree.header()
		other_head.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
		self.other_tree.setColumnWidth(0, initial_width)
		self.other_tree.setColumnWidth(1, initial_width)
		layout.addWidget(self.other_tree)

		self.connections = load_pi_connections()

		# connections
		self.btn_start.clicked.connect(self.start_experiment)
		self.btn_stop.clicked.connect(self.stop_experiment)
		self.btn_edit.clicked.connect(self.open_editor)
		self.tree.doubleClicked.connect(self.open_log_stream)

		# start pi status worker (separate thread)
		self.pi_worker = PiStatusWorker()
		self.pi_thread = QThread()
		self.pi_worker.moveToThread(self.pi_thread)
		self.pi_thread.started.connect(self.pi_worker.run)
		self.pi_worker.statuses_updated.connect(self.update_statuses)
		self.pi_thread.start()

		# start folder status worker (separate thread)
		self.folder_worker = FolderStatusWorker()
		self.folder_thread = QThread()
		self.folder_worker.moveToThread(self.folder_thread)
		self.folder_thread.started.connect(self.folder_worker.run)
		self.folder_worker.folder_statuses_updated.connect(self.update_folder_statuses)
		self.folder_thread.start()

		self.log_windows: dict[str, LogStreamWindow] = {}

	@Slot(dict)
	def update_statuses(self, statuses: dict) -> None:
		self.model.removeRows(0, self.model.rowCount())
		for host, status in statuses.items():
			host_item = QStandardItem(host)
			status_item = QStandardItem(status.value)
			# color by status (compare against PiStatus enum)
			if status == PiStatus.RUNNING:
				status_item.setForeground(QtGui.QBrush(QtGui.QColor("green")))
			elif status == PiStatus.REACHABLE:
				status_item.setForeground(QtGui.QBrush(QtGui.QColor("orange")))
			else:
				status_item.setForeground(QtGui.QBrush(QtGui.QColor("red")))
			self.model.appendRow([host_item, status_item])

	def update_folder_statuses(self, folder_statuses: dict) -> None:
		self.other_model.removeRows(0, self.other_model.rowCount())
		for folder_id, status in folder_statuses.items():
			folder_item = QStandardItem(folder_id)
			status_item = QStandardItem(status.value)
			# color by status
			if status == RemoteFolderStatus.REACHABLE:
				status_item.setForeground(QtGui.QBrush(QtGui.QColor("green")))
			elif status == RemoteFolderStatus.RSYNC_ERROR:
				status_item.setForeground(QtGui.QBrush(QtGui.QColor("orange")))
			else:
				status_item.setForeground(QtGui.QBrush(QtGui.QColor("red")))
			self.other_model.appendRow([folder_item, status_item])

	def open_log_stream(self, index: QtCore.QModelIndex) -> None:
		host = self.model.item(index.row(), 0).text()
		if host in self.log_windows:
			self.log_windows[host].raise_()
			return

		connection = next((c for c in self.connections if c.host == host), None)
		if connection is None:
			QtWidgets.QMessageBox.warning(self, "Log Stream", f"No connection found for host: {host}")
			return

		win = LogStreamWindow(host, connection)
		win.closed.connect(self._on_log_window_closed)
		self.log_windows[host] = win
		win.show()

	def _on_log_window_closed(self, host: str) -> None:
		self.log_windows.pop(host, None)

	def start_experiment(self) -> None:
		script_path = Path(__file__).resolve().parent / "start_experiment.py"
		try:
			launch_script_in_terminal(script_path)
		except Exception as exc:
			QtWidgets.QMessageBox.critical(self, "Error", f"Failed to start experiment: {exc}")

	def stop_experiment(self) -> None:
		script_path = Path(__file__).resolve().parent / "stop_experiment.py"
		try:
			launch_script_in_terminal(script_path)
		except Exception as exc:
			QtWidgets.QMessageBox.critical(self, "Error", f"Failed to stop experiment: {exc}")

	def open_editor(self) -> None:
		dlg = PiEditorDialog(self)
		dlg.exec()

	def closeEvent(self, event: QtGui.QCloseEvent) -> None:
		# stop status worker threads cleanly
		self.pi_worker.stop()
		self.pi_thread.quit()
		self.pi_thread.wait(2000)

		self.folder_worker.stop()
		self.folder_thread.quit()
		self.folder_thread.wait(2000)

		# close any open log streaming windows cleanly
		for win in list(self.log_windows.values()):
			win.close()
		super().closeEvent(event)


def main() -> None:
	app = QtWidgets.QApplication(sys.argv)

	# Increase the default application font size for better readability.
	# If the point size is not available, fall back to a sensible default.
	font = app.font()
	ps = font.pointSize()
	if ps is None or ps <= 0:
		ps = font.pixelSize()
		if ps is None or ps <= 0:
			ps = 10
		font.setPointSize(int(ps * 2))
	else:
		font.setPointSize(max(8, int(ps * 2)))
	app.setFont(font)

	win = MainWindow()
	win.show()
	sys.exit(app.exec())


if __name__ == "__main__":
	main()
