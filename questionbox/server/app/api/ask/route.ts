import { checkDeviceAuth } from "@/lib/config";
import { buildAnswerResponse, type WonderAnswer } from "@/lib/answer";
import { generateChimeWav } from "@/lib/wav";

// This route touches audio and secrets: never cache, always run on the server.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Hard cap on the uploaded audio (a few seconds of 16kHz mono is well under this).
const MAX_AUDIO_BYTES = 5 * 1024 * 1024;

/**
 * POST /api/ask
 * The device posts recorded audio here and gets back spoken audio + text.
 *
 * STAGE 3: we authenticate the device, read (and immediately discard) the
 * audio, and return a hardcoded friendly answer plus a placeholder chime. The
 * real STT -> safety -> LLM -> TTS pipeline lands in Stage 4.
 */
export async function POST(request: Request): Promise<Response> {
  const auth = checkDeviceAuth(request);
  if (!auth.ok) {
    return Response.json({ error: auth.reason }, { status: auth.status });
  }

  // Read the raw audio body. IMPORTANT: audio is used transiently and NEVER
  // stored — not on disk, not in a database, not in logs. It simply goes out of
  // scope at the end of this request. Only question/answer TEXT is ever kept.
  const audio = await request.arrayBuffer();
  if (audio.byteLength > MAX_AUDIO_BYTES) {
    return Response.json({ error: "audio_too_large" }, { status: 413 });
  }
  const audioBytes = audio.byteLength; // fine to note the size; the bytes are discarded

  const answer: WonderAnswer = {
    text:
      "Hi! I'm WonderBox. When my brain is connected, I'll answer your questions!",
    mode: "answered",
    isSpelling: false,
    wav: generateChimeWav(),
  };

  console.log(`[ask] received ${audioBytes} bytes of audio -> returning stage-3 test answer`);
  return buildAnswerResponse(answer);
}

/** Simple health check so you can confirm the server is up from a browser. */
export function GET(): Response {
  return Response.json({ name: "WonderBox", endpoint: "/api/ask", stage: 3, ok: true });
}
