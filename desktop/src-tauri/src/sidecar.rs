//! The Python engine sidecar (`T-022`).
//!
//! `main.py --engine-stdio` runs the same detection/presence pipeline the tray build runs,
//! headless, and talks to us in JSON lines: our commands on its stdin, its events on its
//! stdout. The wire format is documented at the top of `engine_stdio.py`.
//!
//! Why a child process at all: reading the foreground window, extracting icons, uploading them
//! and holding the Discord socket is Windows-only Python that already works and is in daily use.
//! Re-implementing it in Rust is `RUST_MIGRATION_RESEARCH.md`'s problem, not this seam's.
//!
//! The engine is a *peer*, not a servant. It owns the Discord status (we ask, we never decide
//! it), it writes `autorpc.log` itself (we only mirror its lines into the pane, so nothing is
//! logged twice), and it is asked to quit politely — killing the process leaves a presence stuck
//! on the user's profile until the socket drops.
//!
//! Discovery order, for both a dev checkout and a future release layout:
//!
//! 1. `AUTORPC_ENGINE_PYTHON` — an interpreter the user pointed us at, with
//!    `AUTORPC_ENGINE_SCRIPT` for the script;
//! 2. a frozen `DiscordAutoRPC-engine.exe` next to this shell;
//! 3. `python.exe` from PATH, with `main.py` found above the dev binary.

use std::io::{BufRead, BufReader, Write};
use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStderr, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Mutex, MutexGuard};
use std::thread;
use std::time::{Duration, Instant};

use serde::Deserialize;
use serde_json::{json, Value};
use tauri::{AppHandle, Emitter};

use crate::service;
use crate::state::{
    AppInfo, DISCORD_CONNECTED, DISCORD_CONNECTING, DISCORD_NOT_RUNNING, DISCORD_OFFLINE,
    ENGINE_OFFLINE, ENGINE_WAITING,
};

/// `python.exe` is a console binary; without this every launch would flash a black window over
/// a tray app. Piped stdio still works, which is all the protocol needs.
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// How long a polite `quit` gets before the axe.
const SHUTDOWN_GRACE: Duration = Duration::from_millis(1500);

static CHILD: Mutex<Option<Child>> = Mutex::new(None);
static STDIN: Mutex<Option<ChildStdin>> = Mutex::new(None);

/// True between a `ready` line and the process exiting: "the engine is answering".
static READY: AtomicBool = AtomicBool::new(false);
/// True while no engine process exists (also the initial state).
static EXITED: AtomicBool = AtomicBool::new(true);
/// Set by `shutdown`, so a normal quit is not reported as a crash.
static QUITTING: AtomicBool = AtomicBool::new(false);
/// The engine's built-in tagline table, cached for `get_built_ins`.
static BUILT_INS: Mutex<Option<Vec<(String, String)>>> = Mutex::new(None);

fn lock<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
}

/* ------------------------------------------------------------------ protocol --- */

/// One line from the engine.
///
/// Unknown `type`s simply fail to parse and get logged, so a newer engine cannot take an older
/// shell down.
#[derive(Deserialize)]
#[serde(tag = "type", rename_all = "lowercase")]
enum Event {
    Ready {
        version: String,
        #[serde(default)]
        pid: u32,
    },
    Builtins {
        #[serde(default)]
        taglines: std::collections::HashMap<String, String>,
    },
    Discord {
        status: String,
    },
    App {
        app: Option<WireApp>,
    },
    Log {
        level: String,
        logger: String,
        message: String,
    },
    Update {
        tag: String,
        #[serde(default)]
        url: Option<String>,
    },
    Toast {
        #[serde(default = "info_kind")]
        kind: String,
        message: String,
    },
    Fatal {
        message: String,
    },
}

fn info_kind() -> String {
    "info".to_string()
}

/// The engine's `AppInfo`, which is the same shape the frontend already reads.
///
/// Parsed into a local struct first so a missing optional field can never fail the whole line.
#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct WireApp {
    exe: String,
    path: String,
    #[serde(default)]
    pid: u32,
    display_name: String,
    #[serde(default)]
    tagline: Option<String>,
    #[serde(default)]
    icon_url: Option<String>,
    #[serde(default)]
    started_at_ms: Option<u64>,
    #[serde(default)]
    ignored: bool,
}

