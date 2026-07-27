# WonderBox — Server

The "brain" for WonderBox: a **Next.js** app (deployed on **Vercel**) that the
device talks to over HTTPS. It receives recorded audio, and (from Stage 4)
transcribes it, runs the **safety layer**, generates a short kid-safe answer,
speaks it, logs the text to Supabase, and serves the parent dashboard.

## What works in Stage 4

- `POST /api/ask` — the device endpoint, now running the **real pipeline**:
  **speech-to-text → safety (2 gates) → answer LLM → text-to-speech**.
  - Requires `Authorization: Bearer <DEVICE_TOKEN>`.
  - Reads the posted audio, transcribes it, and **discards it** — audio (in and
    out) is never stored. Only question/answer text is kept (logged to Supabase
    in Stage 5).
  - Returns spoken audio (OpenAI TTS, voice **nova**) + answer text in headers.
  - If `OPENAI_API_KEY` is missing it returns a friendly "not set up yet"
    message so the box still talks.
- `GET /api/ask` — health check (`aiConfigured` tells you if the key is set).

### The safety layer (the important part)

Four layers; a bad answer must beat **all** of them, and we **default to defer**:

1. **Gate 0 — deterministic rules** (`lib/safety/`): blocked/deferred topics are
   caught here *before any LLM call*. This is what the test-suite pins down.
2. **Gate 1 — LLM classifier**: anything but a clear "answer" ⇒ defer.
3. **Gate 2 — answer LLM** under a strict kid-safe system prompt (1–3 short
   sentences; emits `[DEFER]` for anything it shouldn't answer).
4. **Post-check**: the generated answer is re-scanned against the deny rules and
   clamped to ≤ 3 sentences.

Spelling questions are handled deterministically and safely (the requested word
is spelled out; blocked words are deferred).

**The allow/deny rules are editable config.** They ship as defaults in
`lib/safety/rules.ts` and, once Supabase is set up, are loaded from the
`topic_rules` table (seeded automatically on first run) so you can edit them from
the dashboard without a code change. ALLOW: how things work, animals, nature,
space, science, simple math, shapes/colors, definitions, spelling, simple
geography. DEFER: opinions, feelings, news, politics, religion, death,
violence/weapons, scary, sex/where-babies-come-from, medical, specific real
people, money — plus REFUSE for attempts to change the rules.

### Logging (Stage 5)

Every interaction is logged to Supabase — **text only**: timestamp, transcribed
question, answer, whether it was `answered`/`deferred`/`refused` and why (plus
`is_spelling`/`spell_word` and latency). **Audio is never logged or stored.**
Logging is best-effort: a logging failure never breaks a child's answer, and if
Supabase isn't configured, logging is simply skipped.

**Setup:** create a project at [supabase.com](https://supabase.com), run
[`supabase/schema.sql`](supabase/schema.sql) in the SQL editor, then add
`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, and
`SUPABASE_SERVICE_ROLE_KEY` to your env (Vercel). RLS is on with no public
policies — only the server's service role can read/write; the dashboard
(Stage 6) reads via the server after authenticating you.

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

## Parent dashboard (Stage 6)

Private, password-protected pages for you only:

- **`/login`** — sign in with your `DASHBOARD_PASSWORD`.
- **`/dashboard`** — today's summary (answered / deferred / refused + topics).
- **`/dashboard/log`** — the full question log, pick any day, search text.
- **`/dashboard/rules`** — edit the approved/blocked topic rules (add, edit
  patterns, enable/disable, delete) — changes take effect within ~30s.

**Auth:** a single password (`DASHBOARD_PASSWORD`) with a signed, HttpOnly,
Secure session cookie — no email/SMTP needed. Set `DASHBOARD_PASSWORD` (and
optionally `DASHBOARD_SESSION_SECRET`) in your env. Dashboard data is read on the
server with the Supabase service role *after* the session check, so the data is
never exposed to the browser via the public key. (Can be upgraded to
Supabase-Auth magic links locked to your email if you prefer.)

## Daily digest (Stage 7)

Once a day, a **Vercel Cron** job (`vercel.json` → `/api/cron/digest`, default
13:00 UTC) summarizes the previous day's questions into a short, friendly note
("On Sunday, the kids asked WonderBox about how far away the moon is…") and
**emails it to you via Resend**. Text only — never audio.

- The cron endpoint is protected by **`CRON_SECRET`** (Vercel sends it as a
  Bearer token automatically; we fail closed if it's unset).
- The send layer is **swappable**: `DIGEST_PROVIDER=sms` uses Twilio instead of
  email — no change to the digest code.
- Quiet days are skipped (no empty emails). You can also **"Email me today's
  digest"** from the dashboard to test it immediately.

**Setup:** add `CRON_SECRET` (`openssl rand -hex 32`), `RESEND_API_KEY` (from
[resend.com](https://resend.com)), and `DIGEST_TO_EMAIL`. Optionally set
`DIGEST_FROM_EMAIL` (defaults to Resend's shared sender until you verify a
domain) and `DIGEST_CHILD_NAME` to personalize the note.

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

The **safety-layer test suite** is the definition of done: `safety-rules.test.ts`
asserts every blocked/deferred category is never classified "answer", and
`pipeline.test.ts` proves that even a fully permissive (mocked) LLM cannot get a
substantive answer past the gates for a blocked question. These run with **no
network and no API key**.

## Deploy to Vercel

1. Push this repo to GitHub (done).
2. In Vercel, **New Project → import the repo**, and set the **Root Directory**
   to `questionbox/server`.
3. Add environment variables:
   - **`DEVICE_TOKEN`** — same value as the firmware's `secrets.h`
     (`openssl rand -hex 32`).
   - **`OPENAI_API_KEY`** — from https://platform.openai.com/api-keys
     (powers STT + safety LLM + TTS).
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
