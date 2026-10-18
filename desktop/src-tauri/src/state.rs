//! Shared in-memory state, and the wire types the frontend consumes.
//!
//! The TypeScript contract in `src/ipc/types.ts` is the other half of these structs:
//! `camelCase` on the wire (hence the serde rename), `null` for “nothing”, and enum-ish
//! string unions rather than Rust enums so an unknown value can never fail to deserialize.

use std::sync::Mutex;

use serde::{Deserialize, Serialize};

pub const ENGINE_OFFLINE: &str = "offline";
pub const ENGINE_WAITING: &str = "waiting";
pub const ENGINE_ACTIVE: &str = "active";
pub const ENGINE_PAUSED: &str = "paused";

pub const DISCORD_CONNECTED: &str = "connected";
/// Part of the status vocabulary: the engine may report this while the IPC handshake is in
/// flight. The shell never sets it — it only accepts it from the engine (`T-022`).
pub const DISCORD_CONNECTING: &str = "connecting";
pub const DISCORD_OFFLINE: &str = "offline";
pub const DISCORD_NOT_RUNNING: &str = "not-running";

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AppInfo {
    pub exe: String,
    pub path: String,
    pub pid: u32,
    pub display_name: String,
    pub tagline: Option<String>,
    pub icon_url: Option<String>,
    /// The engine's icon retry ladder (`T-030`). `None` when it did not report one.
    #[serde(default)]
    pub icon: Option<IconStatus>,
    pub started_at_ms: Option<u64>,
    pub ignored: bool,
}

impl AppInfo {
    pub fn new(exe: &str, path: &str, display_name: &str) -> Self {
        Self {
            exe: exe.to_string(),
            path: path.to_string(),
            pid: 0,
            display_name: display_name.to_string(),
            tagline: None,
            icon_url: None,
            icon: None,
            started_at_ms: None,
            ignored: false,
        }
    }
}

/// Where the engine's icon resolution stands for the app on screen (`T-030`).
///
/// `state` is `"ok" | "pending" | "parked"`: the URL is in hand, the ladder is between
/// attempts, or the three attempts failed and the default icon shows until `retry_at_ms`.
/// A plain string, like every other union on this wire, so a newer engine cannot fail to
/// deserialize.
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct IconStatus {
    pub state: String,
    pub attempts: u32,
    pub retry_at_ms: Option<u64>,
    pub reason: Option<String>,
}

/// One row of `icon_cache.json`, as the settings pane lists it (`T-030`).
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct IconCacheEntry {
    pub path: String,
    pub url: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct EngineState {
    pub version: String,
    pub engine: String,
    pub discord: String,
    pub configured: bool,
    pub update_tag: Option<String>,
    pub app: Option<AppInfo>,
    pub recent_apps: Vec<String>,
    pub autostart_enabled: bool,
    /// The engine's `icon_cache.json`, for the App Names pane (`T-030`). Empty until the
    /// engine answers — an empty list means "not asked yet", never "nothing cached".
    pub icon_cache: Vec<IconCacheEntry>,
}

impl EngineState {
    pub fn offline() -> Self {
        Self {
            version: env!("CARGO_PKG_VERSION").to_string(),
            engine: ENGINE_OFFLINE.to_string(),
            discord: DISCORD_OFFLINE.to_string(),
            configured: false,
            update_tag: None,
            app: None,
            recent_apps: Vec::new(),
            autostart_enabled: false,
            icon_cache: Vec::new(),
        }
    }
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LogLine {
    pub id: u64,
    pub ts: u64,
    pub level: String,
    pub logger: String,
    pub message: String,
    /// Set only for lines read back out of `autorpc.log`. That file stamps each line with a
    /// full date; the view shows just the clock part, so this is already stripped.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub display_time: Option<String>,
}

/// Emitted whenever the main window is resized, so the custom chrome can swap the maximize
/// glyph for a restore glyph (D-055). Only the boolean crosses the wire; the frontend never
/// asks the OS what the state is.
#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct WindowChrome {
    pub maximized: bool,
}

/// Managed state. A single mutex is enough: writes are rare (an app switch every few
/// seconds), and reads clone a small struct.
pub struct Shared {
    engine: Mutex<EngineState>,
}

impl Default for Shared {
    fn default() -> Self {
        Self {
            engine: Mutex::new(EngineState::offline()),
        }
    }
}

impl Shared {
    pub fn snapshot(&self) -> EngineState {
        self.engine
            .lock()
            .map(|guard| guard.clone())
            .unwrap_or_else(|poisoned| poisoned.into_inner().clone())
    }

    pub fn mutate<F: FnOnce(&mut EngineState)>(&self, change: F) {
        match self.engine.lock() {
            Ok(mut guard) => change(&mut guard),
            Err(poisoned) => change(&mut poisoned.into_inner()),
        }
    }
}
