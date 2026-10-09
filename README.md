# NostalgiaBox

**Turn a Raspberry Pi into a retro TV for your kids.**

NostalgiaBox plays folders of old children's shows as if they were real TV
**channels**. Flip to a channel and a show is already playing (starting a few
seconds in, like you just tuned in); when an episode ends, the next one rolls
automatically on an endless shuffle. It boots straight to the TV on power-up, is
driven by a simple remote, sends audio over HDMI, and has an authentic
early-2000s vibe — a green on-screen channel banner and volume bar, and a curved
"CRT" picture. No menus, no apps, no touchscreens. Just a remote and channels.

Follow the steps in order. Each step says **which machine** to use, the
**exact command** to copy, and **what you should see** when it worked.

You will use two machines:

- **Your computer** — the Mac or Windows PC on your desk. Steps 1, 2, 4, and 8.
- **The Pi** — the Raspberry Pi, reached from your computer with SSH. Steps 5, 6, 7, 9, and 10.

---

## Words this guide uses

Two names come from the SD card setup in step 2. Write them down. Every later
command that contains them means "type what you wrote down".

| Placeholder | What to type instead | Example |
|-------------|----------------------|---------|
| `YOUR_USERNAME` | The username you set in Raspberry Pi Imager | `admin` |
| `YOUR_HOSTNAME` | The hostname you set in Raspberry Pi Imager | `TVShows` |

If your username is `admin` and your hostname is `TVShows`, this guide's

```bash
ssh YOUR_USERNAME@YOUR_HOSTNAME.local
```

is the real command

```bash
ssh admin@TVShows.local
```

Hostnames are not case-sensitive. `TVShows.local` and `tvshows.local` are the
same Pi.

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

- A **micro SD card**, 32 GB or larger. This holds the operating system. Shows
  can live on this card too, or on a USB drive (step 6).
- A **USB-C power supply** for the Pi 4 (the official 3A one is recommended).
- A **TV with an HDMI port**.
- A **computer** (Mac or Windows) to set up the SD card and program the remote.
- Your **show video files** (`.mp4`, `.mkv`, and similar episodes you own).
- Optional: a **USB drive** (flash drive or portable hard drive) if you want
  the videos somewhere other than the SD card. Format it as **exFAT** so files
  larger than 4 GB work on Mac, Windows, and the Pi.

---

## 2. Flash the SD card

**On your computer.**

