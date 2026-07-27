import { beforeEach, describe, expect, it } from "vitest";
import { logInteraction } from "@/lib/log";

describe("interaction logging", () => {
  beforeEach(() => {
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    delete process.env.SUPABASE_SERVICE_ROLE_KEY;
  });

  it("is a no-op (and never throws) when Supabase is not configured", async () => {
    await expect(
      logInteraction({
        question: "how far is the moon",
        answer: "The moon is very far away!",
        mode: "answered",
        isSpelling: false,
      }),
    ).resolves.toBeUndefined();
  });
});
