<div align="center">

# 🎮 Discord AutoRPC

### Automatic, High-Resolution Discord Rich Presence for Any Windows App or Game

[![Release](https://img.shields.io/badge/release-v0.1.0--beta-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://github.com/yashkthakor/Discord-AutoRPC/releases)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20%2F%2011-0078D6?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/yashkthakor/Discord-AutoRPC)
[![Python](https://img.shields.io/badge/python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

> **Discord AutoRPC** monitors your active foreground window and instantly broadcasts it to your Discord profile as a dynamic Rich Presence — featuring **native 256×256 crystal-clear icons**, **contextual activity taglines**, and **smooth second-by-second timers** — even for apps and games Discord doesn't natively recognize.

<br/>

> [!NOTE]
> ⚠️ **Open Beta (v0.1.0-beta)**: This project is currently in active open beta. If you encounter any edge cases or wish to request new built-in taglines, please open an [Issue](https://github.com/yashkthakor/Discord-AutoRPC/issues).

</div>

---

## ✨ Key Features

- **⚡ Instant App & Game Detection**: Automatically tracks whatever executable is in focus without needing to configure games in Discord settings.
- **🎨 Native 256×256 Icons**: Uses Windows Win32 `PrivateExtractIconsW` to extract uncompressed high-resolution icons directly from binaries for razor-sharp display on your Discord profile card.
- **💬 Smart Contextual Taglines**: Shows human-friendly details instead of redundant names:
  - 📝 **Notion / Office**: *"Working on a document"*
  - 💻 **IDEs & Code Editors**: *"Working on a project"*
  - 🌐 **Web Browsers**: *"Surfing the internet"*
  - 🎨 **Creative Tools**: *"Designing something"*
- **⏱️ Smooth Second-by-Second Timers**: Discord's UI timer counts up every single second natively without 15-second rate-limit pauses or UI stutter.
- **🛡️ Incognito & Privacy Shield**: Automatically detects Private / Incognito browser sessions (Chrome, Edge, Firefox, Brave, Zen) and masks or suppresses presence so private browsing is never broadcasted.
- **🔄 Discord Process Lifecycle Sync**: Runs silently in the system tray. When Discord is closed, AutoRPC automatically closes itself to save system resources.
- **⚙️ Native Dark Mode Settings GUI**: Right-click the tray icon to open a full graphical settings manager. Easily customize taglines, tune debounce sliders, and toggle startup options without editing JSON files.
- **🚀 Guided 60-Second Setup**: Built-in setup wizard with a one-click button to open the Discord Developer Portal and validate your Application ID.

---

## 🚀 Quick Start (Pre-Compiled Executable)

No Python installation required!

1. **Download**: Go to [**Releases**](https://github.com/yashkthakor/Discord-AutoRPC/releases) and download `DiscordAutoRPC-v0.1.0-beta-windows-x64.zip` (or `DiscordAutoRPC.exe`).
2. **Run**: Double-click `DiscordAutoRPC.exe`.
3. **Setup Wizard**: On first launch, the setup wizard will open:
   - Click **`🌐 Open Discord Developer Portal`**.
   - Click **`New Application`** and name it whatever you like (e.g. *Auto Presence* or your username).
   - Copy your numeric **`Application ID`** and paste it into the box.
   - Click **`Save & Launch AutoRPC`**.
4. **Done**: AutoRPC minimizes to your system tray. Open any app or game to see your Discord profile update automatically!

---

## 🛠️ Running from Source

If you prefer to run or build from Python source:

### Prerequisites
- Windows 10 or 11 (64-bit)
- Python 3.11 or higher
- Discord Desktop Client running

### Installation

```bash
# Clone the repository
git clone https://github.com/yashkthakor/Discord-AutoRPC.git
cd Discord-AutoRPC

# Install dependencies
pip install -r requirements.txt

# Run Discord AutoRPC
python main.py
```

### Building the Standalone Executable

```bash
pip install pyinstaller
python -m PyInstaller --noconsole --onefile --icon="assets/icon.ico" --name="DiscordAutoRPC" main.py
```
The compiled executable will be generated in the `dist/` directory.

---

## ⚙️ Configuration Reference

Settings can be changed visually via the **`⚙️ Settings`** tray menu, or directly in `config.json`:

```jsonc
{
  "application_id": "YOUR_DISCORD_APP_ID", // Required: Your personal Discord App ID
  "poll_interval": 5,                     // Seconds between foreground checks
  "debounce_seconds": 10,                 // Required focus time before switching app
  "idle_timeout_seconds": 60,             // Idle timeout before clearing presence
  "auto_close_with_discord": true,        // Automatically exit when Discord closes
  "mask_private_browsing": true,          // Suppress presence in Incognito windows
  "taglines": {                           // Custom contextual lines per app
    "notion.exe": "Working on a document",
    "antigravity ide.exe": "Working on a project",
    "zen.exe": "Surfing the internet"
  },
  "ignored_exes": [                       // Apps that are never broadcasted
    "explorer.exe",
    "SearchHost.exe"
  ]
}
```

---

## 🧭 System Tray Menu

Right-click the **AutoRPC** icon in your system tray to access:
- **`⭐ Update Available`**: Shows when a newer version is released on GitHub.
- **`⚙️ Settings`**: Open the full GUI configuration window.
- **`⏸️ Pause / ▶️ Resume`**: Temporarily stop presence updates.
- **`🚫 Ignore current app`**: Instantly blacklist the focused app.
- **`📋 Open log`**: View live application logs for troubleshooting.
- **`❌ Quit`**: Cleanly disconnect from Discord RPC and shut down.

---

## 🤝 Contributing

Contributions, feature requests, and bug reports are welcome!
1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📜 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for more information.
