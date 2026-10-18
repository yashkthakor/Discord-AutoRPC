//! `ui_prefs.json` — the appearance preference (A5 / D-024).
//!
//! Deliberately a separate file from `config.json`: the preference belongs to the new UI,
//! and writing it into `config.json` would put a key in front of the Python build that it
//! does not know about. Unknown keys are preserved on write so a future preference does not
//! get clobbered by an older build.

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

use crate::paths::{self, write_atomic};

pub const SYSTEM: &str = "system";
pub const LIGHT: &str = "light";
pub const DARK: &str = "dark";

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct Prefs {
    pub appearance: String,
}

impl Default for Prefs {
    fn default() -> Self {
        Self {
            appearance: SYSTEM.to_string(),
        }
    }
}

/// Anything unrecognised is System — never an error, never a crash (A5).
pub fn normalize(value: &str) -> String {
    match value.trim().to_ascii_lowercase().as_str() {
        LIGHT => LIGHT.to_string(),
        DARK => DARK.to_string(),
        _ => SYSTEM.to_string(),
    }
}

fn read_object() -> Map<String, Value> {
    paths::read_to_string(&paths::prefs_path())
        .and_then(|raw| serde_json::from_str::<Value>(&raw).ok())
        .and_then(|value| match value {
            Value::Object(map) => Some(map),
            _ => None,
        })
        .unwrap_or_default()
}

pub fn load() -> Prefs {
    let appearance = read_object()
        .get("appearance")
        .and_then(Value::as_str)
        .map(normalize)
        .unwrap_or_else(|| SYSTEM.to_string());

    Prefs { appearance }
}

pub fn save(appearance: &str) -> Result<Prefs, String> {
    let normalized = normalize(appearance);

    let mut object = read_object();
    object.insert("appearance".to_string(), Value::String(normalized.clone()));

    let mut text = serde_json::to_string_pretty(&Value::Object(object))
        .map_err(|e| format!("couldn't encode ui_prefs.json: {e}"))?;
    text.push('\n');

    write_atomic(&paths::prefs_path(), text.as_bytes())
        .map_err(|e| format!("couldn't write ui_prefs.json: {e}"))?;

    Ok(Prefs { appearance: normalized })
}
