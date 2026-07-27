# WonderBox

**A friendly "question box" for little kids.** Your child taps a smiling face on
a small round screen, asks a question out loud, and hears a short, safe, spoken
answer back. Grown-up questions (scary, sad, or too-big topics) get a warm
"let's ask Mom or Dad" instead — never a real answer. You get a private
dashboard of everything asked and a friendly email summary once a day.

This guide is written for someone who has **never done this before.** Take it one
step at a time. You can't break anything.

---

## How it works (the 30-second version)

WonderBox has **two parts**:

1. **The device** — the little Waveshare screen gadget in your home. It shows the
   face, listens when tapped, and plays the answer. It is *not* smart on its own.
2. **The server** — a small website (that only you use) running on **Vercel**. It
   does the thinking: turns speech into text, checks it's safe, writes a kid
   answer, turns it back into speech, and remembers what was asked.

The device talks to the server over the internet. The "brain" (and all the
safety rules) lives on the server, never on the device.

```
[child taps face] → device records → server: speech→text → SAFETY CHECK →
   kid answer → text→speech → device plays it aloud
```

---

## Part 0 — The stuff you need first

**Hardware**
- The **Waveshare ESP32-S3-Touch-LCD-1.85C-BOX** (the screen gadget).
- A **USB-C cable that can carry data** (not a charge-only cable — most cables
  that came with a phone/tablet work).
- A computer (Mac or Windows) and your **2.4GHz Wi-Fi** name + password.
  (The device can't use 5GHz Wi-Fi. If your Wi-Fi has one name for both, it's
  usually fine.)

