"""
gui.py — Modern PyQt6 Desktop GUI for Onboarding, Settings, and Real-Time Logs.

Features:
  • Discord-inspired dark design system (QSS)
  • First-Run Guided Setup Wizard (QDialog)
  • Full-Featured Settings Window (QMainWindow)
  • Live Real-Time Terminal & Process Log Streaming
  • Copy-to-Clipboard & Log File Export
"""

import logging
import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QColor, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QCheckBox,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QListWidget,
    QPlainTextEdit,
    QFileDialog,
    QMessageBox,
    QFrame,
)

from config import (
    load_config,
    save_config,
    validate_app_id,
    is_autostart_enabled,
    set_autostart_enabled,
    CONFIG_PATH,
)
from icons import clear_icon_cache

logger = logging.getLogger("autorpc.gui")
BASE_DIR = Path(__file__).resolve().parent
LOG_PATH = BASE_DIR / "autorpc.log"
ICON_PATH = BASE_DIR / "assets" / "icon.png"

# ---------------------------------------------------------------------------
# Modern Discord Dark Theme QSS
# ---------------------------------------------------------------------------

DISCORD_DARK_QSS = """
QWidget {
    background-color: #1E1F22;
    color: #F2F3F5;
    font-family: 'Segoe UI', system-ui, sans-serif;
    font-size: 13px;
}

/* Tab Widget */
QTabWidget::pane {
    border: 1px solid #383A40;
    background-color: #2B2D31;
    border-radius: 8px;
    padding: 10px;
}
QTabBar::tab {
    background-color: #1E1F22;
    color: #949BA4;
    padding: 8px 16px;
    margin-right: 4px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: bold;
}
QTabBar::tab:selected {
    background-color: #2B2D31;
    color: #F2F3F5;
    border-bottom: 2px solid #5865F2;
}
QTabBar::tab:hover:!selected {
    background-color: #2B2D31;
    color: #DBDEE1;
}

/* Buttons */
QPushButton {
    background-color: #4E5058;
    color: #FFFFFF;
    border: none;
    border-radius: 5px;
    padding: 7px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #6D6F78;
}
QPushButton:pressed {
    background-color: #383A40;
}
QPushButton#PrimaryBtn {
    background-color: #5865F2;
}
QPushButton#PrimaryBtn:hover {
    background-color: #4752C4;
}
QPushButton#PrimaryBtn:pressed {
    background-color: #3C45A5;
}
QPushButton#SuccessBtn {
    background-color: #23A55A;
}
QPushButton#SuccessBtn:hover {
    background-color: #1E8E4D;
}
QPushButton#DangerBtn {
    background-color: #DA373C;
}
QPushButton#DangerBtn:hover {
    background-color: #BA2D31;
}

/* Inputs & Spinners */
QLineEdit, QSpinBox {
    background-color: #313338;
    color: #F2F3F5;
    border: 1px solid #383A40;
    border-radius: 5px;
    padding: 6px 10px;
    selection-background-color: #5865F2;
}
QLineEdit:focus, QSpinBox:focus {
    border: 1px solid #5865F2;
}

/* Checkboxes */
QCheckBox {
    color: #F2F3F5;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #4E5058;
    background-color: #313338;
}
QCheckBox::indicator:checked {
    background-color: #5865F2;
    border-color: #5865F2;
}

/* Tables & Lists */
QTableWidget, QListWidget {
    background-color: #1E1F22;
    color: #F2F3F5;
    border: 1px solid #383A40;
    border-radius: 6px;
    gridline-color: #2B2D31;
    selection-background-color: #35373C;
    selection-color: #F2F3F5;
}
QHeaderView::section {
    background-color: #2B2D31;
    color: #949BA4;
    padding: 6px;
    border: none;
    border-bottom: 1px solid #383A40;
    font-weight: bold;
}

/* Terminal Console View */
QPlainTextEdit#TerminalConsole {
    background-color: #111214;
    color: #DCDDDE;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
    border: 1px solid #2B2D31;
    border-radius: 6px;
    padding: 8px;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background-color: #2B2D31;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background-color: #1E1F22;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background-color: #4E5058;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""

# ---------------------------------------------------------------------------
# Qt Log Handler for Live Terminal
# ---------------------------------------------------------------------------

class LogEmitter(QObject):
    log_signal = pyqtSignal(str)


class QtLogHandler(logging.Handler):
    """Custom logging handler that routes log records to a Qt Signal."""
    def __init__(self, emitter: LogEmitter):
        super().__init__()
        self.emitter = emitter

    def emit(self, record):
        try:
            msg = self.format(record)
            self.emitter.log_signal.emit(msg)
        except Exception:
            pass


GLOBAL_EMITTER = LogEmitter()
QT_LOG_HANDLER = QtLogHandler(GLOBAL_EMITTER)
QT_LOG_HANDLER.setLevel(logging.DEBUG)
QT_LOG_HANDLER.setFormatter(
    logging.Formatter("[%(asctime)s] %(levelname)-7s %(name)s - %(message)s", datefmt="%H:%M:%S")
)
logging.getLogger().addHandler(QT_LOG_HANDLER)


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        app.setStyleSheet(DISCORD_DARK_QSS)
        if ICON_PATH.exists():
            app.setWindowIcon(QIcon(str(ICON_PATH)))
    return app


# ---------------------------------------------------------------------------
# First-Run Setup Wizard (Qt)
# ---------------------------------------------------------------------------

class OnboardingWizardDialog(QDialog):
    """Modern 60-second guided wizard for first-run Application ID setup."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Discord AutoRPC — First-Run Setup")
        self.setFixedSize(540, 460)
        self.setStyleSheet(DISCORD_DARK_QSS)
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        self.result_config = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header Card
        header = QFrame()
        header.setStyleSheet("background-color: #2B2D31; border-radius: 8px; padding: 10px;")
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(12, 10, 12, 10)

        title = QLabel("🚀 Welcome to Discord AutoRPC")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet("color: #FFFFFF;")
        h_layout.addWidget(title)

        subtitle = QLabel("Connect Discord AutoRPC to your Discord client in 3 quick steps.")
        subtitle.setStyleSheet("color: #949BA4; font-size: 13px;")
        h_layout.addWidget(subtitle)
        layout.addWidget(header)

        # Step 1
        s1_lbl = QLabel("Step 1: Open the Discord Developer Portal")
        s1_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        layout.addWidget(s1_lbl)

        btn_portal = QPushButton("🌐 Open Discord Developer Portal")
        btn_portal.setObjectName("PrimaryBtn")
        btn_portal.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_portal.setFixedHeight(34)
        btn_portal.clicked.connect(lambda: webbrowser.open("https://discord.com/developers/applications"))
        layout.addWidget(btn_portal)

        # Step 2
        s2_lbl = QLabel("Step 2: Create a Free Application")
        s2_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        layout.addWidget(s2_lbl)

        s2_desc = QLabel("In the portal, click 'New Application' in the top right. Give it any name you want (e.g., 'My Activity' or your username), and click Create.")
        s2_desc.setStyleSheet("color: #949BA4;")
        s2_desc.setWordWrap(True)
        layout.addWidget(s2_desc)

        # Step 3
        s3_lbl = QLabel("Step 3: Paste your Application ID")
        s3_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        layout.addWidget(s3_lbl)

        self.input_id = QLineEdit()
        self.input_id.setPlaceholderText("Paste your 17–20 digit Application ID here...")
        self.input_id.setFixedHeight(34)
        self.input_id.textChanged.connect(self._validate_input)
        layout.addWidget(self.input_id)

        self.err_lbl = QLabel("")
        self.err_lbl.setStyleSheet("color: #F23F43; font-size: 12px;")
        layout.addWidget(self.err_lbl)

        layout.addStretch()

        # Bottom Action Bar
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        self.btn_save = QPushButton("✓ Save & Launch AutoRPC")
        self.btn_save.setObjectName("SuccessBtn")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setFixedHeight(34)
        self.btn_save.clicked.connect(self._save_and_start)
        btn_layout.addWidget(self.btn_save)

        layout.addLayout(btn_layout)

    def _validate_input(self):
        val = self.input_id.text().strip()
        if not val:
            self.err_lbl.setText("")
            return
        valid, err = validate_app_id(val)
        if valid:
            self.err_lbl.setStyleSheet("color: #23A55A; font-size: 12px;")
            self.err_lbl.setText("✓ Valid Discord Application ID")
        else:
            self.err_lbl.setStyleSheet("color: #F23F43; font-size: 12px;")
            self.err_lbl.setText(err)

    def _save_and_start(self):
        val = self.input_id.text().strip()
        valid, err = validate_app_id(val)
        if not valid:
            self.err_lbl.setStyleSheet("color: #F23F43; font-size: 12px;")
            self.err_lbl.setText(err)
            return

        cfg = load_config()
        cfg["application_id"] = val
        save_config(cfg)
        self.result_config = cfg
        self.accept()


