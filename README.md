# NostalgiaBox

Turn a Raspberry Pi into a **retro television** for your kids.

NostalgiaBox plays folders of old children's shows off an SD card as if they
were TV **channels**. Flip to a channel and a random episode is already playing;
when it ends, the next one rolls automatically on an endless shuffle. Changing
channels flashes a channel banner and a brief digital **glitch**, there's an
on-screen **volume bar**, and empty channels show **colour bars / "no signal"** —
all the little touches that make it feel like the TV you grew up with, driven
entirely from a remote control.

> Built for a "nostalgia box": a Raspberry Pi 4 wired to a TV, seasons of old
> shows on a micro SD card, and a remote in little hands.

---

## Features

- **Fixed channels, one per show.** Each channel is just a folder of episodes.
- **Endless randomized shuffle.** A *shuffle bag* plays every episode once before
  repeating any, and never plays the same one twice in a row — no schedule to
  keep, no menus to navigate.
- **Tune-in that feels like TV.** Choose how channels behave when you switch to
  them: start a fresh random episode (`random`, the default), pick up where you
  left off (`resume`), or run like a real always-on station you tune into
  mid-episode (`broadcast`).
- **Authentic on-screen display.** Channel banner ("CH 03 — DRAGON TALES"),
  segmented volume bar, mute indicator, and a glitch/static burst on channel change.
- **Colour-bars "no signal"** screen for empty channels and standby.
- **Works with the remote you have.** USB/IR remotes and keyboards (via Linux
  `evdev`) *and* the TV's own remote over **HDMI-CEC**, at the same time.
- **Boots straight into TV mode** via a systemd service — no desktop required.
- **Drop-in media loading.** Point it at a folder and every sub-folder becomes a
  channel automatically.

---

## Hardware

- Raspberry Pi 4 Model B (what this is tuned for; a Pi 3 works too).
- micro SD card with Raspberry Pi OS **and** your shows (or a second USB/SD for
  media).
- HDMI cable to the TV.
- A remote, any of:
  - a **USB or IR "media remote"** (shows up as a keyboard), or
  - the **TV's own remote** if your TV supports HDMI-CEC (Anynet+, SimpLink,
    BRAVIA Sync, etc.), or
  - a plain **USB keyboard** (great for setup).

---

## Quick start

On the Raspberry Pi:

```bash
git clone <this-repo> nostalgiabox
cd nostalgiabox

# Installs mpv/libmpv, ffmpeg, cec-utils and the Python package, then
# generates the static/colour-bar clips.
./scripts/install.sh

# Tell it where your shows are (see "Loading media" below), then check it:
nano config.yaml
nostalgiabox --check

# Try it out:
nostalgiabox

# Happy with it? Make it boot straight into TV mode:
./scripts/install.sh --service
```

---

## Loading media

Put each show in its own folder. Any common video format works
(`.mp4`, `.mkv`, `.avi`, `.m4v`, `.mov`, …). Season sub-folders are fine — they
are scanned recursively.

```
/media/nostalgiabox/
├── Dragon Tales/
│   ├── S01E01.mp4
│   └── S01E02.mp4
├── Arthur/
│   └── ...
└── Rugrats/
    └── ...
```

Then either **let it auto-discover** the channels:

```yaml
# config.yaml
media_root: /media/nostalgiabox
```

…which turns each folder into a channel (numbered from 2, alphabetical), or
**list them yourself** for full control over numbers and names:

```yaml
channels:
  - number: 2
    name: "Dragon Tales"
    path: /media/nostalgiabox/dragon-tales
  - number: 3
    name: "Arthur"
    path: /media/nostalgiabox/arthur
```

See [`config.example.yaml`](config.example.yaml) for every option. Validate any
time with `nostalgiabox --check`, which lists your channels and episode counts.

### Leaving out episodes

Per channel you can drop content you don't want to air:

```yaml
  - number: 3
    name: "Arthur"
    path: /media/nostalgiabox/arthur
    exclude_seasons: ["6-25"]   # or a list like [6, 7, 8]
    exclude: ["*special*"]      # case-insensitive glob(s) on the path/filename
```

`exclude_seasons` detects the season number from names like `S06E01`, `Season 6`,
or `6x01`. `exclude` drops anything whose path matches a glob. Run
`nostalgiabox --check` to confirm the resulting episode count.

---

## Remote control

Actions are mapped generously so almost any remote works. The main buttons:

| Do this                | Remote / TV remote (CEC)        | USB keyboard          |
|------------------------|---------------------------------|-----------------------|
| Channel up / down      | CH+ / CH− , or ▲ / ▼            | ↑ / ↓ , PgUp / PgDn   |
| Volume up / down       | VOL+ / VOL− , or ► / ◄          | → / ← , `+` / `-`     |
| Mute                   | Mute                            | `m`                   |
| Go to channel number   | digits `0`–`9`, then **OK**     | digits, then Enter    |
| Info banner            | Info / Guide                    | `i`                   |
| Last channel           | Prev / Back / Exit              | `l` (or Back key)     |
| Power / standby        | Power                           | `p`                   |
| Quit the app           | —                               | `q` / Esc             |

