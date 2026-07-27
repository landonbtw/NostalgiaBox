import { checkDeviceAuth } from "@/lib/config";
import { buildAnswerResponse, type WonderAnswer } from "@/lib/answer";
import { generateChimeWav } from "@/lib/wav";
import { hasOpenAI } from "@/lib/ai/openai";
import { transcribe } from "@/lib/ai/stt";
import { synthesize } from "@/lib/ai/tts";
import { makeRealDeps } from "@/lib/ai/deps";
import { answerQuestion } from "@/lib/pipeline";
import { getRules } from "@/lib/safety/rules-store";
import { logInteraction } from "@/lib/log";
import { isSupabaseConfigured } from "@/lib/supabase";
import { setupMessage, troubleMessage } from "@/lib/safety/messages";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_AUDIO_BYTES = 5 * 1024 * 1024;

// Speak `text`, falling back to the chime if TTS is unavailable, so the device
// always gets audio to play.
async function ttsOrChime(text: string): Promise<Buffer> {
  try {
    return await synthesize(text);
  } catch (e) {
    console.error("[ask] TTS failed, using chime:", e);
    return generateChimeWav();
  }
}

/**
 * POST /api/ask — the device endpoint.
 * Pipeline: authenticate -> speech-to-text -> SAFETY (2 gates) -> answer ->
 * text-to-speech. Audio in and audio out are transient and never stored; only
 * question/answer TEXT is kept (logging lands in Stage 5).
 */
export async function POST(request: Request): Promise<Response> {
  const auth = checkDeviceAuth(request);
  if (!auth.ok) return Response.json({ error: auth.reason }, { status: auth.status });

  const audio = await request.arrayBuffer();
  if (audio.byteLength > MAX_AUDIO_BYTES) {
    return Response.json({ error: "audio_too_large" }, { status: 413 });
  }

  // No AI keys yet: return a friendly "not set up" message so the box still talks.
  if (!hasOpenAI()) {
    const text = setupMessage();
    return buildAnswerResponse({ text, mode: "deferred", isSpelling: false, wav: generateChimeWav() });
  }

  const startedAt = Date.now();

  // 1) Speech-to-text (audio discarded right after).
  let question = "";
  try {
    question = await transcribe(audio);
  } catch (e) {
    console.error("[ask] STT failed:", e);
    const text = troubleMessage();
    return buildAnswerResponse({ text, mode: "deferred", isSpelling: false, wav: await ttsOrChime(text) });
  }

  // 2) Safety pipeline (2 gates + deterministic checks) -> answer text.
  const rules = await getRules(); // editable rules from Supabase (or defaults)
  const result = await answerQuestion(question, makeRealDeps(rules), rules);

  // 3) Text-only logging to Supabase (audio is NEVER logged). Best-effort.
  await logInteraction({
    question,
    answer: result.text,
    mode: result.mode,
    category: result.category,
    reason: result.reason,
    isSpelling: result.isSpelling,
    spellWord: result.spellWord,
    latencyMs: Date.now() - startedAt,
  });
  console.log(`[ask] q="${question}" -> mode=${result.mode} cat=${result.category ?? "-"}`);

  // 4) Text-to-speech.
  const wav = await ttsOrChime(result.text);

  const answer: WonderAnswer = {
    text: result.text,
    mode: result.mode,
    isSpelling: result.isSpelling,
    spellWord: result.spellWord,
    wav,
  };
  return buildAnswerResponse(answer);
}

export function GET(): Response {
  return Response.json({
    name: "WonderBox",
    endpoint: "/api/ask",
    stage: 5,
    ok: true,
    aiConfigured: hasOpenAI(),
    loggingConfigured: isSupabaseConfigured(),
  });
}