**Free accounts you'll create (all have free tiers):**
- [GitHub](https://github.com) — stores the code (you may already have this).
- [Vercel](https://vercel.com) — runs the server.
- [OpenAI](https://platform.openai.com) — the AI (this one costs a little per
  use; a few dollars covers a *lot* of kid questions).
- [Supabase](https://supabase.com) — the database (remembers questions + rules).
- [Resend](https://resend.com) — sends you the daily email.

Don't worry about what these are — the steps below tell you exactly what to click.

**Your secrets (I generated these for you — keep them somewhere safe):**

| Name | Value to paste later |
|------|----------------------|
| `DEVICE_TOKEN` | *(see the message from your assistant)* |
| `DASHBOARD_SESSION_SECRET` | *(see the message)* |
| `CRON_SECRET` | *(see the message)* |

You'll also **make up a `DASHBOARD_PASSWORD`** yourself (any password you'll
remember — it's how *you* log into the dashboard).

---

## Part 1 — Put the server online (Vercel)

1. Make sure this project is on **GitHub** (if you're reading this in a repo,
   it already is).
2. Go to [vercel.com](https://vercel.com) and **sign up with GitHub**.
3. Click **Add New… → Project**, and **Import** this repository.
4. **IMPORTANT:** in the setup screen, find **Root Directory** and set it to
   **`questionbox/server`** (click "Edit" and pick that folder). This tells
   Vercel the server lives in that sub-folder.
5. Don't deploy yet — first we need the keys (Parts 2–5). If you already
   deployed, that's fine; we'll add the keys and redeploy.

---

## Part 2 — The database (Supabase)

1. Go to [supabase.com](https://supabase.com), sign up, and **create a new
   project** (pick any name and a database password — Supabase keeps that one;
   you won't need it again).
2. Wait ~2 minutes for it to finish setting up.
3. On the left, open the **SQL Editor**, click **New query**, then open the file
   `questionbox/server/supabase/schema.sql` from this project, **copy all of
   it**, paste it in, and click **Run**. (This creates the tables.)
4. On the left, go to **Project Settings → API**. Keep this tab open — you'll
   copy three values in Part 6:
   - **Project URL**
   - **anon public** key
   - **service_role** key (this one is secret — treat it like a password)

---

## Part 3 — The AI key (OpenAI)

1. Go to [platform.openai.com](https://platform.openai.com) and sign in.
2. Add a little money under **Billing** (even $5 goes a long way).
3. Go to **API keys → Create new secret key**, and **copy it** (starts with
   `sk-…`). You can only see it once — save it for Part 6.

---

## Part 4 — The daily email (Resend)

1. Go to [resend.com](https://resend.com), sign up.
2. Go to **API Keys → Create API Key**, and **copy it** (starts with `re_…`).
3. That's enough to start — emails will come from a shared Resend address until
   you (optionally) verify your own domain later.

---

## Part 5 — Your dashboard password

Just **decide on a password** you'll remember. This is `DASHBOARD_PASSWORD` —
it's how you log into your private dashboard. Write it down.

---

## Part 6 — Put all the keys into Vercel

In Vercel, open your project → **Settings → Environment Variables**. Add each of
these (Name on the left, Value on the right), then click **Save**:

| Name | Value |
|------|-------|
| `DEVICE_TOKEN` | the one from your assistant's message |
| `OPENAI_API_KEY` | your `sk-…` key (Part 3) |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase **Project URL** (Part 2) |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase **anon public** key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase **service_role** key |
| `DASHBOARD_PASSWORD` | the password you chose (Part 5) |
| `DASHBOARD_SESSION_SECRET` | the one from your assistant's message |
| `CRON_SECRET` | the one from your assistant's message |
| `RESEND_API_KEY` | your `re_…` key (Part 4) |
| `DIGEST_TO_EMAIL` | the email address you want the daily note sent to |
| `DIGEST_CHILD_NAME` | *(optional)* your child's name, e.g. `Gus` |

Now click **Deployments → … → Redeploy** (or push any change) so the new keys
take effect. When it says **Ready**, your server is live at something like
`https://wonderbox-yourname.vercel.app`. **Write that address down** — the
device needs it.

**Quick check:** open `https://YOUR-ADDRESS/api/ask` in a browser. You should
see a little bit of text with `"ok":true`. 🎉

---

## Part 7 — Put the code on the device

This is the part that feels scary but really isn't. We use a free tool called
**PlatformIO** inside the **VS Code** editor.

1. **Install VS Code**: [code.visualstudio.com](https://code.visualstudio.com) →
   download → install → open it.
2. **Install PlatformIO**: in VS Code, click the **Extensions** icon on the left
   (four little squares), search **"PlatformIO IDE"**, click **Install**. Wait a
   couple minutes for it to finish (it says so at the bottom).
3. **Open the firmware folder**: File → **Open Folder…** → choose
   `questionbox/firmware` from this project.
4. **Create your secrets file**:
   - In the file list, open the `include` folder.
   - Right-click `secrets.h.example` → **Copy**, then **Paste** — rename the copy
     to exactly **`secrets.h`**.
   - Open `secrets.h` and fill in the four values:
     ```c
     #define WIFI_SSID       "your-wifi-name"
     #define WIFI_PASSWORD   "your-wifi-password"
     #define SERVER_BASE_URL "https://wonderbox-yourname.vercel.app"   // from Part 6
     #define DEVICE_TOKEN    "the DEVICE_TOKEN from your assistant"      // must match Vercel
     ```
     Save the file (Ctrl/Cmd + S). *(This file stays on your computer and is
     never uploaded anywhere.)*
5. **Plug the device** into your computer with the USB-C **data** cable.
6. **Upload**: at the very bottom of VS Code there's a blue bar with small icons.
   Click the **right-arrow (→)** icon ("PlatformIO: Upload"). The first time it
   downloads some tools — that can take several minutes. It's done when you see
   **SUCCESS** in the terminal.
   - *If it can't find the device:* hold the **BOOT** button on the board, tap
     **RESET**, let go of **BOOT**, then click Upload again.
7. The screen should light up with the **smiling face**. 🥳

---

## Part 8 — Try it

1. Tap the **microphone button** on the screen — the face goes to "listening"
   (a ring appears).
2. Ask something simple and kid-friendly: **"How far away is the moon?"**
3. Stop talking (or tap again). The face "thinks," then **speaks the answer**.
4. Now try a grown-up one: **"Where do babies come from?"** — it should warmly
   say to ask Mom or Dad, and **not** answer it. That's the safety layer working.
5. Try **"How do you spell dog?"** — it shows the letters big on screen and says
   them slowly.

---

## Part 9 — Your dashboard

Go to `https://YOUR-ADDRESS/login`, enter your `DASHBOARD_PASSWORD`, and you can:
- See **today's summary** and every question, searchable by day.
- **Edit the topic rules** (what's allowed vs. sent to a grown-up).
- Click **"Email me today's digest"** to test the daily email right away.

The daily email arrives automatically once a day.

---

## If something goes wrong

- **The face never appears / upload failed** → try a different USB-C cable (must
  carry data), and the BOOT/RESET trick in Part 7, step 6.
- **It says a "not set up" message when tapped** → the server is missing the
  `OPENAI_API_KEY`, or the device's `SERVER_BASE_URL` / `DEVICE_TOKEN` don't
  match what's in Vercel. Double-check Parts 6 and 7.
- **Nothing happens when tapped / can't reach server** → the device isn't on
  Wi-Fi (check `WIFI_SSID`/`WIFI_PASSWORD`; remember 2.4GHz), or the URL is
  wrong. Open the PlatformIO **Serial Monitor** (the plug icon in the blue bar)
  to read what it's doing.
- **No sound** → check the speaker is connected and the box isn't muted; the
  little volume buttons are on the board.
- **Dashboard won't log in** → `DASHBOARD_PASSWORD` isn't set in Vercel, or you
  didn't redeploy after adding it.

---

## Good to know (safety & privacy)

- **The mic only listens when tapped** — never on its own.
- **Audio is never saved** — not on the device, not on the server. Only the
  *text* of questions and answers is kept, so you can review it.
- **Two safety checks** decide every answer, and it **defaults to "ask a
  grown-up"** whenever it's unsure. You control the topic rules from the
  dashboard.
- All your keys live in Vercel/your computer — never in the shared code.

Made with care. Enjoy your WonderBox!