Direct entry: type a channel number and it tunes after a short pause (or press
OK/Enter immediately). If the channel doesn't exist you get a brief "NO CHANNEL"
message.

### Remapping buttons (odd remotes)

Any remote that shows up as a keyboard can be remapped in `config.yaml`. Find a
button's key name with `sudo evtest`, then map it to an action:

```yaml
input:
  key_overrides:
    KEY_PAGEUP: channel_up      # e.g. a presenter remote's back button
    KEY_PAGEDOWN: channel_down
    KEY_F5: volume_up
    KEY_DOT: volume_down
```

Actions: `channel_up`, `channel_down`, `volume_up`, `volume_down`, `mute`,
`enter`, `info`, `last_channel`, `power`, `quit`, `digit_0`..`digit_9`, or `none`
to unbind. Overrides win over the built-in defaults; `nostalgiabox --check`
validates them.

---

## Configuration reference (highlights)

```yaml
tune_in: random          # random | resume | broadcast
start_channel: 2         # channel to power on to
start_offset: 5          # start each episode this many seconds in
transition: glitch       # channel-change effect: glitch | static | none
transition_duration: 0.4
channel_bug_seconds: 4   # how long the channel banner lingers
initial_volume: 70       # 0–100
volume_step: 5
scan_recursive: true

input:
  keyboard: true         # USB/IR remotes & keyboards (evdev)
  cec: true              # TV remote over HDMI-CEC
  stdin: false           # developer keyboard (terminal)
```

Everything is optional except the channels themselves. Unavailable input
backends are skipped automatically, so the same config works on the Pi and on a
laptop.

### Retro look: the green OSD and the CRT effect

The on-screen readouts (channel banner, volume bar, messages) are drawn in a
phosphor-green retro terminal font (**VT323**, bundled, installed by the
setup script). And because these shows were made for 4:3 tube TVs, an optional
GLSL **CRT effect** bends the picture like a real CRT — a gentle bulge, rounded
corners, a vignette, and faint scanlines:

```yaml
ui:
  font: "VT323"          # any installed font family name
  color: "#4DFF5A"       # phosphor green
  glow: true             # soft CRT bloom around the text

crt:
  enabled: true          # set false if the Pi struggles or you prefer flat
  curvature: 0.10        # 0 = flat, ~0.2 = strongly bulged
  corner_radius: 0.045
  vignette: 0.22
  scanlines: true
  scanline_intensity: 0.12
```

The CRT effect is a cosmetic shader: if it ever fails to compile on a given GPU,
mpv just logs it and keeps playing. Toggle it live by editing `crt.enabled` and
restarting the service. 4:3 shows are always pillar-boxed (never stretched)
inside the frame.

---

## Running it as an appliance

`./scripts/install.sh --service` installs a systemd unit that renders straight
to the TV over the console (KMS/DRM — no desktop). Useful commands:

```bash
systemctl status nostalgiabox      # is it running?
journalctl -u nostalgiabox -f      # live logs
sudo systemctl restart nostalgiabox
sudo systemctl disable nostalgiabox  # stop starting on boot
```

---

## Developing / testing (no Pi required)

The interesting logic (channel scanning, shuffle, the whole state machine) is
pure Python and has no hardware dependencies, so you can run it anywhere:

```bash
pip install -e .[dev]
pytest                     # full test suite

# Drive the app from your terminal with a mock player (no video, no libmpv):
python -m nostalgiabox --dry-run --config config.yaml
# arrows = channel/volume, digits = channel, m = mute, i = info, q = quit
```

### How it's put together

```
nostalgiabox/
├── config.py      # YAML -> validated Config / ChannelConfig
├── playlist.py    # ShuffleBag: shuffle, once each, then reshuffle
├── channel.py     # scan folders, tune-in modes, channel navigation
├── probe.py       # optional ffprobe duration lookup (broadcast mode)
├── player.py      # Player interface: MpvPlayer (libmpv) + MockPlayer (tests)
├── overlay.py     # ASS overlays: channel banner, volume bar, standby
├── input/         # remote input: evdev keyboard, HDMI-CEC, stdin, keymap
├── static_gen.py  # ffmpeg-generated static & colour-bar clips
├── app.py         # TVApp: the state machine tying it all together
└── __main__.py    # the `nostalgiabox` CLI
```

The `Player` and input backends are the only hardware-facing parts; both have
test doubles, so the entire behaviour is exercised without a screen or media.

---

## Troubleshooting

- **`nostalgiabox --check` shows a channel with 0 episodes.** The folder path is
  wrong or the files use an extension not in `video_extensions`.
- **No video on the Pi.** Ensure `mpv`/`libmpv2` are installed (the installer
  does this) and that the service has the `video`/`render` groups (it does by
  default). Check `journalctl -u nostalgiabox`.
- **TV remote does nothing.** Enable HDMI-CEC on the TV (Anynet+/SimpLink/etc.)
  and confirm `cec-client` sees key presses. USB/IR remotes need read access to
  `/dev/input/*` (the service runs in the `input` group).
- **Static clip missing.** Run `nostalgiabox --generate-assets` (needs ffmpeg).
  Without it, channel changes simply skip the snow — everything else still works.

---

## License

MIT — see [`pyproject.toml`](pyproject.toml). Enjoy your nostalgia box!
