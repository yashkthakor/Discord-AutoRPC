//! The unified ignore list (A18 / D-037 / D-047).
//!
//! What the engine actually honours (`detector.is_ignored`):
//!
//! 1. any exe whose path starts with `%SystemRoot%` — hardcoded, read-only;
//! 2. `config.ignored_exes` — the static list, seeded with twelve Windows apps;
//! 3. `ignore_list.json` — what the Python tray's “Ignore current app” wrote.
//!
//! The new UI presents one list and writes one file: **`config.ignored_exes`**. That is the
//! file the Python Settings pane already wrote, so behaviour is unchanged for that build,
//! and it is where the twelve shipped defaults live.
//!
//! `ignore_list.json` is neither deleted nor rewritten. On startup any entry in it that is
//! missing from `config.ignored_exes` is copied across (a union, so it is idempotent and
//! reversible), and anything still un-copied is surfaced in a separate read-only group
//! rather than being hidden.

use serde::Serialize;
use serde_json::Value;

use crate::config_file;
use crate::paths::{self, write_atomic};

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct IgnoredListing {
    /// The editable list: `config.ignored_exes`.
    pub managed: Vec<String>,
    /// Entries from `ignore_list.json` that are not in `managed` yet.
    pub legacy: Vec<String>,
    /// The shipped seeds, used to tag rows and to offer “restore defaults”.
    pub defaults: Vec<String>,
}

/// Lowercase, trimmed, `.exe`-suffixed — the same normalization the UI applies (I-3).
pub fn normalize(exe: &str) -> String {
    config_file::normalize_exe(exe)
}

fn read_legacy() -> Vec<String> {
    paths::read_to_string(&paths::legacy_ignore_path())
        .and_then(|raw| serde_json::from_str::<Value>(&raw).ok())
        .and_then(|value| match value {
            Value::Array(items) => Some(
                items
                    .into_iter()
                    .filter_map(|item| item.as_str().map(str::to_string))
                    .collect::<Vec<_>>(),
            ),
            _ => None,
        })
        .unwrap_or_default()
}

pub fn load() -> IgnoredListing {
    let config = config_file::load();
    let managed = config_file::string_list(&config, "ignored_exes");
    let defaults = config_file::string_list(&config_file::defaults(), "ignored_exes");

    let legacy = read_legacy()
        .into_iter()
        .filter(|item| !managed.iter().any(|known| known.eq_ignore_ascii_case(item)))
        .collect();

    IgnoredListing {
        managed,
        legacy,
        defaults,
    }
}

fn write_managed(list: Vec<String>) -> Result<(), String> {
    config_file::update(serde_json::json!({ "ignored_exes": list })).map(|_| ())
}

/// Copy any `ignore_list.json` entries into `config.ignored_exes`. Returns how many moved.
///
/// Safe to run on every launch: it only ever adds entries that are missing.
pub fn migrate() -> Result<usize, String> {
    let listing = load();
    if listing.legacy.is_empty() {
        return Ok(0);
    }

    let mut managed = listing.managed;
    let mut moved = 0usize;

    for item in &listing.legacy {
        if !managed.iter().any(|known| known.eq_ignore_ascii_case(item)) {
            managed.push(normalize(item));
            moved += 1;
        }
    }

    if moved > 0 {
        write_managed(managed)?;
    }

    Ok(moved)
}

pub fn add(exe: &str) -> Result<(), String> {
    let key = normalize(exe);
    if key.is_empty() {
        return Err("That doesn't look like an executable name.".to_string());
    }

    let mut managed = load().managed;
    if managed.iter().any(|known| known.eq_ignore_ascii_case(&key)) {
        return Ok(());
    }

    managed.push(key);
    write_managed(managed)
}

pub fn remove(exe: &str) -> Result<(), String> {
    let key = normalize(exe);
    let managed: Vec<String> = load()
        .managed
        .into_iter()
        .filter(|known| !known.eq_ignore_ascii_case(&key))
        .collect();

    write_managed(managed)
}

/// Union the shipped defaults back in without discarding the user's own entries.
///
/// Not wired to a button yet: the shipped twelve are ordinary editable entries, so a user
/// who removes one by mistake adds it back by name. Kept as the hook for a "restore
/// defaults" action if that turns out to be too fiddly in practice.
#[allow(dead_code)]
pub fn restore_defaults() -> Result<(), String> {
    let mut managed = load().managed;

    for item in config_file::string_list(&config_file::defaults(), "ignored_exes") {
        if !managed.iter().any(|known| known.eq_ignore_ascii_case(&item)) {
            managed.push(item);
        }
    }

    write_managed(managed)
}

/// Drop the legacy file once its contents are represented in the managed list.
///
/// Not called anywhere yet — the Python build still reads `ignore_list.json`, so removing
/// it is a deliberate, separate decision (D-047).
#[allow(dead_code)]
pub fn remove_legacy_file() -> Result<(), String> {
    std::fs::remove_file(paths::legacy_ignore_path()).map_err(|e| format!("couldn't remove ignore_list.json: {e}"))
}

/// Convenience for the tray: is this exe currently ignored?
#[allow(dead_code)]
pub fn contains(exe: &str) -> bool {
    let key = normalize(exe);
    load()
        .managed
        .iter()
        .chain(read_legacy().iter())
        .any(|known| known.eq_ignore_ascii_case(&key))
}

#[allow(dead_code)]
fn write_legacy(list: Vec<String>) -> Result<(), String> {
    let mut text = serde_json::to_string_pretty(&list).map_err(|e| format!("encode: {e}"))?;
    text.push('\n');
    write_atomic(&paths::legacy_ignore_path(), text.as_bytes()).map_err(|e| format!("write: {e}"))
}