# ---------------------------------------------------------------------------
# 1-Click Quick Rename Dialog (Qt)
# ---------------------------------------------------------------------------

class QuickRenameDialog(QDialog):
    """Modern 1-click modal to rename an active application and optional tagline."""

    def __init__(self, exe_name: str, current_name: str, current_tagline: str = "", on_saved=None, parent=None):
        super().__init__(parent)
        self.exe_name = exe_name.strip()
        self.on_saved = on_saved
        self.setWindowTitle(f"Rename Active App — {self.exe_name}")
        self.setFixedSize(480, 310)
        self.setStyleSheet(DISCORD_DARK_QSS)
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        self._build_ui(current_name, current_tagline)

    def _build_ui(self, current_name: str, current_tagline: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        # Header Card
        header = QFrame()
        header.setStyleSheet("background-color: #2B2D31; border-radius: 8px; padding: 10px;")
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(10, 8, 10, 8)

        title = QLabel(f"🏷️ Rename '{self.exe_name}'")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        h_layout.addWidget(title)

        desc = QLabel("Customize how this application and status appear on your Discord profile.")
        desc.setStyleSheet("color: #949BA4; font-size: 12px;")
        h_layout.addWidget(desc)
        layout.addWidget(header)

        # Display Name
        lbl_name = QLabel("Custom Display Name (shown as 'Playing ...'):")
        lbl_name.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        layout.addWidget(lbl_name)

        self.input_name = QLineEdit(current_name)
        self.input_name.setPlaceholderText("e.g. PhotoCraft or Photoshop")
        self.input_name.setFixedHeight(34)
        layout.addWidget(self.input_name)

        # Tagline
        lbl_tag = QLabel("Custom Tagline (optional details line):")
        layout.addWidget(lbl_tag)

        self.input_tag = QLineEdit(current_tagline)
        self.input_tag.setPlaceholderText("Leave blank to keep automatic dynamic detail")
        self.input_tag.setFixedHeight(34)
        layout.addWidget(self.input_tag)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_save = QPushButton("💾 Save & Apply Instantly")
        btn_save.setObjectName("PrimaryBtn")
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self._save)
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)

    def _save(self):
        new_name = self.input_name.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Invalid Name", "Display Name cannot be empty.")
            return

        new_tagline = self.input_tag.text().strip()

        cfg = load_config()
        overrides = cfg.setdefault("overrides", {})
        overrides[self.exe_name.lower()] = {
            "name": new_name,
            "tagline": new_tagline,
        }
        save_config(cfg)

        if self.on_saved:
            self.on_saved(cfg, new_name, new_tagline)

        QMessageBox.information(
            self,
            "Name Saved",
            f"Successfully updated '{self.exe_name}' to display as '{new_name}' on Discord!",
        )
        self.accept()


