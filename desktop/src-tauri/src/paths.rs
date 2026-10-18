//! Data-directory resolution.
//!
//! Mirrors `config.get_data_dir()` so the Tauri shell and the Python engine read and write
//! the same files (AGENTS.md §4):
//!
//! - `AUTORPC_DATA_DIR` wins outright — used by dev runs that want a scratch directory.
//! - a debug build uses the repository root, which is what the Python build does when it
//!   is not frozen.
//! - a release build uses the directory the exe sits in when `portable.txt` or
//!   `config.json` is next to it, otherwise `%APPDATA%\DiscordAutoRPC`.
//!
//! Nothing here caches the result: the Python build had a real bug class around capturing
//! the data dir at import time, so every call re-resolves.

use std::fs;
use std::io;
use std::path::{Path, PathBuf};

const APPDATA_FOLDER: &str = "DiscordAutoRPC";

pub fn data_dir() -> PathBuf {
    if let Ok(explicit) = std::env::var("AUTORPC_DATA_DIR") {
        let trimmed = explicit.trim();
        if !trimmed.is_empty() {
            let path = PathBuf::from(trimmed);
            let _ = fs::create_dir_all(&path);
            return path;
        }
    }

    if cfg!(debug_assertions) {
        if let Some(root) = repo_root() {
            return root;
        }
    }

    if let Some(dir) = portable_dir() {
        return dir;
    }

    let base = std::env::var("APPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(|_| std::env::temp_dir());
    let dir = base.join(APPDATA_FOLDER);
    let _ = fs::create_dir_all(&dir);
    dir
}

/// `desktop/src-tauri` → `desktop` → repository root.
fn repo_root() -> Option<PathBuf> {
    let manifest = Path::new(env!("CARGO_MANIFEST_DIR"));
    let root = manifest.parent()?.parent()?;
    if root.join("config.example.json").is_file() {
        Some(root.to_path_buf())
    } else {
        None
    }
}

fn portable_dir() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let dir = exe.parent()?.to_path_buf();
    if dir.join("portable.txt").is_file() || dir.join("config.json").is_file() {
        Some(dir)
    } else {
        None
    }
}

pub fn config_path() -> PathBuf {
    data_dir().join("config.json")
}

pub fn prefs_path() -> PathBuf {
    data_dir().join("ui_prefs.json")
}

pub fn log_path() -> PathBuf {
    data_dir().join("autorpc.log")
}

pub fn icon_cache_path() -> PathBuf {
    data_dir().join("icon_cache.json")
}

pub fn legacy_ignore_path() -> PathBuf {
    data_dir().join("ignore_list.json")
}

pub fn exports_dir() -> PathBuf {
    let dir = data_dir().join("exports");
    let _ = fs::create_dir_all(&dir);
    dir
}

/// Write-then-rename. `create_dir_all` first, then a sibling temp file, then a replace.
///
/// The Python build writes `config.json` in place, which can truncate it if the process
/// dies mid-write (`B-10`). This is the fix, and it is deliberately used for every file.
pub fn write_atomic(path: &Path, contents: &[u8]) -> io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }

    let temp = path.with_extension("tmp");
    fs::write(&temp, contents)?;
    fs::rename(&temp, path)
}

pub fn read_to_string(path: &Path) -> Option<String> {
    fs::read_to_string(path).ok()
}

pub fn now_ms() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

/// A filesystem-safe timestamp for exported file names.
pub fn stamp() -> String {
    let ms = now_ms();
    let secs = ms / 1000;
    format!("{secs}")
}
