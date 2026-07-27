import { beforeEach, describe, expect, it } from "vitest";
import {
  checkPassword,
  createSessionToken,
  verifySessionToken,
  SESSION_TTL_SECONDS,
} from "@/lib/auth/session";

beforeEach(() => {
  process.env.DASHBOARD_PASSWORD = "correct horse battery staple";
  process.env.DASHBOARD_SESSION_SECRET = "unit-test-secret";
});

describe("dashboard password", () => {
  it("accepts the right password and rejects wrong ones", () => {
    expect(checkPassword("correct horse battery staple")).toBe(true);
    expect(checkPassword("wrong")).toBe(false);
    expect(checkPassword("")).toBe(false);
  });
});

describe("session tokens", () => {
  it("verifies a freshly minted token", () => {
    const t = createSessionToken();
    expect(verifySessionToken(t)).toBe(true);
  });

  it("rejects a tampered token", () => {
    const t = createSessionToken();
    expect(verifySessionToken(t + "x")).toBe(false);
    expect(verifySessionToken("garbage")).toBe(false);
    expect(verifySessionToken(undefined)).toBe(false);
  });

  it("rejects an expired token", () => {
    const past = Date.now() - (SESSION_TTL_SECONDS + 60) * 1000;
    const t = createSessionToken(past);
    expect(verifySessionToken(t)).toBe(false);
  });

  it("rejects a token signed with a different secret", () => {
    const t = createSessionToken();
    process.env.DASHBOARD_SESSION_SECRET = "a-different-secret";
    expect(verifySessionToken(t)).toBe(false);
  });
});
