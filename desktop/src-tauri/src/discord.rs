//! A real Discord IPC probe for the “Test connection” button (G-1 / OB-12).
//!
//! Discord exposes a named pipe per client (`\\.\pipe\discord-ipc-0`, then `-1`, …). The
//! handshake is a tiny framed JSON message, so this needs no dependency beyond `serde_json`
//! and a reader thread with a timeout — a pipe that accepts a connection but never answers
//! must not hang the UI.
//!
//! Scope note: this only *tests*. Presence itself is owned by the engine, not by the shell.

use std::fs::OpenOptions;
use std::io::{Read, Write};
use std::sync::mpsc;
use std::thread;
use std::time::Duration;

use serde::Serialize;

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ConnectionTest {
    pub ok: bool,
    pub detail: String,
    pub app_name: Option<String>,
}

fn failure(detail: impl Into<String>) -> ConnectionTest {
    ConnectionTest {
        ok: false,
        detail: detail.into(),
        app_name: None,
    }
}

/// Try to complete a Discord IPC handshake for `client_id`.
pub fn probe(client_id: &str) -> ConnectionTest {
    if client_id.is_empty() || !client_id.chars().all(|c| c.is_ascii_digit()) {
        return failure("Enter your Application ID first.");
    }

    let mut pipe = None;
    for index in 0..10 {
        let path = format!(r"\\.\pipe\discord-ipc-{index}");
        if let Ok(file) = OpenOptions::new().read(true).write(true).open(&path) {
            pipe = Some(file);
            break;
        }
    }

    let Some(mut pipe) = pipe else {
        return failure("Discord is not running on this PC. Start Discord and try again.");
    };

    let payload = serde_json::json!({ "v": 1, "client_id": client_id });
    let body = match serde_json::to_vec(&payload) {
        Ok(bytes) => bytes,
        Err(e) => return failure(format!("Couldn't encode the handshake: {e}")),
    };

    let mut frame = Vec::with_capacity(body.len() + 8);
    frame.extend_from_slice(&0u32.to_le_bytes()); // opcode 0 = handshake
    frame.extend_from_slice(&(body.len() as u32).to_le_bytes());
    frame.extend_from_slice(&body);

    if let Err(e) = pipe.write_all(&frame) {
        return failure(format!("Discord closed the connection immediately ({e})."));
    }

    let mut reader = match pipe.try_clone() {
        Ok(clone) => clone,
        Err(e) => return failure(format!("Couldn't read Discord's answer ({e}).")),
    };

    let (tx, rx) = mpsc::channel();
    thread::spawn(move || {
        let mut header = [0u8; 8];
        let outcome = reader.read_exact(&mut header).and_then(|_| {
            let length = u32::from_le_bytes([header[4], header[5], header[6], header[7]]) as usize;
            let mut body = vec![0u8; length.min(8 * 1024)];
            reader.read_exact(&mut body).map(|_| body)
        });
        let _ = tx.send(outcome);
    });

    let body = match rx.recv_timeout(Duration::from_millis(2500)) {
        Ok(Ok(bytes)) => bytes,
        Ok(Err(e)) => return failure(format!("Discord closed the connection ({e}).")),
        Err(_) => return failure("Discord didn't answer in time. Try again in a moment."),
    };

    let value: serde_json::Value = serde_json::from_slice(&body).unwrap_or(serde_json::json!({}));

    if let Some(message) = value.get("message").and_then(serde_json::Value::as_str) {
        return failure(format!("Discord rejected the Application ID: {message}"));
    }

    let username = value
        .pointer("/data/user/username")
        .and_then(serde_json::Value::as_str)
        .map(str::to_string);

    ConnectionTest {
        ok: true,
        detail: match &username {
            Some(name) => format!("Connected to Discord. Presence will appear as the application named in the portal (signed in as {name})."),
            None => "Connected to Discord.".to_string(),
        },
        app_name: username,
    }
}
