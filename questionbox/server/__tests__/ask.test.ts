import { beforeAll, describe, expect, it } from "vitest";
import { ANSWER_HEADERS } from "@/lib/answer";

const TOKEN = "test-device-token-1234567890";

// The route reads env at request time. No OpenAI key here, so /api/ask uses its
// friendly keyless fallback (returns a "not set up" message + chime WAV).
beforeAll(() => {
  process.env.DEVICE_TOKEN = TOKEN;
  delete process.env.OPENAI_API_KEY;
});

async function importRoute() {
  return import("@/app/api/ask/route");
}

function askRequest(body: ArrayBuffer | Uint8Array, token?: string): Request {
  const headers: Record<string, string> = { "content-type": "audio/wav" };
  if (token) headers["authorization"] = `Bearer ${token}`;
  return new Request("http://localhost/api/ask", { method: "POST", headers, body });
}

describe("POST /api/ask (Stage 3 contract)", () => {
  it("rejects requests with no token", async () => {
    const { POST } = await importRoute();
    const res = await POST(askRequest(new Uint8Array([1, 2, 3])));
    expect(res.status).toBe(401);
  });

  it("rejects requests with a wrong token", async () => {
    const { POST } = await importRoute();
    const res = await POST(askRequest(new Uint8Array([1, 2, 3]), "wrong-token"));
    expect(res.status).toBe(401);
  });

  it("returns audio + answer headers for an authorized device", async () => {
    const { POST } = await importRoute();
    const res = await POST(askRequest(new Uint8Array([1, 2, 3, 4]), TOKEN));

    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("audio/wav");
    expect(res.headers.get("cache-control")).toBe("no-store");
    // Without an OpenAI key the route defers with a friendly setup message.
    expect(res.headers.get(ANSWER_HEADERS.mode)).toBe("deferred");
    expect(res.headers.get(ANSWER_HEADERS.isSpelling)).toBe("0");

    const text = decodeURIComponent(res.headers.get(ANSWER_HEADERS.text) ?? "");
    expect(text.length).toBeGreaterThan(0);

    const buf = Buffer.from(await res.arrayBuffer());
    expect(buf.length).toBeGreaterThan(44); // WAV header + samples
    expect(buf.toString("ascii", 0, 4)).toBe("RIFF");
    expect(buf.toString("ascii", 8, 12)).toBe("WAVE");
  });

  it("returns the same placeholder answer regardless of the audio (audio is discarded, not echoed)", async () => {
    const { POST } = await importRoute();
    const a = await POST(askRequest(new Uint8Array([9, 9, 9, 9, 9, 9]), TOKEN));
    const b = await POST(askRequest(new Uint8Array([1]), TOKEN));
    const ta = decodeURIComponent(a.headers.get(ANSWER_HEADERS.text) ?? "");
    const tb = decodeURIComponent(b.headers.get(ANSWER_HEADERS.text) ?? "");
    expect(ta).toBe(tb);
  });
});
