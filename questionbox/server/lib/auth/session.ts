import { createHmac, createHash, timingSafeEqual } from "node:crypto";

/**
 * Minimal, dependency-free session for the single-parent dashboard.
 *
 * Login is a single password (DASHBOARD_PASSWORD). On success we set an
 * HttpOnly, Secure, SameSite=Lax cookie holding an HMAC-signed token with an
 * expiry. No user database, no third-party auth — private and simple.
 */

export const SESSION_COOKIE = "wb_session";
export const SESSION_TTL_SECONDS = 7 * 24 * 60 * 60; // 7 days

export function isDashboardConfigured(): boolean {
  return !!process.env.DASHBOARD_PASSWORD;
}

function getSecret(): string {
  // Prefer an explicit secret; otherwise derive one from the password so
  // sessions are still signed. Changing the password invalidates old sessions.
  const explicit = process.env.DASHBOARD_SESSION_SECRET;
  if (explicit && explicit.length > 0) return explicit;
  const pw = process.env.DASHBOARD_PASSWORD ?? "";
  return createHash("sha256").update(`wb-session:${pw}`).digest("hex");
}

function b64url(buf: Buffer): string {
  return buf.toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function sign(payload: string): string {
  return b64url(createHmac("sha256", getSecret()).update(payload).digest());
}

/** True if `password` matches DASHBOARD_PASSWORD (constant-time). */
export function checkPassword(password: string): boolean {
  const expected = process.env.DASHBOARD_PASSWORD;
  if (!expected) return false;
  const a = Buffer.from(password);
  const b = Buffer.from(expected);
  if (a.length !== b.length) {
    timingSafeEqual(a, a);
    return false;
  }
  return timingSafeEqual(a, b);
}

export function createSessionToken(now = Date.now()): string {
  const exp = Math.floor(now / 1000) + SESSION_TTL_SECONDS;
  const payload = b64url(Buffer.from(JSON.stringify({ exp })));
  return `${payload}.${sign(payload)}`;
}

export function verifySessionToken(token: string | undefined, now = Date.now()): boolean {
  if (!token) return false;
  const dot = token.lastIndexOf(".");
  if (dot <= 0) return false;
  const payload = token.slice(0, dot);
  const sig = token.slice(dot + 1);

  const expected = sign(payload);
  const a = Buffer.from(sig);
  const b = Buffer.from(expected);
  if (a.length !== b.length || !timingSafeEqual(a, b)) return false;

  try {
    const json = JSON.parse(Buffer.from(payload.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString());
    return typeof json.exp === "number" && json.exp > Math.floor(now / 1000);
  } catch {
    return false;
  }
}
