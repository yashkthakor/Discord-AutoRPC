//! `config.json` — read, merge, write.
//!
//! Three rules this module exists to enforce:
//!
//! 1. **Byte compatibility.** The Python build still reads this file, so unknown keys are
//!    preserved verbatim and the file stays pretty-printed JSON with a trailing newline.
//! 2. **Atomic writes.** Write to a temp file, then rename over the target (`B-10`).
//! 3. **Never lie about a write.** Every mutation returns the value that is now on disk.

use serde_json::Value;

use crate::paths::{self, write_atomic};

/// Mirrors `config.py::DEFAULT_CONFIG`.
///
/// **This is a deliberate Phase-1 duplication** and it is tracked: the Python engine owns
/// these defaults, and T-025 moves them onto the engine protocol so there is one source of
/// truth. Until then, keep this block and `config.py` in step by hand — and remember that
/// `config.example.json` mirrors the same table for users.
const DEFAULT_CONFIG_JSON: &str = r#"{
  "application_id": "",
  "poll_interval": 5,
  "debounce_seconds": 10,
  "idle_timeout_seconds": 60,
  "default_icon_url": "https://cdn.discordapp.com/embed/avatars/0.png",
  "auto_close_with_discord": true,
  "mask_private_browsing": true,
  "whitelist_only": false,
  "whitelist": [],
  "ignored_exes": [
    "explorer.exe",
    "Discord.exe",
    "SearchHost.exe",
    "StartMenuExperienceHost.exe",
    "ShellExperienceHost.exe",
    "SystemSettings.exe",
    "ApplicationFrameHost.exe",
    "TextInputHost.exe",
    "LockApp.exe",
    "ScreenClippingHost.exe",
    "WidgetService.exe",
    "Widgets.exe"
  ],
  "taglines": {
    "notion.exe": "Working on a document",
    "antigravity ide.exe": "Working on a project",
    "chrome.exe": "Surfing the internet",
    "firefox.exe": "Surfing the internet",
    "msedge.exe": "Surfing the internet",
    "brave.exe": "Surfing the internet",
    "zen.exe": "Surfing the internet"
  },
  "overrides": {},
  "steamgriddb_api_key": "",
  "upload_host": "freeimage",
  "enable_dynamic_taglines": true
}"#;

const APP_ID_MIN: usize = 17;
const APP_ID_MAX: usize = 21;

pub fn defaults() -> Value {
    serde_json::from_str(DEFAULT_CONFIG_JSON).expect("DEFAULT_CONFIG_JSON is valid")
}

/// Effective config: defaults with the file's own keys layered on top.
///
/// The merge is shallow, exactly like `load_config()` in `config.py`. Keeping it shallow is
/// what preserves user edits to `taglines` and `overrides` as complete maps.
pub fn load() -> Value {
    let mut merged = defaults();

    if let Some(raw) = paths::read_to_string(&paths::config_path()) {
        if let Ok(Value::Object(file)) = serde_json::from_str::<Value>(&raw) {
            if let Value::Object(target) = &mut merged {
                for (key, value) in file {
                    target.insert(key, value);
                }
            }
        }
    }

    merged
}

fn write(value: &Value) -> Result<(), String> {
    let mut text = serde_json::to_string_pretty(value).map_err(|e| format!("couldn't encode config: {e}"))?;
    text.push('\n');

    write_atomic(&paths::config_path(), text.as_bytes())
        .map_err(|e| format!("couldn't write config.json: {e}"))
}

/// Apply a patch and persist it. Returns the effective config after the write.
pub fn update(patch: Value) -> Result<Value, String> {
    let mut current = load();

    if let (Value::Object(target), Value::Object(incoming)) = (&mut current, patch) {
        for (key, value) in incoming {
            target.insert(key, value);
        }
    }

    write(&current)?;
    Ok(current)
}

/// Restore the shipped defaults. Also returns what was written.
pub fn reset() -> Result<Value, String> {
    let value = defaults();
    write(&value)?;
    Ok(value)
}

/// Replace one map entry (`overrides`, `taglines`) without touching the rest.
pub fn set_map_entry(field: &str, key: &str, value: Option<Value>) -> Result<Value, String> {
    let mut current = load();

    let target = current
        .get_mut(field)
        .and_then(Value::as_object_mut)
        .cloned()
        .unwrap_or_default();

    let mut next = target;
    match value {
        Some(entry) => {
            next.insert(key.to_string(), entry);
        }
        None => {
            next.remove(key);
        }
    }

    current[field] = Value::Object(next);
    write(&current)?;
    Ok(current)
}

/// The exe-key format shared by `overrides`, `taglines`, `whitelist` and `ignored_exes`:
/// lowercased, trimmed, quoted forms unwrapped, and always `.exe`-suffixed.
pub fn normalize_exe(exe: &str) -> String {
    let trimmed = exe.trim().trim_matches('"').to_ascii_lowercase();
    if trimmed.is_empty() {
        return String::new();
    }
    if trimmed.ends_with(".exe") {
        trimmed
    } else {
        format!("{trimmed}.exe")
    }
}

pub fn string_field(config: &Value, field: &str) -> String {
    config.get(field).and_then(Value::as_str).unwrap_or_default().to_string()
}

pub fn string_list(config: &Value, field: &str) -> Vec<String> {
    config
        .get(field)
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default()
}

/// The same acceptance rule as `config.validate_app_id`, digits only, 17–21.
pub fn is_valid_app_id(app_id: &str) -> bool {
    let trimmed = app_id.trim();
    !trimmed.is_empty()
        && trimmed.len() >= APP_ID_MIN
        && trimmed.len() <= APP_ID_MAX
        && trimmed.chars().all(|c| c.is_ascii_digit())
}

pub fn is_configured(config: &Value) -> bool {
    is_valid_app_id(&string_field(config, "application_id"))
}
