# NostalgiaBox

**Turn a Raspberry Pi into a retro TV for your kids.**

NostalgiaBox plays folders of old children's shows off an SD card as if they were
real TV **channels**. Flip to a channel and a show is already playing (starting a
few seconds in, like you just tuned in); when an episode ends, the next one rolls
automatically on an endless shuffle. It boots straight to the TV on power-up, is
driven by a simple remote, sends audio over HDMI, and has an authentic
early-2000s vibe — a green on-screen channel banner and volume bar, and a curved
"CRT" picture. No menus, no apps, no touchscreens. Just a remote and channels.

This guide has two parts:

1. [**The hardware you'll need**](#1-hardware)
2. [**Step-by-step setup**](#2-step-by-step-setup) — the SD card, the terminal, and the programming

---

## 1. Hardware

Everything you need to build one:

| Part | Link | What it's for |
|------|------|---------------|
| **Raspberry Pi 4 Model B** | https://amzn.to/4w6HcSC | The "brain" of the box (2GB RAM or more is plenty) |
| **Flirc USB Remote Adapter** | https://amzn.to/4h7hZ5O | Plugs into the Pi and lets **any** remote control it |
| **Simple TV Remote** | https://amzn.to/4wId7bZ | The big-button remote your kids will actually use |
| **Micro-HDMI → Full HDMI cable** | https://amzn.to/4pn1TXS | Connects the Pi to the TV (the Pi 4 uses micro-HDMI) |
| **Raspberry Pi 4 case** | https://amzn.to/4fg4RJ5 | Housing so it looks tidy next to the TV |

**You'll also need (you may already have these):**

- A **micro SD card**, 32 GB or larger. Bigger = more shows. (This holds the
  operating system *and* your video files.)
- A **USB-C power supply** for the Pi 4 (the official 3A one is recommended).
- A **TV with an HDMI port**.
- A **computer** (Mac or Windows) to set up the SD card and program the remote.
- Your **show video files** (e.g. `.mp4`/`.mkv` episodes you own).

---

## 2. Step-by-step setup

Take it one part at a time. You do the first two parts on your **computer**, then
the rest by connecting to the Pi.

### Part A — Prepare the SD card

1. On your computer, install the **Raspberry Pi Imager** from
   [raspberrypi.com/software](https://www.raspberrypi.com/software/).
2. Put the micro SD card into your computer.
3. Open Raspberry Pi Imager and choose:
   - **Device:** Raspberry Pi 4
   - **Operating System:** *Raspberry Pi OS Lite (64-bit)* (under "Raspberry Pi
     OS (other)"). "Lite" has no desktop — perfect, since the box boots straight
     to the TV.
   - **Storage:** your SD card
4. Click **Next → Edit Settings** (the gear/⚙ customization step) and set:
   - **Hostname:** `nostalgiabox`
   - **Enable SSH** → "Use password authentication"
   - **Username & password** (remember these!)
   - **Wi-Fi** name and password (needed once, for the initial download)
5. Write it, then eject the card.

### Part B — Assemble and power on

1. Put the Pi in its case.
2. Plug the **Flirc** adapter into a USB port on the Pi.
3. Connect the **micro-HDMI → HDMI** cable from the Pi to your TV.
4. Insert the SD card.
5. Plug in power. Wait ~1 minute for it to boot.

### Part C — Open the terminal and connect to the Pi

You'll control the Pi from your computer over the network (SSH).

- **Mac:** open the **Terminal** app.
- **Windows:** open **PowerShell**.

Then connect (use the username you set; hostname is `nostalgiabox`):

```bash
ssh pi@nostalgiabox.local
```

- The first time, type `yes` to accept.
- Enter your password (the screen stays blank while you type — that's normal).

You're "inside" the Pi when the prompt changes to something like
`pi@nostalgiabox:~ $`.

> If `nostalgiabox.local` doesn't resolve, find the Pi's IP address from your
> router and use `ssh pi@THAT.IP.ADDRESS` instead.

### Part D — Install NostalgiaBox

Install git (if needed), download the project, and run the installer:

```bash
sudo apt update
sudo apt install -y git
git clone https://github.com/landonbtw/NostalgiaBox.git
cd NostalgiaBox
./scripts/install.sh
```

The installer sets up everything: the media player (mpv), video tools (ffmpeg),
the retro font, and all dependencies. It takes a few minutes. Say `y` if it asks
to continue. It's done when you see **"==> Done!"**.

### Part E — Load your shows

Put each show in its **own folder**, one folder per channel. For example, on a
USB drive or copied onto the Pi:

```
/media/nostalgiabox/
├── Dragon Tales/
│   ├── S01E01.mp4
│   └── S01E02.mp4
├── Arthur/
└── The Magic School Bus/
```

The easiest way to get files onto the Pi is a **USB drive**: create the show
folders on it from your computer, copy your episodes in, plug it into the Pi, and
copy them over (ask for the exact copy commands if you need them). Any common
video format works (`.mp4`, `.mkv`, `.avi`, `.m4v`, …), and season sub-folders
are fine.

### Part F — Set up your channels

Open the config file and point the channels at your show folders:

```bash
nano config.yaml
```

A minimal example (see [`config.example.yaml`](config.example.yaml) for every
option):

```yaml
channels:
  - number: 2
    name: "Dragon Tales"
    path: /media/nostalgiabox/dragon-tales
  - number: 3
    name: "Arthur"
    path: /media/nostalgiabox/arthur

tune_in: random          # a random episode starts when you flip to a channel
start_offset: [6, 10]    # begin each show 6-10 seconds in (skips the intro)
```

Save in nano with **Ctrl+O**, Enter, then exit with **Ctrl+X**. Check it:

```bash
nostalgiabox --check
```

This lists your channels and how many episodes it found in each. (You can also
leave out specific seasons/specials per channel — see `exclude_seasons` and
`exclude` in the example config.)

### Part G — Program the remote (Flirc)

The **Flirc** adapter learns your Simple TV Remote and turns its buttons into
keys NostalgiaBox understands. Do this **on your computer**:

1. Unplug the Flirc from the Pi and plug it into your computer.
2. Install the **Flirc** app from [flirc.tv/downloads](https://flirc.tv/pages/downloads).
3. In the app, choose the **Full Keyboard** controller.
4. Click a key on the on-screen keyboard, then press the button on your Simple TV
   Remote you want to use for it. Map these:

   | Click this on-screen key | Press this remote button | Does |
   |--------------------------|--------------------------|------|
   | **Up arrow (↑)**   | Channel-Up button   | Channel up |
   | **Down arrow (↓)** | Channel-Down button | Channel down |
   | **Right arrow (→)**| Volume-Up button    | Volume up |
   | **Left arrow (←)** | Volume-Down button  | Volume down |
   | **m**              | Mute button         | Mute |
   | **p**              | Power button        | Standby (blank the screen) |

5. Unplug the Flirc from your computer and plug it back into the Pi.

That's it — no config changes needed; these keys work out of the box. (Advanced:
you can remap any key via `key_overrides` in the config — see the example.)

### Part H — Get audio out the TV (HDMI)

The Pi sometimes sends audio to its headphone jack by default. To force it out
HDMI, find your HDMI audio device:

```bash
nostalgiabox --list-audio
```

Look for the **HDMI** entry (e.g. `alsa/hdmi:CARD=vc4hdmi0,DEV=0`). The Pi 4 has
two HDMI ports: the one nearest the USB-C power is `vc4hdmi0`, the other is
`vc4hdmi1`. Put the matching name in `config.yaml`:

```yaml
audio_device: "alsa/hdmi:CARD=vc4hdmi0,DEV=0"   # use vc4hdmi1 if on the 2nd port
```

### Part I — Make it boot to TV on power-up

Test it first:

```bash
nostalgiabox
```

Your shows should appear on the TV and respond to the remote. Press `q` on a
keyboard (or `Ctrl+C` in SSH) to stop. Happy with it? Turn on auto-start:

```bash
./scripts/install.sh --service
```

Now the box boots straight to TV whenever it gets power — no login, no menus.

### Part J — Make it kid-proof (recommended)

Kids will unplug it. Two things keep the SD card from getting corrupted:

- **Turn it off with the remote:** turn the volume all the way down to 0, then
  press volume-down **once more** — the Pi shuts down cleanly ("GOODBYE"), and
  it's safe to unplug once the green light stops blinking.
- **Read-only mode (belt-and-suspenders):** run `sudo raspi-config` →
  **Performance Options → Overlay File System → Enable** (and write-protect the
  boot partition). This makes the SD read-only, so pulling the plug can *never*
  corrupt it. (To update later, disable the overlay, update, then re-enable it.)

**Done!** Plug it in and enjoy your nostalgia box.

---

## Using it day to day

| Do this | On the remote |
|---------|---------------|
| Change channels | Channel up / down |
| Adjust volume | Volume up / down |
| Mute | Mute |
| Standby (blank screen) | Power |
| **Turn off** (safe to unplug) | Volume-down again when already at 0 |

Turn it on by plugging in power; it boots back to a channel automatically.

---

## Updating later

If a newer version is released:

```bash
cd ~/NostalgiaBox
git pull
sudo systemctl restart nostalgiabox
```

(If you enabled the read-only overlay in Part J, turn it off first via
`raspi-config`, update, then turn it back on.)

---

## Configuration reference (highlights)

All settings live in `config.yaml`:

```yaml
tune_in: random          # random | resume | broadcast
start_channel: 2         # channel to power on to
start_offset: [6, 10]    # start each episode a random 6-10s in (or a fixed number)
transition: none         # channel-change effect: none | glitch | static
bridge_seconds: 0.8      # keep the current show playing while the next loads
channel_bug_seconds: 4   # how long the channel banner lingers
initial_volume: 70       # 0-100
audio_device: "..."      # force HDMI audio (see Part H)

ui:                      # the green on-screen display
  color: "#4DFF5A"
  glow: true
crt:                     # the CRT picture effect (curve, rounding, scanlines)
  enabled: true
  curvature: 0.12
```

Leaving out episodes per channel:

```yaml
  - number: 3
    name: "Arthur"
    path: /media/nostalgiabox/arthur
    exclude_seasons: ["6-25"]   # only air seasons 1-5
    exclude: ["*special*"]      # skip the specials
```

Validate any changes with `nostalgiabox --check`.

---

## Troubleshooting

- **`--check` shows 0 episodes for a channel** → the `path` is wrong, or the
  files use an extension not in `video_extensions`.
- **No video on the TV** → make sure the HDMI cable is in the right Pi port and
  the TV is on that input. Check logs with `journalctl -u nostalgiabox -f`.
- **No sound** → see Part H; try switching `vc4hdmi0` ↔ `vc4hdmi1`, or the
  `alsa/plughw:CARD=...` variant.
- **Remote does nothing** → confirm the Flirc is plugged into the Pi and was
  programmed (Part G). Restart the box after plugging it in.
- **It won't boot / config errors after a power cut** → the SD got corrupted from
  an unclean shutdown. Enable the read-only overlay (Part J) to prevent it.

---

## For the curious (how it works)

The project is plain Python. The "brains" (channel scanning, the shuffle, the
state machine) have no hardware dependencies and are fully unit-tested; the
hardware-facing parts (the mpv video player and the remote input) are isolated
behind small interfaces. You can even drive the whole thing on a laptop with a
mock player:

```bash
pip install -e ".[dev]"
pytest
python -m nostalgiabox --dry-run --config config.yaml   # keyboard-controlled, no video
```

```
nostalgiabox/
├── config.py      YAML -> validated config
├── playlist.py    the shuffle bag (each episode once, then reshuffle)
├── channel.py     folder scanning, tune-in modes, channel navigation
├── player.py      mpv player (+ a mock for tests)
├── overlay.py     the green on-screen display
├── crt.py         the CRT shader
├── input/         remote input (Flirc/keyboard, HDMI-CEC, keymap)
├── static_gen.py  ffmpeg-generated static/glitch/colour-bar clips
└── app.py         the TV state machine
```

## License

MIT. Enjoy your nostalgia box!