# ---------------------------------------------------------------------------
# Modern Settings & Live Terminal Window (Qt)
# ---------------------------------------------------------------------------

class SettingsWindow(QMainWindow):
    """Full-featured modern Qt Settings window with live process terminal."""

    def __init__(self, on_saved: Optional[Callable[[dict], None]] = None):
        super().__init__()
        self.on_saved = on_saved
        self.config = load_config()
        self.current_overrides = dict(self.config.get("overrides", {}))

        self.setWindowTitle("Discord AutoRPC — Settings & Live Terminal")
        self.resize(750, 600)
        self.setStyleSheet(DISCORD_DARK_QSS)
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        self._build_ui()
        self._load_existing_logs()

        # Connect live log streaming
        GLOBAL_EMITTER.log_signal.connect(self._append_log)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Tab 1: General
        self.tab_general = QWidget()
        self._build_general_tab()
        self.tabs.addTab(self.tab_general, "⚙️ General")

        # Tab 2: App Names & Overrides
        self.tab_overrides = QWidget()
        self._build_overrides_tab()
        self.tabs.addTab(self.tab_overrides, "🏷️ App Names & Overrides")

        # Tab 3: Taglines
        self.tab_taglines = QWidget()
        self._build_taglines_tab()
        self.tabs.addTab(self.tab_taglines, "💬 Taglines")

        # Tab 3: Ignored Apps
        self.tab_ignored = QWidget()
        self._build_ignored_tab()
        self.tabs.addTab(self.tab_ignored, "🚫 Ignored Apps")

        # Tab 4: Live Terminal & Process Logs
        self.tab_terminal = QWidget()
        self._build_terminal_tab()
        self.tabs.addTab(self.tab_terminal, "🖥️ Live Terminal & Logs")

        # Bottom Bar
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        btn_cancel = QPushButton("Close")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.close)
        bottom_layout.addWidget(btn_cancel)

        btn_save = QPushButton("💾 Save All Changes")
        btn_save.setObjectName("PrimaryBtn")
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self._save_settings)
        bottom_layout.addWidget(btn_save)

        main_layout.addLayout(bottom_layout)

    def _build_general_tab(self):
        layout = QVBoxLayout(self.tab_general)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # Application ID
        lbl_app = QLabel("Discord Application ID:")
        lbl_app.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        layout.addWidget(lbl_app)

        self.input_app_id = QLineEdit(self.config.get("application_id", ""))
        self.input_app_id.setFixedHeight(34)
        layout.addWidget(self.input_app_id)

        # Checkboxes
        self.cb_autoclose = QCheckBox("Close Discord AutoRPC automatically when Discord exits")
        self.cb_autoclose.setChecked(self.config.get("auto_close_with_discord", True))
        layout.addWidget(self.cb_autoclose)

        self.cb_autostart = QCheckBox("Launch Discord AutoRPC automatically on Windows login")
        self.cb_autostart.setChecked(is_autostart_enabled())
        layout.addWidget(self.cb_autostart)

        self.cb_private = QCheckBox("Mask / suppress presence in Incognito & Private browser windows")
        self.cb_private.setChecked(self.config.get("mask_private_browsing", True))
        layout.addWidget(self.cb_private)

        self.cb_dynamic_taglines = QCheckBox("Enable Smart Dynamic Details (sheet names, web platforms, active files)")
        self.cb_dynamic_taglines.setChecked(self.config.get("enable_dynamic_taglines", True))
        layout.addWidget(self.cb_dynamic_taglines)

        # Timing Spinners
        time_frame = QFrame()
        time_frame.setStyleSheet("background-color: #2B2D31; border-radius: 6px; padding: 10px;")
        t_layout = QVBoxLayout(time_frame)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel("App switch debounce delay (seconds):"))
        self.spin_debounce = QSpinBox()
        self.spin_debounce.setRange(2, 60)
        self.spin_debounce.setValue(int(self.config.get("debounce_seconds", 10)))
        h1.addWidget(self.spin_debounce)
        t_layout.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Idle timeout before clearing presence (seconds):"))
        self.spin_idle = QSpinBox()
        self.spin_idle.setRange(10, 600)
        self.spin_idle.setValue(int(self.config.get("idle_timeout_seconds", 60)))
        h2.addWidget(self.spin_idle)
        t_layout.addLayout(h2)

        layout.addWidget(time_frame)
        layout.addStretch()

    def _build_overrides_tab(self):
        layout = QVBoxLayout(self.tab_overrides)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        desc = QLabel("Customize display names and custom taglines for specific programs:")
        desc.setStyleSheet("color: #949BA4;")
        layout.addWidget(desc)

        # Table: Executable, Custom Name, Custom Tagline
        self.override_table = QTableWidget(0, 3)
        self.override_table.setHorizontalHeaderLabels(["Executable", "Display Name", "Custom Tagline"])
        self.override_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.override_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.override_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.override_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.override_table)

        self._populate_override_table()

        # Add / Edit row
        edit_layout = QHBoxLayout()
        self.input_ovr_exe = QLineEdit()
        self.input_ovr_exe.setPlaceholderText("exe (e.g. photocraft.exe)")
        self.input_ovr_exe.setFixedWidth(160)
        edit_layout.addWidget(self.input_ovr_exe)

        self.input_ovr_name = QLineEdit()
        self.input_ovr_name.setPlaceholderText("Display Name (e.g. PhotoCraft)")
        self.input_ovr_name.setFixedWidth(180)
        edit_layout.addWidget(self.input_ovr_name)

        self.input_ovr_tag = QLineEdit()
        self.input_ovr_tag.setPlaceholderText("Tagline (optional)")
        edit_layout.addWidget(self.input_ovr_tag)

        btn_add = QPushButton("Add / Update")
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(self._add_or_update_override)
        edit_layout.addWidget(btn_add)

        btn_del = QPushButton("Delete")
        btn_del.setObjectName("DangerBtn")
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.clicked.connect(self._delete_override)
        edit_layout.addWidget(btn_del)

        layout.addLayout(edit_layout)

    def _populate_override_table(self):
        self.override_table.setRowCount(0)
        for row, (exe, data) in enumerate(sorted(self.current_overrides.items())):
            self.override_table.insertRow(row)
            self.override_table.setItem(row, 0, QTableWidgetItem(exe))
            name = data.get("name", "") if isinstance(data, dict) else str(data)
            tag = data.get("tagline", "") if isinstance(data, dict) else ""
            self.override_table.setItem(row, 1, QTableWidgetItem(name))
            self.override_table.setItem(row, 2, QTableWidgetItem(tag))

    def _add_or_update_override(self):
        exe = self.input_ovr_exe.text().strip().lower()
        name = self.input_ovr_name.text().strip()
        tag = self.input_ovr_tag.text().strip()
        if exe and name:
            if not exe.endswith(".exe"):
                exe += ".exe"
            entry = {"name": name}
            if tag:
                entry["tagline"] = tag
            self.current_overrides[exe] = entry
            self._populate_override_table()
            self.input_ovr_exe.clear()
            self.input_ovr_name.clear()
            self.input_ovr_tag.clear()

    def _delete_override(self):
        selected = self.override_table.currentRow()
        if selected >= 0:
            exe_item = self.override_table.item(selected, 0)
            if exe_item:
                self.current_overrides.pop(exe_item.text().lower(), None)
                self._populate_override_table()

    def _build_taglines_tab(self):
        layout = QVBoxLayout(self.tab_taglines)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        desc = QLabel("Contextual taglines appear on the 2nd line of your Discord profile:")
        desc.setStyleSheet("color: #949BA4;")
        layout.addWidget(desc)

        # Table
        self.tagline_table = QTableWidget(0, 2)
        self.tagline_table.setHorizontalHeaderLabels(["Executable", "Tagline"])
        self.tagline_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tagline_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tagline_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.tagline_table)

        self.current_taglines = dict(self.config.get("taglines", {}))
        self._populate_tagline_table()

        # Add / Edit row
        edit_layout = QHBoxLayout()
        self.input_tag_exe = QLineEdit()
        self.input_tag_exe.setPlaceholderText("e.g. notion.exe")
        self.input_tag_exe.setFixedWidth(160)
        edit_layout.addWidget(self.input_tag_exe)

        self.input_tag_text = QLineEdit()
        self.input_tag_text.setPlaceholderText("e.g. Working on a document")
        edit_layout.addWidget(self.input_tag_text)

        btn_add = QPushButton("Add / Update")
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(self._add_or_update_tagline)
        edit_layout.addWidget(btn_add)

        btn_del = QPushButton("Delete")
        btn_del.setObjectName("DangerBtn")
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.clicked.connect(self._delete_tagline)
        edit_layout.addWidget(btn_del)

        layout.addLayout(edit_layout)

    def _populate_tagline_table(self):
        self.tagline_table.setRowCount(0)
        for row, (exe, tag) in enumerate(sorted(self.current_taglines.items())):
            self.tagline_table.insertRow(row)
            self.tagline_table.setItem(row, 0, QTableWidgetItem(exe))
            self.tagline_table.setItem(row, 1, QTableWidgetItem(tag))

    def _add_or_update_tagline(self):
        exe = self.input_tag_exe.text().strip().lower()
        tag = self.input_tag_text.text().strip()
        if exe and tag:
            if not exe.endswith(".exe"):
                exe += ".exe"
            self.current_taglines[exe] = tag
            self._populate_tagline_table()
            self.input_tag_exe.clear()
            self.input_tag_text.clear()

    def _delete_tagline(self):
        selected = self.tagline_table.currentRow()
        if selected >= 0:
            exe_item = self.tagline_table.item(selected, 0)
            if exe_item:
                self.current_taglines.pop(exe_item.text(), None)
                self._populate_tagline_table()

    def _build_ignored_tab(self):
        layout = QVBoxLayout(self.tab_ignored)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        desc = QLabel("Applications that will be silently ignored (never shown on Discord):")
        desc.setStyleSheet("color: #949BA4;")
        layout.addWidget(desc)

        self.ignored_list = QListWidget()
        layout.addWidget(self.ignored_list)

        self.current_ignored = list(self.config.get("ignored_exes", []))
        self._populate_ignored_list()

        edit_layout = QHBoxLayout()
        self.input_ignore_exe = QLineEdit()
        self.input_ignore_exe.setPlaceholderText("Executable name (e.g. secret_app.exe)")
        edit_layout.addWidget(self.input_ignore_exe)

        btn_add = QPushButton("Add to Ignore List")
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(self._add_ignore)
        edit_layout.addWidget(btn_add)

        btn_del = QPushButton("Remove")
        btn_del.setObjectName("DangerBtn")
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.clicked.connect(self._remove_ignore)
        edit_layout.addWidget(btn_del)

        layout.addLayout(edit_layout)

    def _populate_ignored_list(self):
        self.ignored_list.clear()
        for exe in sorted(self.current_ignored):
            self.ignored_list.addItem(exe)

    def _add_ignore(self):
        exe = self.input_ignore_exe.text().strip().lower()
        if exe:
            if not exe.endswith(".exe"):
                exe += ".exe"
            if exe not in self.current_ignored:
                self.current_ignored.append(exe)
                self._populate_ignored_list()
                self.input_ignore_exe.clear()

    def _remove_ignore(self):
        selected = self.ignored_list.currentRow()
        if selected >= 0:
            item = self.ignored_list.item(selected)
            if item and item.text() in self.current_ignored:
                self.current_ignored.remove(item.text())
                self._populate_ignored_list()

    def _build_terminal_tab(self):
        layout = QVBoxLayout(self.tab_terminal)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Toolbar
        tb_layout = QHBoxLayout()
        lbl_info = QLabel("Real-Time Process & Detection Logs:")
        lbl_info.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        tb_layout.addWidget(lbl_info)

        tb_layout.addStretch()

        self.cb_autoscroll = QCheckBox("Auto-scroll")
        self.cb_autoscroll.setChecked(True)
        tb_layout.addWidget(self.cb_autoscroll)

        btn_copy = QPushButton("📋 Copy Logs")
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.clicked.connect(self._copy_logs)
        tb_layout.addWidget(btn_copy)

        btn_save_log = QPushButton("💾 Export Log File...")
        btn_save_log.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save_log.clicked.connect(self._export_log_file)
        tb_layout.addWidget(btn_save_log)

        btn_clear = QPushButton("🧹 Clear")
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear.clicked.connect(lambda: self.console.clear())
        tb_layout.addWidget(btn_clear)

        btn_cache = QPushButton("🔄 Reset Icon Cache")
        btn_cache.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cache.clicked.connect(self._reset_icon_cache)
        tb_layout.addWidget(btn_cache)

        layout.addLayout(tb_layout)

        # Live Console Display
        self.console = QPlainTextEdit()
        self.console.setObjectName("TerminalConsole")
        self.console.setReadOnly(True)
        layout.addWidget(self.console)

    def _load_existing_logs(self):
        if LOG_PATH.exists():
            try:
                with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                    # Show last 200 lines initially
                    tail = "".join(lines[-200:])
                    self.console.setPlainText(tail)
                    self.console.moveCursor(QTextCursor.MoveOperation.End)
            except Exception:
                pass

    def _append_log(self, text: str):
        self.console.appendPlainText(text)
        if self.cb_autoscroll.isChecked():
            self.console.moveCursor(QTextCursor.MoveOperation.End)

    def _copy_logs(self):
        text = self.console.toPlainText()
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            QMessageBox.information(self, "Copied", "Terminal logs copied to clipboard!")

    def _export_log_file(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Log File", "autorpc_logs.txt", "Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self.console.toPlainText())
                QMessageBox.information(self, "Saved", f"Log successfully saved to {file_path}")
            except Exception as exc:
                QMessageBox.critical(self, "Error", f"Failed to save log file: {exc}")

    def _reset_icon_cache(self):
        count = clear_icon_cache()
        QMessageBox.information(
            self,
            "Icon Cache Reset",
            f"Successfully cleared {count} cached icons.\nNext app detections will fetch/upload fresh icons.",
        )

    def _save_settings(self):
        app_id = self.input_app_id.text().strip()
        valid, err = validate_app_id(app_id)
        if not valid:
            QMessageBox.critical(self, "Invalid Application ID", err)
            return

        self.config["application_id"] = app_id
        self.config["auto_close_with_discord"] = self.cb_autoclose.isChecked()
        self.config["mask_private_browsing"] = self.cb_private.isChecked()
        self.config["enable_dynamic_taglines"] = self.cb_dynamic_taglines.isChecked()
        self.config["debounce_seconds"] = self.spin_debounce.value()
        self.config["idle_timeout_seconds"] = self.spin_idle.value()
        self.config["taglines"] = self.current_taglines
        self.config["ignored_exes"] = self.current_ignored
        self.config["overrides"] = self.current_overrides

        set_autostart_enabled(self.cb_autostart.isChecked())
        save_config(self.config)

        if self.on_saved:
            self.on_saved(self.config)

        QMessageBox.information(self, "Saved", "Settings saved successfully!")
        self.close()


