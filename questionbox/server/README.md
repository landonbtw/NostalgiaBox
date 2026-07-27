# WonderBox — Server

The "brain" for WonderBox: a **Next.js** app (deployed on **Vercel**) that the
device talks to over HTTPS. It receives recorded audio, and (from Stage 4)
transcribes it, runs the **safety layer**, generates a short kid-safe answer,
speaks it, logs the text to Supabase, and serves the parent dashboard.

## What works in Stage 3

- `POST /api/ask` — the device endpoint.
  - Requires `Authorization: Bearer <DEVICE_TOKEN>` (so only your box can call it).
  - Reads the posted audio and **immediately discards it** — audio is never
    stored anywhere. Only text is ever kept (logging arrives in Stage 5).
  - Returns a **hardcoded friendly answer**: a short chime as the audio (to
    prove the speaker path) plus answer text in response headers.
- `GET /api/ask` — a health check you can open in a browser.
- A tiny landing page at `/`.

The real **speech-to-text → safety → LLM → text-to-speech** pipeline replaces
the hardcoded answer in Stage 4.

## The device↔server contract

**Request:** `POST /api/ask`, body = WAV audio (16 kHz mono, 16-bit),
header `Authorization: Bearer <DEVICE_TOKEN>`.

**Response:** body = WAV audio to play; text fields in headers:

| Header | Meaning |
|---|---|
| `X-Answer-Text` | the answer text (URL-encoded) |
| `X-Answer-Mode` | `answered` \| `deferred` \| `refused` |
| `X-Is-Spelling` | `1` if it's a spelling answer, else `0` |
| `X-Spell-Word` | the word to spell (URL-encoded), when spelling |

We return audio as the body + text in headers so the microcontroller doesn't
have to parse JSON or decode base64.

## Run it locally

```bash
cd questionbox/server
npm install
cp .env.example .env.local     # then set DEVICE_TOKEN to a long random value
npm run dev                    # http://localhost:3000
```

Quick check:

```bash
# health
curl http://localhost:3000/api/ask

# a fake "ask" (returns the chime WAV; needs your token)
curl -X POST http://localhost:3000/api/ask \
  -H "Authorization: Bearer YOUR_DEVICE_TOKEN" \
  --data-binary @some.wav -o answer.wav -D -
```

## Tests

```bash
npm test         # vitest — verifies /api/ask auth + contract
npm run typecheck
```

The **safety-layer test suite** (the definition of done for the safety work)
lands in Stage 4.

## Deploy to Vercel

1. Push this repo to GitHub (done).
2. In Vercel, **New Project → import the repo**, and set the **Root Directory**
   to `questionbox/server`.
3. Add the environment variable **`DEVICE_TOKEN`** (same value as the firmware's
   `secrets.h`). Generate one with `openssl rand -hex 32`.
4. Deploy. Your device's `SERVER_BASE_URL` is the resulting
   `https://<your-project>.vercel.app`.

## Environment variables

See `.env.example`. For Stage 3 you only need `DEVICE_TOKEN`. Later stages add
OpenAI, Supabase, and Resend keys — all read from the environment, never
committed.

## Security notes

- Endpoint is **authenticated** with a device token (constant-time compared) and
  **fails closed** if `DEVICE_TOKEN` is unset.
- Audio is **read and discarded** — never written to disk, DB, or logs.
- Responses are `no-store`.
- A request body size cap rejects oversized uploads.
