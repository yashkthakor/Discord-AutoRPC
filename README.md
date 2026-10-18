<div align="center">

# Discord AutoRPC

**Automatic Discord Rich Presence for any Windows app or game.**

Real 256×256 icons, contextual activity lines, and a timer that ticks — with
nothing to configure inside Discord.

[![Release](https://img.shields.io/badge/release-v0.1.0--beta-5865F2?style=flat-square)](https://github.com/yashkthakor/Discord-AutoRPC/releases)
[![Platform](https://img.shields.io/badge/platform-windows%2010%20%7C%2011-0078D6?style=flat-square)](https://github.com/yashkthakor/Discord-AutoRPC)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-brightgreen?style=flat-square)](LICENSE)

</div>

Discord AutoRPC lives in the system tray and watches your foreground window.
When the active app changes it extracts the application's own icon, composes a
short contextual line for it, and publishes both to your Discord profile — at
most one update every 15 seconds, so the timer on your profile keeps ticking
smoothly.

> [!NOTE]
> **Open beta (`v0.1.0-beta`).** Rough edges are expected. Bugs, questions and
> tagline requests are welcome in
> [Issues](https://github.com/yashkthakor/Discord-AutoRPC/issues).

## Features

- **Any app or game, automatically.** Whatever executable has focus gets
  broadcast — there is no per-game setup in Discord.
- **Native 256×256 icons.** Extracted from the binary itself with Windows'
  `PrivateExtractIconsW`, not scaled up from a thumbnail.
- **Contextual taglines.** The second line is built from the window title —
  browsers get *Surfing the internet*, documents *Working on a document*,
  editors *Working on a project*.
- **A timer that keeps ticking.** The presence is sent once and left alone, so
  the counter on your profile advances every second instead of resetting with
  each update.
- **Private browsing stays private.** Incognito and private windows across
  Chrome, Edge, Firefox, Brave, Zen and friends are masked, never broadcast.
- **Lifecycle aware.** When the Discord client exits, AutoRPC stops
  broadcasting and hides its tray icon, then restores both when Discord is
  back (configurable via `auto_close_with_discord`).
- **Settings, not JSON.** A first-run wizard opens the Discord Developer Portal
  and validates your Application ID; after that everything — taglines,
  overrides, the ignore list, timing — is a few clicks in the settings window.

## Install

### Prebuilt (recommended)

No Python required.

1. Download `DiscordAutoRPC-v0.1.0-beta-windows-x64.zip` (or the bare
   `DiscordAutoRPC.exe`) from
   [Releases](https://github.com/yashkthakor/Discord-AutoRPC/releases).
2. Run `DiscordAutoRPC.exe`. The setup wizard starts on first launch:
   - Click **Open Discord Developer Portal**, create a new application (any
     name), and copy its **Application ID**.
   - Paste it into the wizard and choose **Save & Launch AutoRPC**.
3. That's it — AutoRPC waits in the tray. Open any app and check your Discord
   profile.

### From source

Windows 10/11 (64-bit), Python 3.11+, and the Discord desktop client running.

```bash
git clone https://github.com/yashkthakor/Discord-AutoRPC.git
cd Discord-AutoRPC
pip install -r requirements.txt

python main.py             # run it
pythonw main.py --startup  # or, without a console window
```

To build the standalone executable:

```bash
pip install pyinstaller
python -m PyInstaller --noconsole --onefile --icon="assets/icon.ico" --name="DiscordAutoRPC" main.py
```

The result lands in `dist/`. Releases are built by CI from a `v*` tag.

## Configuration

`config.json` sits next to the executable in portable mode (a `portable.txt`
or an existing `config.json` beside it) and in `%APPDATA%\DiscordAutoRPC\`
otherwise. Everything in it is editable from Settings; a ready-to-edit
template ships as [`config.example.json`](config.example.json).

| Key | Default | Purpose |
|---|---|---|
| `application_id` | `""` | Your Discord application ID. Required. |
| `poll_interval` | `5` | Seconds between foreground checks. |
| `debounce_seconds` | `10` | Focus time an app needs before it is broadcast. |
| `idle_timeout_seconds` | `60` | Clear the presence after this much inactivity. |
| `default_icon_url` | Discord's default avatar | Fallback icon when extraction fails. |
| `auto_close_with_discord` | `true` | Go dormant while the Discord client is closed. |
| `mask_private_browsing` | `true` | Never broadcast incognito/private windows. |
| `whitelist_only` | `false` | Broadcast only what is in `whitelist`. |
| `whitelist` | `[]` | Executable names, used when `whitelist_only` is on. |
| `ignored_exes` | system shells and Explorer | Executable names that are never broadcast. |
| `taglines` | built-in table | Static second line per executable. |
| `overrides` | `{}` | Per-executable `name` / `tagline` / `icon_url` that wins over everything. |
| `steamgriddb_api_key` | `""` | Optional SteamGridDB key for game icons. |
| `upload_host` | `"freeimage"` | Icon upload host: `freeimage` or `catbox`. |
| `enable_dynamic_taglines` | `true` | Build the second line from the window title. |

For example, giving one game a custom name, line and icon:

```jsonc
"overrides": {
  "example_game.exe": {
    "name": "My Cool Game",
    "tagline": "Playing a custom game",
    "icon_url": "https://example.com/icon.png"
  }
}
```

Icons are extracted locally and uploaded to the chosen host over HTTPS, because
Discord needs a URL for them; the results are cached in `icon_cache.json`. No
raw window titles or file paths are uploaded anywhere.

## Tray menu

| Item | Action |
|---|---|
| `Discord AutoRPC v0.1.0-beta` | Version marker; becomes an update notice (opens the release page) when a newer release exists. |
| `Settings` | The configuration window. |
| `Rename Active App…` | Rename / re-tag whatever is focused right now. |
| `Pause` / `Resume` | Stop broadcasting for a while. |
| `Ignore current app` | Add the focused app to `ignored_exes`. |
| `Open log` | Open `autorpc.log`. |
| `Quit` | Clear the presence and exit. |

## How it works

- The foreground window is polled every `poll_interval` seconds, then filtered
  through the ignore list, the whitelist, private-browsing detection and a
  debounce window.
- Display names come from the executable's version information; the tagline
  comes from parsing the window title (`context.py`).
- Icons are extracted at 256×256, cached to disk, and uploaded once per app.
- The presence payload is deduplicated and rate-limited to one update every 15
  seconds — which is what keeps the timer on your profile honest.

This engine is also driven headlessly by the next-generation UI under
[`desktop/`](desktop) (Tauri 2 + React, in development); see
[`GUI_HANDOFF_TAURI_REACT.md`](GUI_HANDOFF_TAURI_REACT.md).

## Contributing

Bug reports, feature requests and pull requests are all welcome.

1. Fork the repository.
2. Create a branch (`git checkout -b feature/my-change`).
3. Commit and push it.
4. Open a pull request.

## License

MIT — see [`LICENSE`](LICENSE).
