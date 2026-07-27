import { toFile } from "openai";
import { getOpenAI } from "./openai";

/**
 * Speech-to-text. Transcribes the child's recorded WAV to text.
 * Audio is used transiently here and never persisted.
 */
export async function transcribe(audio: ArrayBuffer | Buffer): Promise<string> {
  const openai = getOpenAI();
  const model = process.env.STT_MODEL || "gpt-4o-mini-transcribe";
  const buf = Buffer.isBuffer(audio) ? audio : Buffer.from(audio);
  const file = await toFile(buf, "question.wav", { type: "audio/wav" });

  const res = await openai.audio.transcriptions.create({
    file,
    model,
    response_format: "text",
  });

  // With response_format "text" the SDK returns a string; be defensive anyway.
  const text = typeof res === "string" ? res : ((res as { text?: string }).text ?? "");
  return text.trim();
}
