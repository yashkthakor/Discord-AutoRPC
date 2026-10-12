"""
watcher.pyw — Silent background monitor for Discord AutoRPC.

Runs silently without a console window (using pythonw).
Monitors for Discord.exe:
  • When Discord starts → Launches main.py (using pythonw for zero clutter)
  • When Discord exits → main.py auto-closes (via auto_close_with_discord)
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

BASE_DIR = Path(__file__).resolve().parent
MAIN_PY = BASE_DIR / "main.py"
DISCORD_EXES = {"discord.exe", "discordcanary.exe", "discordptb.exe", "discorddevelopment.exe"}


def is_discord_running() -> bool:
    for proc in psutil.process_iter(["name"]):
        try:
            name = proc.info.get("name")
            if name and name.lower() in DISCORD_EXES:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def is_autorpc_running() -> bool:
    main_str = str(MAIN_PY).lower()
    for proc in psutil.process_iter(["cmdline", "pid"]):
        try:
            # Exclude current watcher process
            if proc.pid == os.getpid():
                continue
            cmdline = proc.info.get("cmdline")
            if cmdline:
                cmd_joined = " ".join(cmdline).lower()
                if "main.py" in cmd_joined and ("python" in cmd_joined or "pythonw" in cmd_joined):
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def main():
    # Find pythonw.exe in the current Python environment
    py_executable = sys.executable
    if "python.exe" in py_executable.lower():
        pyw_executable = py_executable.lower().replace("python.exe", "pythonw.exe")
        if not os.path.exists(pyw_executable):
            pyw_executable = py_executable
    else:
        pyw_executable = py_executable

    while True:
        try:
            discord_active = is_discord_running()
            autorpc_active = is_autorpc_running()

            if discord_active and not autorpc_active:
                # Start AutoRPC in the background
                subprocess.Popen(
                    [pyw_executable, str(MAIN_PY)],
                    cwd=str(BASE_DIR),
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )

            time.sleep(3)
        except Exception:
            time.sleep(5)


if __name__ == "__main__":
    main()
