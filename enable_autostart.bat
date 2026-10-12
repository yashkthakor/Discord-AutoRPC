@echo off
setlocal
echo Setting up Discord AutoRPC Watcher in Windows Startup...

set "SCRIPT_DIR=%~dp0"
set "WATCHER_PATH=%SCRIPT_DIR%watcher.pyw"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\DiscordAutoRPCWatcher.lnk"

powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; ^
   $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); ^
   $s.TargetPath = 'pythonw.exe'; ^
   $s.Arguments = '\"%WATCHER_PATH%\"'; ^
   $s.WorkingDirectory = '%SCRIPT_DIR%'; ^
   $s.WindowStyle = 7; ^
   $s.Save()"

if exist "%SHORTCUT_PATH%" (
    echo [SUCCESS] AutoRPC Watcher added to Windows Startup!
    echo It will now run silently whenever you log in, launching AutoRPC when Discord opens, and closing it when Discord closes.
    echo Starting the watcher right now...
    start "" pythonw "%WATCHER_PATH%"
) else (
    echo [ERROR] Failed to create startup shortcut.
)
pause
