@echo off
setlocal
echo Removing Discord AutoRPC Watcher from Windows Startup...

set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\DiscordAutoRPCWatcher.lnk"

if exist "%SHORTCUT_PATH%" (
    del "%SHORTCUT_PATH%"
    echo [SUCCESS] AutoRPC Watcher removed from Windows Startup.
) else (
    echo [INFO] Shortcut was not found in Startup folder.
)

powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*watcher.pyw*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Stopped any running watcher instances.
pause
