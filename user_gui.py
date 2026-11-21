#!/usr/bin/env python3
""" PySide6 GUI scaffold for MAVRS.

Provides:
- Main window with a `QTreeView` for Pi statuses
- Background `QThread` worker that emits status updates
- Log stream window scaffold using `QTextEdit`
- Editor dialog for reading/writing `PI_ADDRESS_FILE`

"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional

from fabric import Connection
from pydantic import ValidationError
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtCore import QObject, Signal, Slot, QThread
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtWidgets import QApplication

from config import ENV, UNIT
from data_paths import (
	read_data_paths,
	read_repair_videos_on_stop,
	save_data_paths,
	save_repair_videos_on_stop,
)
from load_settings import load_pi_connections
from locations import Location
from path_config import PI_ADDRESS_FILE, EXPERIMENT_NAMES_FILE, PI_SETTINGS_FILE
from status_checker import get_pi_statuses, PiHealth, PiStatus, check_other_folders_statuses, RemoteFolderStatus
from terminal_launcher import launch_script_in_terminal
from transfer_data import copy_to_pi_home

def format_settings_validation_errors(error: ValidationError) -> str:
	field_names = {
		"local_data_path": "Local data path",
		"backup_data_path": "Backup data path",
		"other_folders": "Other folders",
		"suggested_name_format": "Session name format",
		"repair_videos_on_stop": "Repair video timestamps",
	}
	messages = []
	for issue in error.errors():
		location = issue["loc"]
		field = str(location[0]) if location else "Settings"
		label = field_names.get(field, field)
		if len(location) > 1:
			label += f" ({', '.join(str(part) for part in location[1:])})"
		message = issue["msg"].removeprefix("Value error, ")
		message = message.removeprefix(f"{field} ")
		messages.append(f"{label}: {message}")
	return "\n".join(messages)


def show_pi_settings_results(
	parent: QtWidgets.QWidget, results: list[tuple[Location, str | None]]
) -> None:
	if not results:
		QtWidgets.QMessageBox.information(parent, "Pi Settings", "No enabled Pis were found.")
		return
	failures = [(pi, error) for pi, error in results if error is not None]
	if failures:
		copied = len(results) - len(failures)
		details = "\n".join(f"{pi}: {error}" for pi, error in failures)
		QtWidgets.QMessageBox.warning(
			parent, "Pi Settings", f"Copied settings to {copied} of {len(results)} Pis.\n\nFailed:\n{details}"
		)
	else:
		QtWidgets.QMessageBox.information(parent, "Pi Settings", f"Copied settings to all {len(results)} Pis.")


def relative_window_size(rel_width: float, rel_height: float) -> tuple[int, int]:
	screen = QApplication.primaryScreen()
	screen_geometry = screen.availableGeometry()
	width = int(screen_geometry.width() * rel_width)
	height = int(screen_geometry.height() * rel_height)
	return width, height


def apply_dark_theme(app: QtWidgets.QApplication) -> None:
	"""Apply a simple dark Fusion theme to the QApplication."""
	app.setStyle("Fusion")
	palette = QtGui.QPalette()
	palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(53, 53, 53))
	palette.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor(220, 220, 220))
	palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(35, 35, 35))
	palette.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor(53, 53, 53))
	palette.setColor(QtGui.QPalette.ColorRole.ToolTipBase, QtGui.QColor(255, 255, 220))
	palette.setColor(QtGui.QPalette.ColorRole.ToolTipText, QtGui.QColor(0, 0, 0))
	palette.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor(220, 220, 220))
	palette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor(53, 53, 53))
	palette.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor(220, 220, 220))
	palette.setColor(QtGui.QPalette.ColorRole.BrightText, QtGui.QColor(255, 0, 0))
	palette.setColor(QtGui.QPalette.ColorRole.Link, QtGui.QColor(42, 130, 218))
	palette.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(42, 130, 218))
	palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor(0, 0, 0))
	app.setPalette(palette)
	# Slight stylesheet to improve contrast for disabled controls
	app.setStyleSheet("QToolTip { color: #000000; background-color: #ffffdc; border: 1px solid black; }")

def stop_thread(thread: QThread | None, worker: QObject | None = None, timeout_ms: int = 5000) -> None:
	if thread is None or not thread.isRunning():
		return
	if worker is not None:
		try:
			# Call stop() if the worker implements it (worker typed as QObject so static
			# check may not know about stop). Use getattr to avoid attribute errors.
			if hasattr(worker, "stop"):
				getattr(worker, "stop")()
		except Exception:
			pass
	thread.quit()
	if not thread.wait(timeout_ms):
		try:
			thread.terminate()
		except Exception:
			pass
		thread.wait(max(1000, timeout_ms // 2))


class PiStatusWorker(QObject):
	statuses_updated = Signal(dict)
	stopped = False

	@Slot()
	def run(self) -> None:
		"""Continuously fetch real Pi statuses and emit them."""
		# Initially set statuses to unknown (so something displays while waiting for update)
		pi_group = load_pi_connections()
		statuses = {str(c.host): PiHealth(PiStatus.UNKNOWN) for c in pi_group}
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
				f"{ENV} journalctl --user-unit={UNIT}.service -f --no-pager",
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
		self.resize(*relative_window_size(0.5, 0.6))
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
		self.hide()
		event.accept()
		QtCore.QTimer.singleShot(0, self._shutdown)

	def _shutdown(self) -> None:
		self.worker.stop()
		stop_thread(self.worker_thread, self.worker, 5000)
		self.closed.emit(self.host)


class PiEditorDialog(QtWidgets.QDialog):
	def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
		super().__init__(parent)
		self.setWindowTitle("Edit Pi Addresses")
		self.resize(*relative_window_size(0.5, 0.6))
		layout = QtWidgets.QVBoxLayout(self)

		self.scroll_area = QtWidgets.QScrollArea()
		self.scroll_area.setWidgetResizable(True)
		self.container = QtWidgets.QWidget()
		self.grid = QtWidgets.QGridLayout(self.container)
		self.grid.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
		self.grid.setColumnStretch(1, 1)
		self.grid.setColumnStretch(2, 1)
		self.scroll_area.setWidget(self.container)
		layout.addWidget(self.scroll_area)

		# header row for address editor
		address_label = QtWidgets.QLabel("Pi Address")
		comment_label = QtWidgets.QLabel("Comment")
		font = address_label.font()
		font.setBold(True)
		address_label.setFont(font)
		comment_label.setFont(font)
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

	@staticmethod
	def parse_line(line: str) -> tuple[bool, str, str]:
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
		edt_main = QtWidgets.QLineEdit(main)
		edt_cmt = QtWidgets.QLineEdit(comment)
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


class ExperimentNameEditorDialog(QtWidgets.QDialog):
	def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
		super().__init__(parent)
		self.setWindowTitle("Edit Experiment Names")
		self.resize(*relative_window_size(0.5, 0.6))
		layout = QtWidgets.QVBoxLayout(self)

		self.scroll_area = QtWidgets.QScrollArea()
		self.scroll_area.setWidgetResizable(True)
		self.container = QtWidgets.QWidget()
		self.grid = QtWidgets.QGridLayout(self.container)
		self.grid.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
		self.grid.setColumnStretch(1, 1)
		self.grid.setColumnStretch(2, 1)
		self.scroll_area.setWidget(self.container)
		layout.addWidget(self.scroll_area)

		name_label = QtWidgets.QLabel("Experiment Name")
		comment_label = QtWidgets.QLabel("Comment")
		font = name_label.font()
		font.setBold(True)
		name_label.setFont(font)
		comment_label.setFont(font)
		self.grid.addWidget(name_label, 0, 1)
		self.grid.addWidget(comment_label, 0, 2)

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
		p = Path(EXPERIMENT_NAMES_FILE)
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
		edt_main = QtWidgets.QLineEdit(main)
		edt_cmt = QtWidgets.QLineEdit(comment)
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
		Path(EXPERIMENT_NAMES_FILE).write_text("\n".join(out_lines) + "\n")


class AutomatedDataProcessingDialog(QtWidgets.QDialog):
	def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
		super().__init__(parent)
		self.setWindowTitle("Automated Data Processing")
		layout = QtWidgets.QVBoxLayout(self)

		self.repair_video_timestamps = QtWidgets.QCheckBox("Repair video timestamps")
		self.repair_video_timestamps.setChecked(read_repair_videos_on_stop())
		layout.addWidget(self.repair_video_timestamps)

		buttons = QtWidgets.QHBoxLayout()
		self.btn_save = QtWidgets.QPushButton("Save")
		self.btn_close = QtWidgets.QPushButton("Close")
		buttons.addStretch()
		buttons.addWidget(self.btn_save)
		buttons.addWidget(self.btn_close)
		layout.addLayout(buttons)
		self.btn_save.clicked.connect(self.save)
		self.btn_close.clicked.connect(self.reject)

	def save(self) -> None:
		try:
			save_repair_videos_on_stop(self.repair_video_timestamps.isChecked())
		except ValidationError as exc:
			QtWidgets.QMessageBox.warning(self, "Invalid Settings", format_settings_validation_errors(exc))
			return
		except Exception as exc:
			QtWidgets.QMessageBox.critical(self, "Automated Data Processing", f"Failed to save settings: {exc}")
			return
		self.accept()


class DataPathsDialog(QtWidgets.QDialog):
	def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
		super().__init__(parent)
		self.setWindowTitle("Data Paths")
		self.resize(*relative_window_size(0.6, 0.6))
		layout = QtWidgets.QVBoxLayout(self)

		paths = QtWidgets.QFormLayout()
		self.local_path = QtWidgets.QLineEdit()
		self.backup_path = QtWidgets.QLineEdit()
		self.suggested_name_format = QtWidgets.QLineEdit()
		self.backup_path.setPlaceholderText("Leave blank if no backup destination is configured")
		paths.addRow("Local data path", self.local_path)
		paths.addRow("Backup data path", self.backup_path)
		paths.addRow("Session Name Format", self.suggested_name_format)
		layout.addLayout(paths)

		folder_group = QtWidgets.QGroupBox("Other Folders")
		folder_layout = QtWidgets.QVBoxLayout(folder_group)
		headers = QtWidgets.QHBoxLayout()
		headers.addWidget(QtWidgets.QLabel("Folder name"), 1)
		headers.addWidget(QtWidgets.QLabel("Path (blank uses local data path)"), 2)
		headers.addSpacing(80)
		folder_layout.addLayout(headers)
		self.folder_scroll = QtWidgets.QScrollArea()
		self.folder_scroll.setWidgetResizable(True)
		self.folder_container = QtWidgets.QWidget()
		self.folder_rows_layout = QtWidgets.QVBoxLayout(self.folder_container)
		self.folder_rows_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
		self.folder_scroll.setWidget(self.folder_container)
		folder_layout.addWidget(self.folder_scroll)
		layout.addWidget(folder_group)

		buttons = QtWidgets.QHBoxLayout()
		self.btn_add_folder = QtWidgets.QPushButton("Add Folder")
		self.btn_save = QtWidgets.QPushButton("Save")
		self.btn_close = QtWidgets.QPushButton("Close")
		buttons.addWidget(self.btn_add_folder)
		buttons.addStretch()
		buttons.addWidget(self.btn_save)
		buttons.addWidget(self.btn_close)
		layout.addLayout(buttons)

		self.folder_rows: list[tuple[QtWidgets.QWidget, QtWidgets.QLineEdit, QtWidgets.QLineEdit]] = []
		self.btn_add_folder.clicked.connect(lambda: self.add_folder_row())
		self.btn_save.clicked.connect(self.save)
		self.btn_close.clicked.connect(self.reject)

		local_path, backup_path, folders, suggested_name_format = read_data_paths()
		self.local_path.setText(local_path)
		self.backup_path.setText(backup_path or "")
		self.suggested_name_format.setText(suggested_name_format)
		for name, path in folders.items():
			self.add_folder_row(name, path or "")

	def add_folder_row(self, name: str = "", path: str = "") -> None:
		row = QtWidgets.QWidget()
		row_layout = QtWidgets.QHBoxLayout(row)
		row_layout.setContentsMargins(0, 0, 0, 0)
		name_edit = QtWidgets.QLineEdit(name)
		path_edit = QtWidgets.QLineEdit(path)
		remove_button = QtWidgets.QPushButton("Remove")
		row_layout.addWidget(name_edit, 1)
		row_layout.addWidget(path_edit, 2)
		row_layout.addWidget(remove_button)
		self.folder_rows_layout.addWidget(row)
		self.folder_rows.append((row, name_edit, path_edit))
		remove_button.clicked.connect(lambda: self.remove_folder_row(row))

	def remove_folder_row(self, row: QtWidgets.QWidget) -> None:
		self.folder_rows = [entry for entry in self.folder_rows if entry[0] is not row]
		self.folder_rows_layout.removeWidget(row)
		row.deleteLater()

	def save(self) -> None:
		folders: dict[str, str | None] = {}
		for _, name_edit, path_edit in self.folder_rows:
			name = name_edit.text().strip()
			path = path_edit.text()
			if not name and not path:
				continue
			if not name or name in folders:
				QtWidgets.QMessageBox.warning(self, "Other Folders", "Each folder needs a unique name.")
				return
			folders[name] = path or None
		try:
			save_data_paths(
				self.local_path.text(),
				self.backup_path.text() or None,
				folders,
				self.suggested_name_format.text(),
			)
		except ValidationError as exc:
			QtWidgets.QMessageBox.warning(self, "Invalid Data Paths", format_settings_validation_errors(exc))
			return
		except Exception as exc:
			QtWidgets.QMessageBox.critical(self, "Data Paths", f"Failed to save settings: {exc}")
			return
		self.accept()


class PiFleetSettingsDialog(QtWidgets.QDialog):
	def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
		super().__init__(parent)
		self.setWindowTitle("Pi fleet Settings")
		self.resize(*relative_window_size(0.4, 0.5))
		layout = QtWidgets.QVBoxLayout(self)

		self.btn_open_file = QtWidgets.QPushButton("Open settings file in editor")
		layout.addWidget(self.btn_open_file)

		scroll = QtWidgets.QScrollArea()
		scroll.setWidgetResizable(True)
		container = QtWidgets.QWidget()
		grid = QtWidgets.QGridLayout(container)
		grid.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
		grid.setColumnStretch(1, 1)
		grid.setColumnStretch(2, 1)
		self.select_all_checkbox = QtWidgets.QCheckBox()
		self.select_all_checkbox.setToolTip("Select or clear all Pi addresses")
		grid.addWidget(self.select_all_checkbox, 0, 0)
		address_label = QtWidgets.QLabel("Pi Address")
		comment_label = QtWidgets.QLabel("Comment")
		font = address_label.font()
		font.setBold(True)
		address_label.setFont(font)
		comment_label.setFont(font)
		grid.addWidget(address_label, 0, 1)
		grid.addWidget(comment_label, 0, 2)

		self.pi_checkboxes: list[tuple[Location, QtWidgets.QCheckBox]] = []
		lines = PI_ADDRESS_FILE.read_text().splitlines() if PI_ADDRESS_FILE.exists() else []
		for row, line in enumerate(lines, start=1):
			active, address, comment = PiEditorDialog.parse_line(line)
			checkbox = QtWidgets.QCheckBox()
			try:
				pi = Location(address) if address else None
			except ValueError:
				pi = None
			if pi is None or pi.host is None:
				checkbox.setEnabled(False)
				checkbox.setToolTip("Not a valid Pi address")
			else:
				checkbox.setChecked(active)
				self.pi_checkboxes.append((pi, checkbox))
			address_field = QtWidgets.QLineEdit(address)
			address_field.setReadOnly(True)
			comment_field = QtWidgets.QLineEdit(comment)
			comment_field.setReadOnly(True)
			grid.addWidget(checkbox, row, 0)
			grid.addWidget(address_field, row, 1)
			grid.addWidget(comment_field, row, 2)
		if not lines:
			grid.addWidget(QtWidgets.QLabel("No Pi addresses are configured."), 1, 1, 1, 2)
		self.select_all_checkbox.setEnabled(bool(self.pi_checkboxes))
		self.select_all_checkbox.setChecked(
			bool(self.pi_checkboxes) and all(checkbox.isChecked() for _, checkbox in self.pi_checkboxes)
		)
		scroll.setWidget(container)
		layout.addWidget(scroll)

		self.btn_deploy = QtWidgets.QPushButton("Deploy settings to selected Pis")
		self.btn_deploy.setEnabled(any(checkbox.isChecked() for _, checkbox in self.pi_checkboxes))
		layout.addWidget(self.btn_deploy)
		self.status_label = QtWidgets.QLabel()
		layout.addWidget(self.status_label)
		self.btn_close = QtWidgets.QPushButton("Close")
		layout.addWidget(self.btn_close)

		self.btn_open_file.clicked.connect(self.open_settings_file)
		self.btn_deploy.clicked.connect(self.deploy_settings)
		self.btn_close.clicked.connect(self.close)
		self.select_all_checkbox.toggled.connect(self.set_all_pis_selected)
		for _, checkbox in self.pi_checkboxes:
			checkbox.toggled.connect(self.update_selection_state)

	def set_all_pis_selected(self, selected: bool) -> None:
		for _, checkbox in self.pi_checkboxes:
			checkbox.setChecked(selected)

	def update_selection_state(self) -> None:
		selected = [checkbox.isChecked() for _, checkbox in self.pi_checkboxes]
		self.btn_deploy.setEnabled(any(selected))
		was_blocked = self.select_all_checkbox.blockSignals(True)
		self.select_all_checkbox.setChecked(bool(selected) and all(selected))
		self.select_all_checkbox.blockSignals(was_blocked)

	def open_settings_file(self) -> None:
		try:
			url = QtCore.QUrl.fromLocalFile(str(PI_SETTINGS_FILE))
			if not QtGui.QDesktopServices.openUrl(url):
				raise RuntimeError(f"No application could open {PI_SETTINGS_FILE}")
		except Exception as exc:
			QtWidgets.QMessageBox.critical(self, "Pi Settings", f"Failed to open Pi settings: {exc}")

	def deploy_settings(self) -> None:
		selected = [pi for pi, checkbox in self.pi_checkboxes if checkbox.isChecked()]
		if not selected:
			return
		self.btn_deploy.setEnabled(False)
		self.status_label.setText(f"Deploying settings to {len(selected)} Pis...")
		QApplication.processEvents()
		try:
			results = copy_to_pi_home(selected)
		except Exception as exc:
			QtWidgets.QMessageBox.critical(self, "Pi Settings", f"Failed to deploy settings: {exc}")
		else:
			show_pi_settings_results(self, results)
		finally:
			self.status_label.clear()
			self.update_selection_state()


class MainWindow(QtWidgets.QMainWindow):
	def __init__(self) -> None:
		super().__init__()
		self.setWindowTitle("MAVRS server GUI")
		self.resize(*relative_window_size(0.5, 0.6))

		tabs = QtWidgets.QTabWidget()
		self.setCentralWidget(tabs)
		main_tab = QtWidgets.QWidget()
		tabs.addTab(main_tab, "Main")
		layout = QtWidgets.QVBoxLayout(main_tab)
		preferences_tab = QtWidgets.QWidget()
		tabs.addTab(preferences_tab, "Preferences")
		preferences_layout = QtWidgets.QVBoxLayout(preferences_tab)

		# top buttons
		btn_layout = QtWidgets.QHBoxLayout()
		self.btn_start = QtWidgets.QPushButton("Start Experiment")
		self.btn_stop = QtWidgets.QPushButton("Stop Experiment")
		self.btn_backup = QtWidgets.QPushButton("Backup Data")
		btn_layout.addWidget(self.btn_start)
		btn_layout.addWidget(self.btn_stop)
		btn_layout.addWidget(self.btn_backup)
		layout.addLayout(btn_layout)

		self.btn_edit = QtWidgets.QPushButton("Pi Addresses")
		self.btn_edit_experiments = QtWidgets.QPushButton("Experiment Names")
		self.btn_data_paths = QtWidgets.QPushButton("Data Paths")
		self.btn_automated_data_processing = QtWidgets.QPushButton("Automated Data Processing")
		self.btn_pi_settings = QtWidgets.QPushButton("Pi fleet Settings")
		preferences_layout.addWidget(self.btn_data_paths)
		preferences_layout.addWidget(self.btn_automated_data_processing)
		preferences_layout.addWidget(self.btn_edit)
		preferences_layout.addWidget(self.btn_edit_experiments)
		preferences_layout.addWidget(self.btn_pi_settings)
		preferences_layout.addStretch()

		# tree view for pi statuses
		self.tree = QtWidgets.QTreeView()
		self.model = QStandardItemModel(0, 2)
		self.model.setHeaderData(0, QtCore.Qt.Orientation.Horizontal, "Pi Address")
		self.model.setHeaderData(1, QtCore.Qt.Orientation.Horizontal, "Status")
		self.tree.setModel(self.model)
		self.tree.setRootIsDecorated(True)
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
		self.btn_backup.clicked.connect(self.backup_data)
		self.btn_edit.clicked.connect(self.open_editor)
		self.btn_edit_experiments.clicked.connect(self.open_experiment_name_editor)
		self.btn_data_paths.clicked.connect(self.open_data_paths)
		self.btn_automated_data_processing.clicked.connect(self.open_automated_data_processing)
		self.btn_pi_settings.clicked.connect(self.open_pi_settings)
		self.tree.doubleClicked.connect(self.open_log_stream)

		# start pi status worker (separate thread)
		self.pi_worker = PiStatusWorker()
		self.pi_thread = QThread(self)
		self.pi_worker.moveToThread(self.pi_thread)
		self.pi_thread.started.connect(self.pi_worker.run)
		self.pi_worker.statuses_updated.connect(self.update_statuses)
		self.pi_thread.start()

		# start folder status worker (separate thread)
		self.folder_worker = FolderStatusWorker()
		self.folder_thread = QThread(self)
		self.folder_worker.moveToThread(self.folder_thread)
		self.folder_thread.started.connect(self.folder_worker.run)
		self.folder_worker.folder_statuses_updated.connect(self.update_folder_statuses)
		self.folder_thread.start()

		self.log_windows: dict[str, LogStreamWindow] = {}

	@Slot(dict)
	def update_statuses(self, statuses: dict) -> None:
		expanded_hosts = {
			self.model.item(row, 0).text()
			for row in range(self.model.rowCount())
			if self.tree.isExpanded(self.model.index(row, 0))
		}
		self.model.removeRows(0, self.model.rowCount())
		for host, health in statuses.items():
			host_item = QStandardItem(host)
			status_item = QStandardItem(health.summary)
			# color by status (compare against PiStatus enum)
			if health.status == PiStatus.RUNNING:
				status_item.setForeground(QtGui.QBrush(QtGui.QColor("turquoise")))
			elif health.status == PiStatus.STOPPED:
				status_item.setForeground(QtGui.QBrush(QtGui.QColor("green")))
			elif health.status in (PiStatus.STARTING, PiStatus.PARTIAL_FAILURE, PiStatus.UNKNOWN):
				status_item.setForeground(QtGui.QBrush(QtGui.QColor("orange")))
			else:
				status_item.setForeground(QtGui.QBrush(QtGui.QColor("red")))
			self.model.appendRow([host_item, status_item])
			for component, detail in health.components.items():
				component_item = QStandardItem(component)
				component_status = QStandardItem(detail["state"])
				if detail["state"] in ("failed", "stopped"):
					component_status.setForeground(QtGui.QBrush(QtGui.QColor("red")))
					reason = detail.get("reason")
					exit_code = detail.get("exit_code")
					component_status.setToolTip(f"{reason or 'Recorder exited'}; exit code: {exit_code}")
				elif detail["state"] == "starting":
					component_status.setForeground(QtGui.QBrush(QtGui.QColor("orange")))
				else:
					component_status.setForeground(QtGui.QBrush(QtGui.QColor("turquoise")))
				host_item.appendRow([component_item, component_status])
			if host in expanded_hosts:
				self.tree.expand(self.model.index(self.model.rowCount() - 1, 0))

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
		if index.parent().isValid():
			index = index.parent()
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

	def backup_data(self) -> None:
		script_path = Path(__file__).resolve().parent / "backup_data.py"
		try:
			launch_script_in_terminal(script_path)
		except Exception as exc:
			QtWidgets.QMessageBox.critical(self, "Error", f"Failed to start backup: {exc}")

	def open_editor(self) -> None:
		dlg = PiEditorDialog(self)
		dlg.exec()

	def open_experiment_name_editor(self) -> None:
		dlg = ExperimentNameEditorDialog(self)
		dlg.exec()

	def open_data_paths(self) -> None:
		try:
			dlg = DataPathsDialog(self)
			dlg.exec()
		except Exception as exc:
			QtWidgets.QMessageBox.critical(self, "Data Paths", f"Failed to open settings: {exc}")

	def open_automated_data_processing(self) -> None:
		try:
			dlg = AutomatedDataProcessingDialog(self)
			dlg.exec()
		except Exception as exc:
			QtWidgets.QMessageBox.critical(self, "Automated Data Processing", f"Failed to open settings: {exc}")

	def open_pi_settings(self) -> None:
		try:
			dlg = PiFleetSettingsDialog(self)
			dlg.exec()
		except Exception as exc:
			QtWidgets.QMessageBox.critical(self, "Pi Settings", f"Failed to open Pi fleet settings: {exc}")

	def closeEvent(self, event: QtGui.QCloseEvent) -> None:
		self.hide()
		event.accept()
		QtCore.QTimer.singleShot(0, self._shutdown_workers)

	def _shutdown_workers(self) -> None:
		for win in list(self.log_windows.values()):
			win.close()
		stop_thread(self.pi_thread, self.pi_worker)
		stop_thread(self.folder_thread, self.folder_worker)
		app = QtWidgets.QApplication.instance()
		if app is not None:
			app.quit()


def main() -> None:
	app = QtWidgets.QApplication(sys.argv)
	apply_dark_theme(app)
	win = MainWindow()
	win.show()
	sys.exit(app.exec())


if __name__ == "__main__":
	main()