impl From<WireApp> for AppInfo {
    fn from(wire: WireApp) -> Self {
        Self {
            exe: wire.exe,
            path: wire.path,
            pid: wire.pid,
            display_name: wire.display_name,
            tagline: wire.tagline,
            icon_url: wire.icon_url,
            started_at_ms: wire.started_at_ms,
            ignored: wire.ignored,
        }
    }
}

fn parse(line: &str) -> Result<Event, serde_json::Error> {
    serde_json::from_str(line)
}

/* -------------------------------------------------------------------- startup --- */

/// How to start the engine, once we know it can be started at all.
struct Plan {
    program: PathBuf,
    args: Vec<String>,
    cwd: Option<PathBuf>,
}

fn env_path(name: &str) -> Option<PathBuf> {
    let value = std::env::var(name).ok()?;
    let trimmed = value.trim();
    if trimmed.is_empty() {
        return None;
    }
    Some(PathBuf::from(trimmed))
}

fn plan() -> Option<Plan> {
    if let Some(python) = env_path("AUTORPC_ENGINE_PYTHON") {
        return script_plan(python);
    }

    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let bundled = dir.join("DiscordAutoRPC-engine.exe");
            if bundled.is_file() {
                return Some(Plan {
                    program: bundled,
                    args: vec!["--engine-stdio".to_string()],
                    cwd: None,
                });
            }
        }
    }

    script_plan(PathBuf::from("python.exe"))
}

fn script_plan(python: PathBuf) -> Option<Plan> {
    let script = env_path("AUTORPC_ENGINE_SCRIPT").or_else(find_script)?;
    let cwd = script
        .parent()
        .map(Path::to_path_buf)
        .filter(|dir| dir.is_dir());

    Some(Plan {
        program: python,
        args: vec![
            script.display().to_string(),
            "--engine-stdio".to_string(),
        ],
        cwd,
    })
}

/// Find the checkout `main.py` lives in.
///
/// In development this binary sits at `desktop/src-tauri/target/debug/…`, so the repository root
/// is a few directories up — and a directory holding both `main.py` and `detector.py` is
/// unmistakably it.
fn find_script() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let mut dir = exe.parent()?.to_path_buf();

    for _ in 0..6 {
        let candidate = dir.join("main.py");
        if candidate.is_file() && dir.join("detector.py").is_file() {
            return Some(candidate);
        }
        dir = dir.parent()?.to_path_buf();
    }

    None
}