1. Install **Raspberry Pi Imager** from
   [raspberrypi.com/software](https://www.raspberrypi.com/software/).
2. Put the micro SD card into your computer.
3. Open Raspberry Pi Imager and choose:
   - **Device:** Raspberry Pi 4
   - **Operating System:** *Raspberry Pi OS Lite (64-bit)* (under "Raspberry Pi
     OS (other)"). "Lite" has no desktop — the box boots straight to the TV.
   - **Storage:** your SD card
4. Click **Next**, then **Edit Settings** (the gear), and set:
   - **Hostname:** `nostalgiabox` is a good choice. Any name is fine. This is
     `YOUR_HOSTNAME`. Write it down.
   - **Enable SSH**, and choose **password authentication**.
   - **Username and password.** Pick them yourself and write them down. The
     username is `YOUR_USERNAME`. It will not be filled in for you.
   - **Wi-Fi** name and password, so the Pi can download NostalgiaBox once.
5. Write the card, then eject it.

**What you should see:** Imager says the card was written successfully.

---

## 3. Plug it in

**At the TV.** No typing yet.

1. Put the Pi in its case.
2. Plug the **Flirc** adapter into a USB port on the Pi. (You will unplug it
   in step 8 to program the remote, then plug it back in.)
3. Connect the **micro-HDMI → HDMI** cable from the Pi to the TV. On a Pi 4,
   use the micro-HDMI port **next to the USB-C power plug**.
4. Insert the SD card.
5. Plug in power. Wait about a minute. The TV may stay black. That is normal
   for Raspberry Pi OS Lite — there is no desktop.

---

## 4. Connect from your computer

**On your computer.** You are about to open a terminal *on the Pi*.

- **Mac:** open the **Terminal** app.
- **Windows:** open **PowerShell**.

Connect. Replace the two placeholders with the names from step 2:

```bash
ssh YOUR_USERNAME@YOUR_HOSTNAME.local
```

- The first time, type `yes` and press Enter to accept the fingerprint.
- Type the password from step 2. **Nothing appears while you type.** That is
  normal. Press Enter.

**What you should see:** the prompt changes to something like

```text
admin@TVShows:~ $
```

The word before `@` is your username. The word after `@` is the hostname. The
`~` means you are in your home folder on the Pi. Every command in steps 5, 6,
7, and 9 is typed at this prompt.

**If `YOUR_HOSTNAME.local` does not connect:** find the Pi's IP address on your
router's device list (it may be listed under the hostname), then connect with
that address instead:

```bash
ssh YOUR_USERNAME@192.168.1.50
```

Use the address your router shows, not the example numbers above.

---

## 5. Install NostalgiaBox

**On the Pi** (the SSH window from step 4).

Copy this whole block. It downloads the project into your home folder and
installs it. The install command works no matter which folder the prompt is
in. Do not put `sudo` in front of the install line — the installer asks for
your password itself.

```bash
cd ~
sudo apt update
sudo apt install -y git
git clone https://github.com/landonbtw/NostalgiaBox.git
bash ~/NostalgiaBox/scripts/install.sh
```

`sudo apt` asks for the same password as step 4. The installer takes a few
minutes. It installs the video player, creates the show folder, puts the
`nostalgiabox` command where every terminal can find it, and turns on
boot-to-TV.

**What you should see:** lines that start with `==>`, then a block that begins
with `==> NostalgiaBox is installed.` and tells you the next step. A check
near the end will say no show folders were found. That is expected — you have
not copied shows yet.

If `git clone` says the folder already exists, skip that line and run the
`bash ~/NostalgiaBox/scripts/install.sh` line again. Re-running the installer
is safe.

---

## 6. Put your shows where the TV can find them

**One folder per show. The folder name is the channel name.** Spaces are fine.
Season subfolders inside a show are fine. Use `.mp4`, `.mkv`, `.avi`, `.m4v`,
or `.mov`.

```text
Dragon Tales/
  S01E01.mp4
  S01E02.mp4
Arthur/
  Season 1/
    S01E01.mp4
```

With those two folders, alphabetical order makes **Arthur channel 2** and
**Dragon Tales channel 3**. Numbers start at 2. A new folder is inserted in
that same A-to-Z order (a folder named "Blue's Clues" would become channel 3,
between Arthur and Dragon Tales). No config edit is required for any of that.

| What | Path on the Pi |
|------|----------------|
| The program (do not put videos here) | `/home/YOUR_USERNAME/NostalgiaBox` |
| The settings file | `/home/YOUR_USERNAME/NostalgiaBox/config.yaml` |
| Shows stored on the SD card | `/media/nostalgiabox/NAME OF SHOW/` |
| A USB drive, once it is plugged in | `/media/nostalgiabox-usb/NAME OF SHOW/` |

The installer creates `/media/nostalgiabox` and makes it yours, so copy
commands below work without extra permission steps.

### Option A — USB drive (simplest)

The videos stay on the USB drive. Leave it plugged into the Pi. When the drive
has show folders on it, NostalgiaBox uses those and ignores the SD card folder.

**On your computer:**

1. Format the drive as **exFAT**.
   - **Mac:** open Disk Utility, select the drive (the physical disk, not a
     volume indented under it), click Erase, choose **ExFAT**, erase.
   - **Windows:** open File Explorer, right-click the drive, choose Format,
     choose **exFAT**, start.
2. On the drive, make one folder per show and copy the episode files into it.
   Use the layout at the top of this step.
3. Eject the drive from your computer and plug it into a USB port on the Pi.
4. Wait 15 seconds.

**On the Pi**, check that the drive showed up:

```bash
ls "/media/nostalgiabox-usb"
```

**What you should see:** your show folder names, such as `Dragon Tales`.

Then go to step 7. The files stay on the USB drive.

`/media/nostalgiabox-usb` is only a window onto that drive. Put the show
folders on the drive while it is plugged into your computer. Copying files
into `/media/nostalgiabox-usb` on the Pi while nothing is plugged in hides
those files the next time a drive is mounted there. The SD card folder
`/media/nostalgiabox` is a normal folder and is the right place for a copy
that should survive unplugging the drive.

### Option B — keep the shows on the SD card

Use this when you want to unplug the USB drive after copying, or when you are
copying over the network.

**From a USB drive, on the Pi.** Plug the drive in, wait 15 seconds, then copy
one show (repeat for each show, and use your real folder name):

```bash
cp -a "/media/nostalgiabox-usb/Dragon Tales" /media/nostalgiabox/
```

Unplug the USB drive when the copies are finished. While it stays plugged in
and still has show folders, the TV plays the USB copies.

**From a Mac, on your computer** (a new Terminal window, not the SSH one).
Replace the path with the folder on your Mac:

```bash
scp -r "/Users/YOURNAME/Movies/Dragon Tales" YOUR_USERNAME@YOUR_HOSTNAME.local:/media/nostalgiabox/
```

**From Windows, on your computer** (PowerShell):

```powershell
scp -r "C:\Users\YOURNAME\Videos\Dragon Tales" YOUR_USERNAME@YOUR_HOSTNAME.local:/media/nostalgiabox/
```

`scp` asks for the Pi password (again, the typing is invisible). It uploads
that one show folder into `/media/nostalgiabox/`. Repeat for each show.

**What you should see on the Pi:**

```bash
ls /media/nostalgiabox
```

lists your show folders.

---

## 7. Check that it worked

**On the Pi.** This command works from any folder:

```bash
nostalgiabox --check
```

**What you should see:** a report that ends in `Ready.` Each show folder is a
channel with an episode count above zero. A USB library looks like this:

```text
Shows
  OK   Using the USB drive at /media/nostalgiabox-usb

Channels
  OK   CH   2  Arthur                         40 episodes
  OK   CH   3  Dragon Tales                   26 episodes
       66 episodes in 2 channels
```

An SD card library says `Using the SD card folder /media/nostalgiabox` instead.

Any line that says `FIX` includes the command that corrects it. Run that
command, then run `nostalgiabox --check` again.

The TV service is already installed. After the check says `Ready`, start
playback now (you do not have to reboot):

```bash
sudo systemctl restart nostalgiabox
```

**What you should see:** the TV (on the HDMI input you used in step 3) starts
playing a show within a few seconds. The picture starts a few seconds into the
episode. That is intentional.

---

## 8. Program the remote

**On your computer.** The Flirc adapter learns your Simple TV Remote and turns
its buttons into keys NostalgiaBox already understands.

1. Unplug the Flirc from the Pi and plug it into your computer.
2. Install the **Flirc** app from [flirc.tv/downloads](https://flirc.tv/pages/downloads).
3. In the app, choose the **Full Keyboard** controller.
4. Click a key on the on-screen keyboard, then press the matching button on
   your remote:

   | Click this on-screen key | Press this remote button | What it does |
   |--------------------------|--------------------------|--------------|
   | **Up arrow** | Channel up | Next channel |
   | **Down arrow** | Channel down | Previous channel |
   | **Right arrow** | Volume up | Louder |
   | **Left arrow** | Volume down | Quieter |
   | **m** | Mute | Mute |
   | **p** | Power | Blank the screen (standby) |

5. Unplug the Flirc from your computer and plug it back into the Pi.

**What you should see:** channel buttons change the channel. Volume buttons
change the television's own volume when HDMI-CEC works, and the Pi's volume
otherwise. See [Volume](#volume). No config edit is required for this layout.
Flirc has no separate CEC mode — this Full Keyboard layout is the whole remote
setup. To use different keys later, see `key_overrides` in
[`config.example.yaml`](config.example.yaml). Find a button's Linux name with
`sudo evtest` on the Pi.

---

## 9. Send the sound to the TV

**On the Pi.** The Pi sometimes sends audio to the headphone jack. List the
outputs:

```bash
nostalgiabox --list-audio
```

**What you should see:** several lines. Find the one whose description mentions
**HDMI**. The name looks like `alsa/hdmi:CARD=vc4hdmi0,DEV=0`.

On a Pi 4, the HDMI port next to the USB-C power plug is `vc4hdmi0`. The other
micro-HDMI port is `vc4hdmi1`. Use the one that matches the cable from step 3.

**On the Pi**, open the settings file:

```bash
nano ~/NostalgiaBox/config.yaml
```

Add this line, using the name you found (keep the quotes):

```yaml
audio_device: "alsa/hdmi:CARD=vc4hdmi0,DEV=0"
```

Save with **Ctrl+O**, Enter, then leave nano with **Ctrl+X**. Apply it:

```bash
sudo systemctl restart nostalgiabox
```

**What you should see:** sound from the TV speakers.

---

## 10. Turn it off safely

Kids will pull the plug. Two habits keep the SD card from getting corrupted.

**Remote shutdown, when the Pi is doing volume** (`volume_control: pi`, which
is what you get if the TV has no HDMI-CEC). Turn the volume all the way down
to 0, then press volume-down **once more**. The screen says `GOODBYE`, the Pi
shuts down, and it is safe to unplug once the green light stops blinking.
Turn it back on by plugging the power in. It boots to a channel by itself.

**When the remote's volume keys control the TV** (the usual case; see
[Volume](#volume)), those keys cannot shut the Pi down, because they never
move the Pi's volume. The power button blanks the screen (standby). To shut
all the way down so it is safe to unplug, SSH in and run `sudo poweroff`.

**Read-only SD card (optional, stronger).** On the Pi:

```bash
sudo raspi-config
```

Open **Performance Options → Overlay File System**, enable it, and when asked,
write-protect the boot partition. Reboot. Pulling the power can no longer
corrupt the card. The USB show drive and anything you still want to change
(new episodes, a software update) need the overlay turned off first: run
`sudo raspi-config` again, disable the overlay, make the change, then enable
it again.

---

## Day to day

| Do this | On the remote |
|---------|---------------|
| Change channels | Channel up / down |
| Adjust volume | Volume up / down (the TV, when HDMI-CEC works) |
| Mute | Mute |
| Standby (blank screen) | Power |
| **Turn off** (safe to unplug) | Volume-down again at 0, **only** when the Pi is doing volume. Otherwise `sudo poweroff` over SSH |

New episodes: add files to that show's folder (on the USB drive, or under
`/media/nostalgiabox/NAME OF SHOW/`). The TV picks them up the next time that
channel starts an episode. If a brand-new show folder does not appear, run:

```bash
sudo systemctl restart nostalgiabox
```

---

## Volume

The remote does not have two volume knobs. One press moves one thing, once,
and letting go stops it.

**Television volume (the default when CEC works).** The installer puts
`cec-utils` on the Pi. If `cec-client` is there, volume up, volume down, and
mute on the Flirc remote are sent to the TV over HDMI-CEC. The Pi stays at
full output (`initial_volume: 100`), so a TV set to 40 is just 40 — the Pi is
not also sitting at 70 and making that quieter. Program the Flirc exactly as
in step 8 (Full Keyboard: Right = volume up, Left = volume down, **m** = mute).
On the TV, turn on HDMI-CEC. Makers call it Anynet+ (Samsung), SimpLink (LG),
BRAVIA Sync (Sony), or HDMI control. The on-screen note says `TV VOL +`,
`TV VOL -`, or `TV MUTE`. It is not a bar, because the Pi is not the knob and
does not know the TV's number.

**Pi volume.** Set this in `~/NostalgiaBox/config.yaml` when the TV ignores
CEC, or when you want the green bar:

```yaml
volume_control: pi
initial_volume: 100
```

Then `sudo systemctl restart nostalgiabox`. Each press adds or subtracts
`volume_step` (5 unless you change it). The level is one number for every
episode and every channel. It does not climb on its own after the bar
disappears, and a new show does not pick a new gain. `volume_control: auto`
(the default when the line is missing) uses the TV if CEC is available and the
Pi otherwise. `volume_control: tv` asks for the TV and falls back to the Pi
when CEC is missing.

Shows are not loudness-normalized. A quiet rip and a loud rip can still sound
different from each other. That is the file. Nothing in NostalgiaBox turns on
replaygain or a loudness filter.

If this Pi was set up before this change, `config.yaml` may still say
`initial_volume: 70`. The installer does not overwrite that file. Set it to
`100`, or delete the line, then restart the service.

---

## Updating

**On the Pi.** When you want a newer version of NostalgiaBox:

```bash
cd ~/NostalgiaBox
git pull
bash ~/NostalgiaBox/scripts/install.sh
```

**What you should see:** `git pull` reports the update (or "Already up to
date."), then the installer finishes with `==> NostalgiaBox is installed.`
Running the installer again is the update. It keeps your `config.yaml` and
your show folders, and it restarts the TV service.

If you turned on the read-only overlay in step 10, disable it in
`raspi-config` before these commands, then enable it again afterwards.

---

## Troubleshooting

Run `nostalgiabox --check` first. Read every `FIX` line and do what it says.

### `nostalgiabox: command not found`

The command was installed inside a hidden virtual environment, so the shell
could not see it. Current installers also link it into `/usr/local/bin`, which
is on the path in every folder and every new SSH session. Fix it with:

```bash
bash ~/NostalgiaBox/scripts/install.sh
```

Then open a new SSH session and run `nostalgiabox --check` again.

### `./scripts/install.sh: No such file or directory`

That happens when the prompt is already inside `~/NostalgiaBox/scripts` and the
command looks for a second `scripts` folder. Use this instead. It works from
any folder, including that one:

```bash
bash ~/NostalgiaBox/scripts/install.sh
```

Boot-to-TV is part of that command. You do not pass `--service`. (If an older
note told you to, `--service` is accepted and does the same install.)

### The check cannot find your shows, or you copied them into the program

Show folders belong in `/media/nostalgiabox/NAME OF SHOW/` or on the USB drive.
They do not belong in `~/NostalgiaBox/nostalgiabox/`. That second folder is the
program (you will see files like `app.py` and `player.py` there).

`nostalgiabox --check` prints a `mv` command for each show folder it finds in
the program directory. Run those commands, then run the check again.

If your `config.yaml` still lists paths such as
`/media/nostalgiabox/dragon-tales` (a made-up name from an older example), the
check will say those folders do not exist. Delete the whole `channels:` list
from `~/NostalgiaBox/config.yaml` and keep this line:

```yaml
media_root: /media/nostalgiabox
```

Real folder names are used as-is. A folder called `Dragon Tales` is the
channel "Dragon Tales".

### SSH says `pi@nostalgiabox.local` or "Could not resolve hostname"

Connect with the username and hostname from step 2, not with `pi` unless that
is the username you chose:

```bash
ssh YOUR_USERNAME@YOUR_HOSTNAME.local
```

### The USB drive does not show your shows

On the Pi:

```bash
ls "/media/nostalgiabox-usb"
bash ~/NostalgiaBox/scripts/mount-usb.sh
ls "/media/nostalgiabox-usb"
```

**What you should see:** after the mount command, `ls` prints your show
folders. The drive must be exFAT, NTFS, or a Linux filesystem (ext4), with one
folder per show and video files inside. A drive that only contains loose
`.mp4` files in its root does not count — make a folder per show.

NostalgiaBox uses the USB drive only when those folders contain videos. An
empty drive leaves the SD card library (`/media/nostalgiabox`) in charge.

If the automatic mount still fails, label the drive `NOSTALGIA` (Disk Utility
on a Mac, or the volume name when you format on Windows) and run
`bash ~/NostalgiaBox/scripts/mount-usb.sh` again. A drive with that label is
preferred when more than one USB disk is plugged in.

**Manual mount, if you would rather edit a system file.** On the Pi, find the
drive (the row whose `TRAN` column says `usb`):

```bash
lsblk -o NAME,LABEL,UUID,SIZE,TRAN,FSTYPE
id -u
id -g
```

For an **exFAT** drive, add one line to `/etc/fstab` with `sudo nano /etc/fstab`.
Use the UUID from `lsblk` and the two numbers from `id`:

```text
UUID=YOUR-UUID  /media/nostalgiabox-usb  exfat  defaults,nofail,uid=YOUR_UID,gid=YOUR_GID,umask=022,x-systemd.automount,x-systemd.idle-timeout=10  0  0
```

Then run `sudo systemctl daemon-reload` and `bash ~/NostalgiaBox/scripts/mount-usb.sh`.
`nofail` means the Pi still boots when the drive is unplugged. This exFAT line
is the right one for a drive formatted on Mac or Windows. A Linux ext4 drive
does not use the `uid=` and `gid=` options; `defaults,nofail,x-systemd.automount`
is enough, and the files on it need to be readable by your user.

### No picture on the TV

The HDMI cable must be in the port you configured, and the TV must be on that
input. Then, on the Pi:

```bash
sudo systemctl restart nostalgiabox
journalctl -u nostalgiabox -n 50 --no-pager
```

The log should mention channels, not a Python traceback. Leave it running
with `journalctl -u nostalgiabox -f` while you watch the TV.

### No sound

Repeat step 9. If you used `vc4hdmi0`, try `vc4hdmi1` (or the other way
around), then `sudo systemctl restart nostalgiabox`.

### Volume keeps climbing, or jumps between shows

One press should move the level once, and it should stop when you let go.
Older builds treated Flirc's held-key repeat as more presses, and mpv could
keep changing its own gain after the on-screen bar had gone (the console
keyboard was still connected, and mpv will boost past 100 unless it is capped).
A new episode could also come back at a different level. Update with the
commands under [Updating](#updating), then set `initial_volume: 100` in
`~/NostalgiaBox/config.yaml` if that line is still `70`, and restart:

```bash
sudo systemctl restart nostalgiabox
```

With the Pi at 100, the TV is the volume control. See [Volume](#volume). If
the remote still will not change the TV, the set's HDMI-CEC is off or the TV
does not support it. Set `volume_control: pi` for the on-screen bar instead.
Flirc stays on the step 8 layout either way. There is no per-show loudness
normalizer to turn off; it is not used.

### The remote does nothing

The Flirc has to be programmed (step 8) and plugged into the Pi. Unplug it,
plug it back in, and run `sudo systemctl restart nostalgiabox`.

### The Pi will not boot after the power was pulled

The SD card was likely corrupted by an unclean shutdown. Re-flash it from
step 2, then use the remote shutdown in step 10. The read-only overlay in that
step prevents a repeat.

---

## Settings you can change

Most people never open this file. When you do, it lives at
`~/NostalgiaBox/config.yaml`. Edit it on the Pi with `nano ~/NostalgiaBox/config.yaml`,
then run `nostalgiabox --check` and `sudo systemctl restart nostalgiabox`.

The full annotated file is [`config.example.yaml`](config.example.yaml). The
important knobs:

```yaml
media_root: /media/nostalgiabox
usb_media_root: /media/nostalgiabox-usb
prefer_usb: true             # a USB drive with videos wins over the SD folder
first_channel_number: 2
tune_in: random              # random | resume | broadcast
start_channel: 2
start_offset: [6, 10]        # start each episode 6–10 seconds in
transition: none             # none | glitch | static
initial_volume: 100          # Pi output. 100 = let the TV do the volume
volume_control: auto         # auto | tv | pi   (auto = TV when CEC works)
audio_device: "alsa/hdmi:CARD=vc4hdmi0,DEV=0"
```

To number channels yourself, or to skip seasons, uncomment a `channels:` list
in the example and copy it into `config.yaml`. While that list exists, folder
discovery is off, so every `path:` has to be a real folder.

---

## For the curious

The project is plain Python. Channel scanning, the shuffle, and the state
machine have no hardware dependencies and are unit-tested. The mpv player and
the remote input sit behind small interfaces. On a laptop:

```bash
pip install -e ".[dev]"
pytest
python -m nostalgiabox --dry-run --config config.yaml
```

```text
nostalgiabox/
├── config.py      YAML -> validated config, including folder discovery
├── doctor.py      the "nostalgiabox --check" report
├── usb.py         which USB partition to mount
├── playlist.py    the shuffle bag (each episode once, then reshuffle)
├── channel.py     folder scanning, tune-in modes, channel navigation
├── player.py      mpv player (+ a mock for tests)
├── volume.py      TV vs Pi volume mode
├── overlay.py     the green on-screen display
├── crt.py         the CRT shader
├── input/         remote input (Flirc/keyboard, HDMI-CEC, keymap)
├── static_gen.py  ffmpeg-generated static/glitch/colour-bar clips
└── app.py         the TV state machine
```

## License

MIT. Enjoy your nostalgia box!
