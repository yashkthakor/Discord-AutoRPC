"""
gui.py — Desktop GUI for First-Run Setup & Settings Management.

Built with Tkinter (zero external dependencies).
Features a Discord-inspired dark theme.
"""

import logging
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
from typing import Callable, Optional

from config import (
    load_config,
    save_config,
    validate_app_id,
    is_autostart_enabled,
    set_autostart_enabled,
)

logger = logging.getLogger("autorpc.gui")

# Discord Color Palette
BG_DARK = "#1E1F22"       # Main background
BG_PANEL = "#2B2D31"      # Card / panel background
BG_INPUT = "#313338"      # Input fields
TEXT_PRIMARY = "#F2F3F5"  # Primary white text
TEXT_MUTED = "#949BA4"    # Secondary muted text
ACCENT_BLURPLE = "#5865F2"# Discord Blurple
ACCENT_HOVER = "#4752C4"  # Hover Blurple
ACCENT_GREEN = "#23A55A"  # Success green
ACCENT_RED = "#F23F43"    # Error red
BORDER_COLOR = "#383A40"  # Subtle border


def _center_window(win: tk.Tk | tk.Toplevel, width: int, height: int):
    """Center a tkinter window on the active monitor."""
    win.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    x = max(0, (sw - width) // 2)
    y = max(0, (sh - height) // 2)
    win.geometry(f"{width}x{height}+{x}+{y}")


# ---------------------------------------------------------------------------
# First-Run Setup Wizard
# ---------------------------------------------------------------------------

class OnboardingWizard:
    """Guided 60-second wizard for first-time Application ID setup."""

    def __init__(self, on_success: Optional[Callable[[dict], None]] = None):
        self.on_success = on_success
        self.root = tk.Tk()
        self.root.title("Discord AutoRPC — Setup")
        self.root.configure(bg=BG_DARK)
        self.root.resizable(False, False)
        _center_window(self.root, 540, 460)

        self._build_ui()
        self.result_config = None

    def _build_ui(self):
        # Header Container
        header_frame = tk.Frame(self.root, bg=BG_PANEL, pady=16, padx=20)
        header_frame.pack(fill="x")

        title_lbl = tk.Label(
            header_frame,
            text="🚀 Welcome to Discord AutoRPC",
            font=("Segoe UI", 14, "bold"),
            fg=TEXT_PRIMARY,
            bg=BG_PANEL,
        )
        title_lbl.pack(anchor="w")

        sub_lbl = tk.Label(
            header_frame,
            text="Let's connect your personal Discord Application in 3 quick steps.",
            font=("Segoe UI", 9),
            fg=TEXT_MUTED,
            bg=BG_PANEL,
        )
        sub_lbl.pack(anchor="w", pady=(4, 0))

        # Steps Container
        body_frame = tk.Frame(self.root, bg=BG_DARK, padx=24, pady=16)
        body_frame.pack(fill="both", expand=True)

        # Step 1
        s1_lbl = tk.Label(
            body_frame,
            text="Step 1: Open the Discord Developer Portal",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT_PRIMARY,
            bg=BG_DARK,
        )
        s1_lbl.pack(anchor="w")

        btn_portal = tk.Button(
            body_frame,
            text="🌐 Open Discord Developer Portal",
            font=("Segoe UI", 9, "bold"),
            bg=ACCENT_BLURPLE,
            fg="white",
            activebackground=ACCENT_HOVER,
            activeforeground="white",
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=6,
            command=lambda: webbrowser.open("https://discord.com/developers/applications"),
        )
        btn_portal.pack(anchor="w", pady=(6, 12))

        # Step 2
        s2_lbl = tk.Label(
            body_frame,
            text="Step 2: Create a Free Application",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT_PRIMARY,
            bg=BG_DARK,
        )
        s2_lbl.pack(anchor="w")

        s2_desc = tk.Label(
            body_frame,
            text="Click 'New Application' in the top right. Give it any name you want\n(e.g., 'My Activities' or your gamer tag), then click Create.",
            font=("Segoe UI", 9),
            fg=TEXT_MUTED,
            bg=BG_DARK,
            justify="left",
        )
        s2_desc.pack(anchor="w", pady=(2, 12))

        # Step 3
        s3_lbl = tk.Label(
            body_frame,
            text="Step 3: Paste your Application ID",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT_PRIMARY,
            bg=BG_DARK,
        )
        s3_lbl.pack(anchor="w")

        self.id_var = tk.StringVar()
        self.entry_id = tk.Entry(
            body_frame,
            textvariable=self.id_var,
            font=("Segoe UI", 11),
            bg=BG_INPUT,
            fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=ACCENT_BLURPLE,
        )
        self.entry_id.pack(fill="x", pady=(6, 4), ipady=5)
        self.entry_id.focus_set()

        self.err_lbl = tk.Label(
            body_frame,
            text="",
            font=("Segoe UI", 9),
            fg=ACCENT_RED,
            bg=BG_DARK,
        )
        self.err_lbl.pack(anchor="w")

        # Footer
        footer = tk.Frame(self.root, bg=BG_PANEL, padx=20, pady=12)
        footer.pack(fill="x", side="bottom")

        btn_save = tk.Button(
            footer,
            text="✓ Save & Launch AutoRPC",
            font=("Segoe UI", 10, "bold"),
            bg=ACCENT_GREEN,
            fg="white",
            relief="flat",
            cursor="hand2",
            padx=16,
            pady=6,
            command=self._handle_save,
        )
        btn_save.pack(side="right")

        btn_exit = tk.Button(
            footer,
            text="Cancel",
            font=("Segoe UI", 9),
            bg=BG_INPUT,
            fg=TEXT_MUTED,
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=6,
            command=self.root.destroy,
        )
        btn_exit.pack(side="right", padx=(0, 10))

    def _handle_save(self):
        val = self.id_var.get().strip()
        valid, err = validate_app_id(val)
        if not valid:
            self.err_lbl.config(text=err)
            return

        config = load_config()
        config["application_id"] = val
        save_config(config)

        self.result_config = config
        if self.on_success:
            self.on_success(config)
        self.root.destroy()

    def run(self) -> Optional[dict]:
        self.root.mainloop()
        return self.result_config


# ---------------------------------------------------------------------------
# Settings Management GUI
# ---------------------------------------------------------------------------

class SettingsWindow:
    """Full-featured Settings GUI accessible from the system tray menu."""

    def __init__(self, on_saved: Optional[Callable[[dict], None]] = None):
        self.on_saved = on_saved
        self.config = load_config()

        self.win = tk.Tk()
        self.win.title("Discord AutoRPC — Settings")
        self.win.configure(bg=BG_DARK)
        _center_window(self.win, 620, 520)

        self._apply_styles()
        self._build_tabs()

    def _apply_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=BG_DARK, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG_PANEL, foreground=TEXT_MUTED, padding=[16, 6], font=("Segoe UI", 9, "bold"))
        style.map("TNotebook.Tab", background=[("selected", BG_DARK)], foreground=[("selected", TEXT_PRIMARY)])

    def _build_tabs(self):
        notebook = ttk.Notebook(self.win)
        notebook.pack(fill="both", expand=True, padx=12, pady=12)

        # Tab 1: General
        tab_general = tk.Frame(notebook, bg=BG_DARK, padx=16, pady=16)
        notebook.add(tab_general, text="General")
        self._build_general_tab(tab_general)

        # Tab 2: Taglines
        tab_taglines = tk.Frame(notebook, bg=BG_DARK, padx=16, pady=16)
        notebook.add(tab_taglines, text="Taglines")
        self._build_taglines_tab(tab_taglines)

        # Tab 3: Ignored Apps
        tab_ignored = tk.Frame(notebook, bg=BG_DARK, padx=16, pady=16)
        notebook.add(tab_ignored, text="Ignored Apps")
        self._build_ignored_tab(tab_ignored)

        # Bottom Bar
        footer = tk.Frame(self.win, bg=BG_PANEL, padx=16, pady=10)
        footer.pack(fill="x", side="bottom")

        btn_save = tk.Button(
            footer, text="Save All Changes", font=("Segoe UI", 9, "bold"),
            bg=ACCENT_BLURPLE, fg="white", relief="flat", cursor="hand2",
            padx=16, pady=5, command=self._save_all,
        )
        btn_save.pack(side="right")

        btn_cancel = tk.Button(
            footer, text="Close", font=("Segoe UI", 9),
            bg=BG_INPUT, fg=TEXT_MUTED, relief="flat", cursor="hand2",
            padx=12, pady=5, command=self.win.destroy,
        )
        btn_cancel.pack(side="right", padx=(0, 10))

    def _build_general_tab(self, parent):
        # Application ID
        tk.Label(parent, text="Discord Application ID:", font=("Segoe UI", 9, "bold"), fg=TEXT_PRIMARY, bg=BG_DARK).pack(anchor="w")
        self.var_appid = tk.StringVar(value=self.config.get("application_id", ""))
        e_appid = tk.Entry(parent, textvariable=self.var_appid, font=("Segoe UI", 10), bg=BG_INPUT, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief="flat")
        e_appid.pack(fill="x", pady=(4, 16), ipady=4)

        # Toggles
        self.var_autoclose = tk.BooleanVar(value=self.config.get("auto_close_with_discord", True))
        cb_close = tk.Checkbutton(
            parent, text="Close AutoRPC automatically when Discord exits",
            variable=self.var_autoclose, font=("Segoe UI", 9),
            fg=TEXT_PRIMARY, bg=BG_DARK, selectcolor=BG_INPUT, activebackground=BG_DARK, activeforeground=TEXT_PRIMARY,
        )
        cb_close.pack(anchor="w", pady=4)

        self.var_autostart = tk.BooleanVar(value=is_autostart_enabled())
        cb_start = tk.Checkbutton(
            parent, text="Start Discord AutoRPC automatically on Windows login",
            variable=self.var_autostart, font=("Segoe UI", 9),
            fg=TEXT_PRIMARY, bg=BG_DARK, selectcolor=BG_INPUT, activebackground=BG_DARK, activeforeground=TEXT_PRIMARY,
        )
        cb_start.pack(anchor="w", pady=4)

        # Timers
        time_frame = tk.Frame(parent, bg=BG_DARK, pady=16)
        time_frame.pack(fill="x")

        tk.Label(time_frame, text="App switch debounce (seconds):", font=("Segoe UI", 9), fg=TEXT_MUTED, bg=BG_DARK).grid(row=0, column=0, sticky="w", pady=4)
        self.var_debounce = tk.StringVar(value=str(self.config.get("debounce_seconds", 10)))
        tk.Entry(time_frame, textvariable=self.var_debounce, width=8, bg=BG_INPUT, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief="flat").grid(row=0, column=1, sticky="w", padx=8)

        tk.Label(time_frame, text="Idle timeout (seconds):", font=("Segoe UI", 9), fg=TEXT_MUTED, bg=BG_DARK).grid(row=1, column=0, sticky="w", pady=4)
        self.var_idle = tk.StringVar(value=str(self.config.get("idle_timeout_seconds", 60)))
        tk.Entry(time_frame, textvariable=self.var_idle, width=8, bg=BG_INPUT, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief="flat").grid(row=1, column=1, sticky="w", padx=8)

    def _build_taglines_tab(self, parent):
        tk.Label(parent, text="Contextual taglines shown on Discord's second line:", font=("Segoe UI", 9), fg=TEXT_MUTED, bg=BG_DARK).pack(anchor="w", pady=(0, 8))

        # Listbox for taglines
        list_frame = tk.Frame(parent, bg=BG_DARK)
        list_frame.pack(fill="both", expand=True)

        self.taglines_box = tk.Listbox(list_frame, bg=BG_INPUT, fg=TEXT_PRIMARY, selectbackground=ACCENT_BLURPLE, relief="flat", font=("Segoe UI", 9))
        self.taglines_box.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.taglines_box.yview)
        scrollbar.pack(side="right", fill="y")
        self.taglines_box.config(yscrollcommand=scrollbar.set)

        self.current_taglines: dict = dict(self.config.get("taglines", {}))
        self._refresh_taglines_list()

        # Add / Edit row
        edit_frame = tk.Frame(parent, bg=BG_DARK, pady=8)
        edit_frame.pack(fill="x")

        tk.Label(edit_frame, text="Executable (e.g. notion.exe):", font=("Segoe UI", 8), fg=TEXT_MUTED, bg=BG_DARK).grid(row=0, column=0, sticky="w")
        tk.Label(edit_frame, text="Tagline:", font=("Segoe UI", 8), fg=TEXT_MUTED, bg=BG_DARK).grid(row=0, column=1, sticky="w", padx=6)

        self.entry_exe = tk.Entry(edit_frame, width=22, bg=BG_INPUT, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief="flat")
        self.entry_exe.grid(row=1, column=0, sticky="w")

        self.entry_tag = tk.Entry(edit_frame, width=30, bg=BG_INPUT, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief="flat")
        self.entry_tag.grid(row=1, column=1, sticky="w", padx=6)

        btn_add = tk.Button(edit_frame, text="Add / Update", bg=BG_PANEL, fg=TEXT_PRIMARY, relief="flat", cursor="hand2", padx=8, command=self._add_tagline)
        btn_add.grid(row=1, column=2, padx=4)

        btn_del = tk.Button(edit_frame, text="Delete", bg=BG_PANEL, fg=ACCENT_RED, relief="flat", cursor="hand2", padx=8, command=self._del_tagline)
        btn_del.grid(row=1, column=3)

    def _refresh_taglines_list(self):
        self.taglines_box.delete(0, tk.END)
        for exe, tag in sorted(self.current_taglines.items()):
            self.taglines_box.insert(tk.END, f"{exe}  →  \"{tag}\"")

    def _add_tagline(self):
        exe = self.entry_exe.get().strip().lower()
        tag = self.entry_tag.get().strip()
        if exe and tag:
            if not exe.endswith(".exe"):
                exe += ".exe"
            self.current_taglines[exe] = tag
            self._refresh_taglines_list()
            self.entry_exe.delete(0, tk.END)
            self.entry_tag.delete(0, tk.END)

    def _del_tagline(self):
        sel = self.taglines_box.curselection()
        if sel:
            item = self.taglines_box.get(sel[0])
            exe = item.split("  →  ")[0].strip()
            self.current_taglines.pop(exe, None)
            self._refresh_taglines_list()

    def _build_ignored_tab(self, parent):
        tk.Label(parent, text="Applications silently ignored (never tracked):", font=("Segoe UI", 9), fg=TEXT_MUTED, bg=BG_DARK).pack(anchor="w", pady=(0, 8))

        list_frame = tk.Frame(parent, bg=BG_DARK)
        list_frame.pack(fill="both", expand=True)

        self.ignored_box = tk.Listbox(list_frame, bg=BG_INPUT, fg=TEXT_PRIMARY, selectbackground=ACCENT_BLURPLE, relief="flat", font=("Segoe UI", 9))
        self.ignored_box.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.ignored_box.yview)
        scrollbar.pack(side="right", fill="y")
        self.ignored_box.config(yscrollcommand=scrollbar.set)

        self.current_ignored: list = list(self.config.get("ignored_exes", []))
        self._refresh_ignored_list()

        edit_frame = tk.Frame(parent, bg=BG_DARK, pady=8)
        edit_frame.pack(fill="x")

        self.entry_ignore_exe = tk.Entry(edit_frame, width=28, bg=BG_INPUT, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief="flat")
        self.entry_ignore_exe.pack(side="left", padx=(0, 6), ipady=3)

        btn_add = tk.Button(edit_frame, text="Add to Ignore List", bg=BG_PANEL, fg=TEXT_PRIMARY, relief="flat", cursor="hand2", padx=8, command=self._add_ignore)
        btn_add.pack(side="left", padx=4)

        btn_del = tk.Button(edit_frame, text="Remove", bg=BG_PANEL, fg=ACCENT_RED, relief="flat", cursor="hand2", padx=8, command=self._del_ignore)
        btn_del.pack(side="left")

    def _refresh_ignored_list(self):
        self.ignored_box.delete(0, tk.END)
        for exe in sorted(self.current_ignored):
            self.ignored_box.insert(tk.END, exe)

    def _add_ignore(self):
        exe = self.entry_ignore_exe.get().strip().lower()
        if exe:
            if not exe.endswith(".exe"):
                exe += ".exe"
            if exe not in self.current_ignored:
                self.current_ignored.append(exe)
                self._refresh_ignored_list()
                self.entry_ignore_exe.delete(0, tk.END)

    def _del_ignore(self):
        sel = self.ignored_box.curselection()
        if sel:
            exe = self.ignored_box.get(sel[0])
            if exe in self.current_ignored:
                self.current_ignored.remove(exe)
                self._refresh_ignored_list()

    def _save_all(self):
        # Validate App ID
        app_id = self.var_appid.get().strip()
        valid, err = validate_app_id(app_id)
        if not valid:
            messagebox.showerror("Invalid Application ID", err)
            return

        self.config["application_id"] = app_id
        self.config["auto_close_with_discord"] = self.var_autoclose.get()
        self.config["taglines"] = self.current_taglines
        self.config["ignored_exes"] = self.current_ignored

        try:
            self.config["debounce_seconds"] = int(self.var_debounce.get())
            self.config["idle_timeout_seconds"] = int(self.var_idle.get())
        except ValueError:
            pass

        # Windows Startup toggle
        set_autostart_enabled(self.var_autostart.get())

        save_config(self.config)
        if self.on_saved:
            self.on_saved(self.config)

        messagebox.showinfo("Saved", "Settings saved successfully!")
        self.win.destroy()

    def run(self):
        self.win.mainloop()


def open_settings_gui(on_saved: Optional[Callable[[dict], None]] = None):
    """Launch Settings GUI in a standalone or main thread."""
    win = SettingsWindow(on_saved=on_saved)
    win.run()