/// Spawn the engine. `false` means nothing was started, and the caller decides what to say
/// about it — the shell falls back to the mock, an explicit `AUTORPC_ENGINE=python` reports
/// the problem instead.
pub fn start(app: AppHandle) -> bool {
    let Some(plan) = plan() else {
        service::ui_log(
            &app,
            "WARNING",
            "autorpc.engine",
            "No Python engine found — set AUTORPC_ENGINE_PYTHON to an interpreter, or run this \
             build from the repository. Detection is unavailable until then.",
        );
        return false;
    };

    let mut command = Command::new(&plan.program);
    command
        .args(&plan.args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .creation_flags(CREATE_NO_WINDOW);
    if let Some(cwd) = &plan.cwd {
        command.current_dir(cwd);
    }

    let mut child = match command.spawn() {
        Ok(child) => child,
        Err(error) => {
            service::ui_log(
                &app,
                "ERROR",
                "autorpc.engine",
                &format!("Could not start {}: {error}", plan.program.display()),
            );
            return false;
        }
    };

    service::ui_log(
        &app,
        "INFO",
        "autorpc.engine",
        &format!(
            "Starting the engine: {} {}",
            plan.program.display(),
            plan.args.join(" ")
        ),
    );

    EXITED.store(false, Ordering::SeqCst);
    READY.store(false, Ordering::SeqCst);
    QUITTING.store(false, Ordering::SeqCst);

    if let Some(stdin) = child.stdin.take() {
        *lock(&STDIN) = Some(stdin);
    }
    if let Some(stdout) = child.stdout.take() {
        let handle = app.clone();
        thread::spawn(move || read_events(handle, stdout));
    }
    if let Some(stderr) = child.stderr.take() {
        let handle = app.clone();
        thread::spawn(move || read_errors(handle, stderr));
    }

    *lock(&CHILD) = Some(child);

    service::set_engine(&app, ENGINE_WAITING);
    true
}

/* --------------------------------------------------------------------- pipes --- */

fn read_events(app: AppHandle, stdout: ChildStdout) {
    for line in BufReader::new(stdout).lines() {
        let Ok(line) = line else { break };
        let line = line.trim();
        if line.is_empty() {
            continue;
        }

        match parse(line) {
            Ok(event) => apply(&app, event),
            Err(_) => service::emit_log(
                &app,
                "WARNING",
                "autorpc.engine",
                &format!("Unrecognised line from the engine: {}", clip(line, 240)),
            ),
        }
    }

    // The pipe closed, so the process is gone: either our own `quit` or something worse.
    let code = reap();
    let ready = READY.swap(false, Ordering::SeqCst);

    if QUITTING.load(Ordering::SeqCst) {
        service::emit_log(&app, "INFO", "autorpc.engine", "Engine stopped");
        return;
    }

    service::set_discord(&app, DISCORD_OFFLINE);
    service::set_engine(&app, ENGINE_OFFLINE);
    service::clear_current_app(&app);

    let detail = match code {
        Some(code) => format!("exited with code {code}"),
        None => "stopped".to_string(),
    };

    if ready {
        service::ui_log(
            &app,
            "ERROR",
            "autorpc.engine",
            &format!("The engine {detail} — detection is offline. See the log for details."),
        );
    } else {
        service::ui_log(
            &app,
            "ERROR",
            "autorpc.engine",
            &format!(
                "The engine {detail} before it was ready — most likely it could not import its \
                 dependencies. Run `python main.py --engine-stdio` in a terminal to see why."
            ),
        );
    }

    let _ = app.emit(
        "toast",
        json!({
            "kind": "error",
            "message": "The detection engine stopped — see the Logs pane.",
        }),
    );
}

/// Anything the engine prints to stderr is a traceback or a warning; both belong in the log.
fn read_errors(app: AppHandle, stderr: ChildStderr) {
    for line in BufReader::new(stderr).lines() {
        let Ok(line) = line else { break };
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        service::emit_log(&app, "ERROR", "autorpc.engine", &clip(line, 400));
    }
}

/// Convert one engine event into shell state.
fn apply(app: &AppHandle, event: Event) {
    match event {
        Event::Ready { version, pid } => {
            READY.store(true, Ordering::SeqCst);
            service::set_engine(app, ENGINE_WAITING);
            service::ui_log(
                app,
                "INFO",
                "autorpc.engine",
                &format!("Python engine ready (v{version}, pid {pid})"),
            );
        }

        Event::Builtins { taglines } => {
            *lock(&BUILT_INS) = Some(taglines.into_iter().collect());
        }

        Event::Discord { status } => {
            // Only the vocabulary the frontend knows crosses into state; anything else is a
            // newer engine talking past an older shell.
            if matches!(
                status.as_str(),
                DISCORD_CONNECTED | DISCORD_CONNECTING | DISCORD_OFFLINE | DISCORD_NOT_RUNNING
            ) {
                service::set_discord(app, &status);
            }
        }

        Event::App { app: info } => match info {
            Some(wire) => service::set_current_app(app, wire.into()),
            None => service::clear_current_app(app),
        },

        // The engine already wrote this line to autorpc.log; emitting it is what puts it in the
        // Logs pane, and appending it again would duplicate it on disk.
        Event::Log {
            level,
            logger,
            message,
        } => service::emit_log(app, &level, &logger, &message),

        Event::Update { tag, url } => {
            service::ui_log(
                app,
                "INFO",
                "autorpc.updater",
                &format!("Update available: v{tag}"),
            );
            let target = url.filter(|value| !value.is_empty());
            service::mutate(app, |state| state.update_tag = Some(tag.clone()));
            service::emit_log(
                app,
                "DEBUG",
                "autorpc.updater",
                &format!("Release page: {}", target.unwrap_or_default()),
            );
        }

        Event::Toast { kind, message } => {
            let _ = app.emit("toast", json!({ "kind": kind, "message": message }));
        }

        Event::Fatal { message } => service::ui_log(
            app,
            "ERROR",
            "autorpc.engine",
            &format!("Engine reported a fatal error: {message}"),
        ),
    }
}

/// Reap the child so Windows does not keep its PID reserved, and report its exit code.
fn reap() -> Option<i32> {
    let mut guard = lock(&CHILD);
    let mut child = guard.take()?;
    EXITED.store(true, Ordering::SeqCst);
    *lock(&STDIN) = None;
    child.wait().ok().and_then(|status| status.code())
}

/* -------------------------------------------------------------- shell → engine --- */

/// One protocol line to the engine, flushed immediately: it is blocked reading, not polling.
fn send(payload: Value) {
    let mut guard = lock(&STDIN);
    let Some(stdin) = guard.as_mut() else {
        return; // no engine running (the mock, or a failed start)
    };

    // A failed write is not handled here on purpose: the reader thread sees the same EOF and
    // reports the lost engine once, with the exit code, instead of every caller doing it.
    let _ = writeln!(stdin, "{payload}");
    let _ = stdin.flush();
}

pub fn set_paused(paused: bool) {
    send(json!({ "cmd": "set_paused", "paused": paused }));
}

/// Nudge the engine after the shell wrote config.json, so a rename or a new gradient of
/// settings lands on the next poll instead of on the engine's next mtime check.
pub fn reload_config() {
    send(json!({ "cmd": "reload_config" }));
}

/// Ask the engine to clear the presence and exit, and kill it only if it does not.
///
/// Called from the exit path: Discord should be left clean, and a presence nobody can reach is
/// worse than a slow quit.
pub fn shutdown(app: &AppHandle) {
    QUITTING.store(true, Ordering::SeqCst);
    send(json!({ "cmd": "quit" }));

    let deadline = Instant::now() + SHUTDOWN_GRACE;
    while !EXITED.load(Ordering::SeqCst) && Instant::now() < deadline {
        thread::sleep(Duration::from_millis(50));
    }

    if EXITED.load(Ordering::SeqCst) {
        return;
    }

    service::ui_log(
        app,
        "WARNING",
        "autorpc.engine",
        "The engine did not answer the quit request in time — killing it (the presence on \
         Discord will expire with the socket).",
    );

    if let Some(child) = lock(&CHILD).as_mut() {
        let _ = child.kill();
        let _ = child.wait();
    }
    EXITED.store(true, Ordering::SeqCst);
    *lock(&STDIN) = None;
}

/// The engine's built-in tagline table, empty until it answers.
pub fn built_ins() -> Vec<(String, String)> {
    lock(&BUILT_INS).clone().unwrap_or_default()
}

/// Keep the Logs pane readable: a multi-kilobyte line is clipped, not dropped.
fn clip(text: &str, limit: usize) -> String {
    if text.chars().count() <= limit {
        return text.to_string();
    }

    let clipped: String = text.chars().take(limit).collect();
    format!("{clipped}…")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_ready_line_is_an_event() {
        match parse(r#"{"type":"ready","version":"0.1.0-beta","pid":4242}"#) {
            Ok(Event::Ready { version, pid }) => {
                assert_eq!(version, "0.1.0-beta");
                assert_eq!(pid, 4242);
            }
            other => panic!("unexpected: ok={}", other.is_ok()),
        }
    }

    #[test]
    fn an_app_line_may_omit_the_optional_fields() {
        let line = r#"{"type":"app","app":{"exe":"code.exe","path":"C:\\Code.exe","displayName":"Visual Studio Code"}}"#;
        match parse(line) {
            Ok(Event::App { app: Some(wire) }) => {
                assert_eq!(wire.exe, "code.exe");
                assert_eq!(wire.display_name, "Visual Studio Code");
                assert_eq!(wire.pid, 0);
                assert!(wire.tagline.is_none());
            }
            other => panic!("unexpected: ok={}", other.is_ok()),
        }
    }

    #[test]
    fn an_app_line_can_clear_the_app() {
        assert!(matches!(
            parse(r#"{"type":"app","app":null}"#),
            Ok(Event::App { app: None })
        ));
    }

    #[test]
    fn an_unknown_type_is_rejected_rather_than_guessed() {
        assert!(parse(r#"{"type":"something-new","value":1}"#).is_err());
    }

    #[test]
    fn a_toast_without_a_kind_defaults_to_info() {
        match parse(r#"{"type":"toast","message":"hello"}"#) {
            Ok(Event::Toast { kind, message }) => {
                assert_eq!(kind, "info");
                assert_eq!(message, "hello");
            }
            other => panic!("unexpected: ok={}", other.is_ok()),
        }
    }
}
