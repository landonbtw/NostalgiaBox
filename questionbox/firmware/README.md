# WonderBox — Firmware

Runs on the **Waveshare ESP32-S3-Touch-LCD-1.85C-BOX** (1.85" round 360×360
LCD, capacitive touch, dual mic + speaker, Wi-Fi). This is the part that shows
the friendly face, listens when tapped, and (later) talks to the server.

Built on top of Waveshare's official demo drivers, so the display and touch are
proven hardware bring-up — we don't drive the panel from scratch. Uses
**Arduino + PlatformIO**.

## What works in Stage 3

The real **device↔server loop** (with a hardcoded test answer from the server):

1. Tap the mic (**IDLE → LISTENING**) — starts recording from the I2S mic.
2. Tap again, or just stop talking (**auto-stop on silence**) — the device
   builds a WAV and **POSTs it to the server** (`/api/ask`), showing **THINKING**.
3. The server returns audio + text; the device plays the audio out the speaker
   while showing **SPEAKING** (or **SPELLING**, letter by letter, for spelling
   answers), then returns to **IDLE**.

The animated **face** has all five looks (IDLE / LISTENING / THINKING /
SPEAKING / SPELLING), designed for the round screen. Push-to-talk only — the
mic never listens on its own. **Audio is recorded, sent, and discarded — never
stored** on the device.

> **Stage 4 update:** the server now runs the real (multi-second) STT → safety →
> LLM → TTS pipeline, so the device sends the request on a **background task**.
> The **THINKING** dots keep bouncing during the wait, and the **SPEAKING**
> mouth animates during playback. No device setup changes vs. Stage 3 — just set
> `OPENAI_API_KEY` on the server.

### Before it can talk: set up `secrets.h`

Copy `include/secrets.h.example` to `include/secrets.h` and fill in your
2.4GHz Wi-Fi, your server URL, and a device token (the same token you set in the
server's environment). `secrets.h` is gitignored and never committed. Without
it the firmware still builds, but it won't connect.

> **Security note:** by default the device uses TLS *without* certificate
> validation (`WB_TLS_INSECURE=1`) so it works out of the box — the connection
> is encrypted but not authenticated. To harden, set `WB_TLS_INSECURE 0` and
> paste your server's root CA into `src/net/wonder_client.cpp`.

## Hardware pins (from the Waveshare wiki, for reference)

| Function | Detail |
|---|---|
| Display | ST77916, QSPI, 360×360 |
| Touch | CST816, I2C addr `0x15`, INT `GPIO4` |
| I2C bus | SCL `GPIO10`, SDA `GPIO11` |
| GPIO expander | TCA9554 @ `0x20` (LCD reset, touch reset) |
| Backlight | `GPIO5` (PWM) |
| Speaker (PCM5101 DAC) | DIN `GPIO47`, BCK `GPIO48`, LRCK `GPIO38` |
| Microphone (I2S MEMS) | SCK `GPIO15`, WS `GPIO2`, SD `GPIO39` |

## Flashing it (beginner steps)

1. **Install VS Code**, then the **PlatformIO IDE** extension
   (Extensions → search "PlatformIO IDE" → Install).
2. **Open this folder** (`questionbox/firmware`) in VS Code:
   File → Open Folder. PlatformIO will notice `platformio.ini`.
3. Plug the WonderBox into your computer with a **USB-C cable** (use a real data
   cable, not charge-only).
4. Click the **PlatformIO “Upload”** button (the → arrow in the blue bottom bar),
   or run in the PlatformIO terminal:
   ```bash
   pio run -t upload
   ```
   The first build downloads the ESP32 toolchain and LVGL — that can take a few
   minutes. Later builds are fast.
5. Open the **Serial Monitor** (plug icon, or `pio device monitor`) at
   **115200 baud** to see log messages.

> If upload fails to find the board, hold **BOOT**, tap **RESET**, release
> **BOOT**, then upload again.

## Project layout

```
firmware/
├── platformio.ini        board + libraries (LVGL 8.3.10) pinned
├── include/
│   ├── lv_conf.h         LVGL config (from the demo; big fonts enabled)
│   └── secrets.h.example copy to secrets.h for Wi-Fi + server (Stage 3)
└── src/
    ├── main.cpp          setup/loop + the Stage 2 demo state flow
    ├── board/            drivers ported from Waveshare's demo
    │   ├── I2C_Driver.*  Display_ST77916.*  esp_lcd_st77916.*
    │   ├── Touch_CST816.*  TCA9554PWR.*  LVGL_Driver.*
    ├── ui/
    │   ├── face.*        the animated face + all five states
    │   └── mic_button.*  the tap-to-talk button
    ├── audio/
    │   ├── mic.*         I2S mic recording -> WAV (silence auto-stop)
    │   └── speaker.*     stream WAV answer -> PCM5101 speaker
    ├── net/
    │   ├── wifi_conn.*   Wi-Fi connect
    │   └── wonder_client.*  HTTPS POST to /api/ask + header parsing
    └── app/
        └── wonderbox_state.h   the shared state enum
```

## Credits

Board drivers (`src/board/*`) and `lv_conf.h` are adapted from Waveshare's
official `ESP32-S3-Touch-LCD-1.85C` demo. LVGL is © the LVGL project (MIT).
