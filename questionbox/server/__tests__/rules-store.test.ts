import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { getRules, _clearRulesCache } from "@/lib/safety/rules-store";
import { DEFAULT_RULES } from "@/lib/safety/rules";

describe("rules store", () => {
  beforeEach(() => {
    _clearRulesCache();
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    delete process.env.SUPABASE_SERVICE_ROLE_KEY;
  });
  afterEach(() => {
    _clearRulesCache();
  });

  it("falls back to DEFAULT_RULES when Supabase is not configured", async () => {
    const rules = await getRules();
    expect(rules).toBe(DEFAULT_RULES);
    expect(rules.deny.length).toBeGreaterThan(0);
  });
});