# ---------------------------------------------------------------------------
# Public Functions to Invoke from main.py
# ---------------------------------------------------------------------------

_CURRENT_SETTINGS_WINDOW = None


def open_settings_gui(on_saved: Optional[Callable[[dict], None]] = None):
    """Launch or focus the modern Qt Settings window."""
    global _CURRENT_SETTINGS_WINDOW
    _ensure_qapp()

    if _CURRENT_SETTINGS_WINDOW is None or not _CURRENT_SETTINGS_WINDOW.isVisible():
        _CURRENT_SETTINGS_WINDOW = SettingsWindow(on_saved=on_saved)
        _CURRENT_SETTINGS_WINDOW.show()
    else:
        _CURRENT_SETTINGS_WINDOW.raise_()
        _CURRENT_SETTINGS_WINDOW.activateWindow()


def run_onboarding_wizard() -> Optional[dict]:
    """Launch the first-run onboarding dialog modally and return updated config."""
    app = _ensure_qapp()
    wizard = OnboardingWizardDialog()
    if wizard.exec() == QDialog.DialogCode.Accepted:
        return wizard.result_config
    return None


def open_quick_rename_gui(
    exe_name: str,
    current_name: str,
    current_tagline: str = "",
    on_saved: Optional[Callable] = None,
):
    """Launch the 1-click Quick Rename modal dialog."""
    app = _ensure_qapp()
    dialog = QuickRenameDialog(
        exe_name=exe_name,
        current_name=current_name,
        current_tagline=current_tagline,
        on_saved=on_saved,
    )
    dialog.exec()

