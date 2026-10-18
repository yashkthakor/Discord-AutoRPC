/**
 * Validation and normalization.
 *
 * These are behavior contracts, not presentation details:
 * - exe keys MUST stay lowercase + `.exe` (O-4 / T-4 / I-3). Changing this breaks config keys.
 * - App ID rules mirror `config.validate_app_id`, and the copy now matches the check
 *   (17–21) — see D-048.
 */

/** Lowercase and force a `.exe` suffix. The single normalization used everywhere. */
export function normalizeExeKey(raw: string): string {
  const trimmed = raw.trim().toLowerCase().replace(/^"+|"+$/g, "");
  if (!trimmed) return "";
  return trimmed.endsWith(".exe") ? trimmed : `${trimmed}.exe`;
}

/** A pasted App ID is often a full URL or has whitespace; recover the digits. */
export function normalizeAppId(raw: string): string {
  const trimmed = raw.trim();
  const fromUrl = /applications\/(\d+)/.exec(trimmed);
  if (fromUrl) return fromUrl[1] ?? "";
  return trimmed.replace(/\D/g, "");
}

export interface Validation {
  ok: boolean;
  error?: string;
}

const APP_ID_MIN = 17;
const APP_ID_MAX = 21;

/** Shared by onboarding (OB-7) and Settings → General (G-1). */
export function validateAppId(raw: string): Validation {
  const value = raw.trim();

  if (!value) return { ok: false, error: "Application ID cannot be empty." };
  if (value === "YOUR_DISCORD_APPLICATION_ID_HERE" || value === "0") {
    return { ok: false, error: "Please enter your actual Discord Application ID." };
  }
  if (!/^\d+$/.test(value)) {
    return { ok: false, error: "Application ID must contain numbers only." };
  }
  if (value.length < APP_ID_MIN || value.length > APP_ID_MAX) {
    return {
      ok: false,
      error: `Discord Application IDs are ${APP_ID_MIN}–${APP_ID_MAX} digits long (got ${value.length} digits).`,
    };
  }
  return { ok: true };
}

/** O-8: Discord rejects asset URLs over 255 characters, and must be https. */
export function validateIconUrl(raw: string): Validation {
  const value = raw.trim();
  if (!value) return { ok: true };
  if (!/^https:\/\//i.test(value)) return { ok: false, error: "Must be an https:// URL." };
  if (value.length > 255) return { ok: false, error: `Too long (${value.length}/255 characters).` };
  return { ok: true };
}

export const TAGLINE_SOFT_LIMIT = 128;

/** Discord truncates long taglines; warn, never block (T-8). */
export function taglineLengthState(raw: string): "ok" | "close" | "over" {
  const length = raw.trim().length;
  if (length > TAGLINE_SOFT_LIMIT) return "over";
  if (length > TAGLINE_SOFT_LIMIT - 16) return "close";
  return "ok";
}
