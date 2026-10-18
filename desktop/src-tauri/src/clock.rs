//! Local wall-clock time for log lines.
//!
//! The Python build writes `[%(asctime)s]` with the default `datefmt`
//! (`%Y-%m-%d %H:%M:%S`), and both builds append to **the same `autorpc.log`**, so the shell
//! writes the identical shape — a mixed file would be a confusing thing to hand a user.
//! Calling `GetLocalTime` directly avoids pulling in a date/time crate for five numbers.

#[repr(C)]
#[derive(Default)]
#[allow(dead_code)]
struct SystemTime {
    year: u16,
    month: u16,
    day_of_week: u16,
    day: u16,
    hour: u16,
    minute: u16,
    second: u16,
    milliseconds: u16,
}

#[link(name = "kernel32")]
extern "system" {
    fn GetLocalTime(time: *mut SystemTime);
}

fn now() -> SystemTime {
    let mut raw = SystemTime::default();
    // SAFETY: GetLocalTime only writes into the struct we hand it.
    unsafe { GetLocalTime(&mut raw) };
    raw
}

/// `2026-10-18 14:07:33` — what goes into `autorpc.log`, matching `logging.Formatter`.
pub fn timestamp_string() -> String {
    let clock = now();
    format!(
        "{:04}-{:02}-{:02} {:02}:{:02}:{:02}",
        clock.year, clock.month, clock.day, clock.hour, clock.minute, clock.second
    )
}
