/**
 * The shared answer contract between the WonderBox device and server.
 *
 * The device wants two things back: audio to play, and text to (maybe) show.
 * Rather than make an MCU parse JSON+base64, we return the audio as the binary
 * body and the small text fields as response headers.
 */

export type AnswerMode = "answered" | "deferred" | "refused";

export interface WonderAnswer {
  /** The answer text (1-3 short sentences), or the warm defer/refuse message. */
  text: string;
  /** Whether we answered, deferred to a parent, or refused. */
  mode: AnswerMode;
  /** True when this is a spelling answer to show big, letter by letter. */
  isSpelling: boolean;
  /** The word to spell (only meaningful when isSpelling). */
  spellWord?: string;
  /** WAV audio (16-bit PCM) of the spoken answer. */
  wav: Buffer;
}

/** Header names the device reads for the text side of the answer. */
export const ANSWER_HEADERS = {
  text: "X-Answer-Text",
  mode: "X-Answer-Mode",
  isSpelling: "X-Is-Spelling",
  spellWord: "X-Spell-Word",
} as const;

/**
 * Build the HTTP response: WAV bytes as the body, answer text in headers.
 * `Cache-Control: no-store` because answers are per-child and never cached.
 */
export function buildAnswerResponse(a: WonderAnswer): Response {
  const headers = new Headers();
  headers.set("Content-Type", "audio/wav");
  headers.set("Content-Length", String(a.wav.length));
  headers.set("Cache-Control", "no-store");
  headers.set(ANSWER_HEADERS.text, encodeURIComponent(a.text));
  headers.set(ANSWER_HEADERS.mode, a.mode);
  headers.set(ANSWER_HEADERS.isSpelling, a.isSpelling ? "1" : "0");
  headers.set(ANSWER_HEADERS.spellWord, encodeURIComponent(a.spellWord ?? ""));
  // Let non-device clients (e.g. a browser fetch, tests) read the custom headers.
  headers.set(
    "Access-Control-Expose-Headers",
    Object.values(ANSWER_HEADERS).join(", "),
  );

  // Copy into a fresh Uint8Array so the Web Response gets a clean ArrayBuffer.
  const body = new Uint8Array(a.wav);
  return new Response(body, { status: 200, headers });
}
