import { getOpenAI } from "./openai";
import { encodeWav } from "../wav";

/**
 * Text-to-speech. Returns a 24 kHz mono 16-bit WAV (what the device expects).
 *
 * Provider is swappable via TTS_PROVIDER ("openai" | "elevenlabs") — a one-line
 * env change. Voice defaults to OpenAI's warm "nova".
 */
export async function synthesize(text: string): Promise<Buffer> {
  const provider = (process.env.TTS_PROVIDER || "openai").toLowerCase();
  if (provider === "elevenlabs") return synthesizeElevenLabs(text);
  return synthesizeOpenAI(text);
}

async function synthesizeOpenAI(text: string): Promise<Buffer> {
  const openai = getOpenAI();
  const model = process.env.TTS_MODEL || "gpt-4o-mini-tts";
  const voice = process.env.TTS_VOICE || "nova";

  const res = await openai.audio.speech.create({
    model,
    voice,
    input: text,
    response_format: "pcm", // raw 24kHz mono 16-bit LE
    instructions:
      "Speak in a warm, gentle, friendly female voice, slowly and clearly, as if reading to a young child.",
  });

  const pcm = Buffer.from(await res.arrayBuffer());
  return encodeWav(pcm, { sampleRate: 24000, numChannels: 1 });
}

async function synthesizeElevenLabs(text: string): Promise<Buffer> {
  const key = process.env.ELEVENLABS_API_KEY;
  if (!key) throw new Error("ELEVENLABS_API_KEY is not set");
  const voiceId = process.env.ELEVENLABS_VOICE_ID || "EXAVITQu4vr4xnSDxMaL"; // warm default
  const modelId = process.env.ELEVENLABS_MODEL_ID || "eleven_flash_v2_5";

  const res = await fetch(
    `https://api.elevenlabs.io/v1/text-to-speech/${voiceId}?output_format=pcm_24000`,
    {
      method: "POST",
      headers: { "xi-api-key": key, "content-type": "application/json" },
      body: JSON.stringify({ text, model_id: modelId }),
    },
  );
  if (!res.ok) throw new Error(`ElevenLabs TTS failed: ${res.status}`);

  const pcm = Buffer.from(await res.arrayBuffer());
  return encodeWav(pcm, { sampleRate: 24000, numChannels: 1 });
}
