# AGENTS.md

## Cursor Cloud specific instructions

This repo is a **monorepo with two unrelated products** (they share no runtime code and are set up/tested independently):

- **NostalgiaBox** (repo root, Python 3) — a retro-TV media player for a Raspberry Pi. See `README.md`.
- **WonderBox** (`questionbox/`) — a kids' "question box": a **Next.js server** (`questionbox/server`) plus **ESP32 firmware** (`questionbox/firmware`). See `questionbox/README.md` and `questionbox/server/README.md`.

The update script installs deps for both testable parts: `pip install -e ".[dev]"` (NostalgiaBox) and `npm install` in `questionbox/server` (WonderBox server).

### NostalgiaBox (Python, repo root)

- **Test:** `python3 -m pytest`. The `pytest`/`nostalgiabox` console scripts install to `~/.local/bin`, which is **not on PATH** — invoke via `python3 -m ...` (or `~/.local/bin/nostalgiabox`).
- **Lint:** none configured.
- **Run (dev, no hardware):** needs a `config.yaml` (gitignored; copy from `config.example.yaml`). Then `python3 -m nostalgiabox --dry-run --config config.yaml`, which swaps in a `MockPlayer` and reads keys from stdin (arrows=channel/volume, digits+Enter=direct channel, `m` mute, `i` info, `l` last, `q` quit). Validate a config with `--check`.
- The `[pi]` extras (`python-mpv`, `evdev`) and system `mpv`/`ffmpeg`/`cec-utils` are **only needed to run against real hardware** on a Pi — not for tests or `--dry-run`. `mpv` is not installed in this VM.
- **Gotcha — buffered output:** `MockPlayer` prints via `print()`, which is block-buffered when piped (e.g. `| tee`). Use `python3 -u` / `PYTHONUNBUFFERED=1` to see `[player] ...` lines live.
- **Gotcha — scripted arrow keys:** the stdin dev backend grabs an escape sequence within a ~20 ms window; feeding arrow keys programmatically (e.g. `tmux send-keys Up`) often arrives as a bare ESC, which maps to **QUIT**. When scripting a dry-run, change channels with `<digit>` then `Enter` instead of arrows. Interactive human use of arrows is fine.

### WonderBox server (`questionbox/server`, Next.js 16 / React 19)

- **Run (dev):** `npm run dev` → http://localhost:3000 (see `questionbox/server/README.md`).
- **Test:** `npm test` (Vitest — runs with no network and no API keys). **Static check:** `npm run typecheck` (`tsc --noEmit`).
- **Gotcha — `npm run lint` is broken:** it runs `next lint`, but Next.js 16 removed the `lint` subcommand, so it fails with `Invalid project directory provided, no such directory: .../lint`. This is upstream, not an env problem — use `npm run typecheck` for static checking.
- **Env:** copy `.env.example` → `.env.local` (gitignored). Everything is optional and degrades gracefully:
  - `DEVICE_TOKEN` — required for `POST /api/ask` auth (generate with `openssl rand -hex 32`).
  - `OPENAI_API_KEY` — without it `/api/ask` still returns a valid WAV with a friendly "not set up yet" message (STT/LLM/TTS disabled).
  - `DASHBOARD_PASSWORD` — enables the parent dashboard login at `/login` → `/dashboard`.
  - Supabase / Resend / Twilio keys — enable logging, dashboard data, and the daily digest; unset = those features are skipped, no crash.
- **`/api/ask` contract:** `POST` a WAV body with header `Authorization: Bearer <DEVICE_TOKEN>`; response body is a WAV plus `X-Answer-Text` / `X-Answer-Mode` / `X-Is-Spelling` / `X-Spell-Word` headers. `GET /api/ask` is a health check.

### WonderBox firmware (`questionbox/firmware`)

- C/C++ for ESP32 via PlatformIO; requires the PlatformIO toolchain and physical hardware. **Not buildable/testable in this cloud VM** — treat as out of scope here.
