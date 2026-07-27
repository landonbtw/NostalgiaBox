import { timingSafeEqual } from "node:crypto";

/**
 * Central place for reading environment configuration. Secrets ONLY ever come
 * from environment variables (Vercel env / .env.local) — never hard-coded.
 */

export function getDeviceToken(): string | undefined {
  const t = process.env.DEVICE_TOKEN;
  return t && t.length > 0 ? t : undefined;
}

/** Constant-time comparison so token checks don't leak length/prefix via timing. */
export function safeEqual(a: string, b: string): boolean {
  const ab = Buffer.from(a);
  const bb = Buffer.from(b);
  if (ab.length !== bb.length) {
    // Still do a comparison to keep timing roughly constant.
    timingSafeEqual(ab, ab);
    return false;
  }
  return timingSafeEqual(ab, bb);
}

/**
 * Validates the device's `Authorization: Bearer <token>` header against
 * DEVICE_TOKEN. Returns a reason string when the request should be rejected,
 * or null when it is authorized.
 */
export function checkDeviceAuth(request: Request): { ok: true } | { ok: false; status: number; reason: string } {
  const expected = getDeviceToken();
  if (!expected) {
    // Fail closed: if the server is misconfigured, do not accept requests.
    return { ok: false, status: 500, reason: "server_missing_device_token" };
  }
  const header = request.headers.get("authorization") ?? "";
  const match = /^Bearer\s+(.+)$/i.exec(header);
  if (!match) return { ok: false, status: 401, reason: "missing_bearer_token" };
  if (!safeEqual(match[1], expected)) return { ok: false, status: 401, reason: "invalid_token" };
  return { ok: true };
}
