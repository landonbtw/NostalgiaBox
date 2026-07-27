import { beforeEach, describe, expect, it } from "vitest";
import { buildDigest } from "@/lib/digest";
import { isDigestConfigured, sendMessage } from "@/lib/email";
import type { Interaction } from "@/lib/dashboard-data";

function mk(partial: Partial<Interaction>): Interaction {
  return {
    id: Math.random().toString(36),
    created_at: "2026-07-27T14:00:00.000Z",
    question: null,
    answer: null,
    mode: "answered",
    category: null,
    reason: null,
    is_spelling: false,
    spell_word: null,
    latency_ms: null,
    ...partial,
  };
}

describe("buildDigest", () => {
  it("summarizes a day with example questions", () => {
    const rows = [
      mk({ question: "How far away is the moon?", mode: "answered" }),
      mk({ question: "Why do volcanoes erupt?", mode: "answered" }),
      mk({ question: "Where do babies come from?", mode: "deferred" }),
    ];
    const d = buildDigest("2026-07-27", rows, "Gus");
    expect(d.total).toBe(3);
    expect(d.subject).toContain("Gus");
    expect(d.text).toContain("How far away is the moon?");
    expect(d.text).toContain("Why do volcanoes erupt?");
    // Deferred/answered counts appear.
    expect(d.text).toMatch(/answered 2/);
    expect(d.html).toContain("WonderBox");
  });

  it("dedupes repeated questions", () => {
    const rows = [
      mk({ question: "what is a triangle", mode: "answered" }),
      mk({ question: "What is a triangle", mode: "answered" }),
    ];
    const d = buildDigest("2026-07-27", rows);
    const occurrences = d.text.split("triangle").length - 1;
    expect(occurrences).toBe(1);
  });

  it("handles a quiet day", () => {
    const d = buildDigest("2026-07-27", []);
    expect(d.total).toBe(0);
    expect(d.subject.toLowerCase()).toContain("quiet");
  });
});

describe("send layer", () => {
  beforeEach(() => {
    delete process.env.RESEND_API_KEY;
    delete process.env.DIGEST_TO_EMAIL;
    delete process.env.DIGEST_PROVIDER;
  });

  it("is not configured and skips (never throws) without keys", async () => {
    expect(isDigestConfigured()).toBe(false);
    const r = await sendMessage({ subject: "hi", text: "hi", html: "<p>hi</p>" });
    expect(r.sent).toBe(false);
    expect(r.skipped).toBe("not_configured");
  });
});
