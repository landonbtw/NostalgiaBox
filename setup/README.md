<div align="center">

# 📺 NostalgiaBox Setup (BusyParent)

**A web page to run your [NostalgiaBox](https://github.com/landonbtw/NostalgiaBox) retro TV, with no SSH, no config files and no terminal after the first install.**

![Raspberry Pi 4](https://img.shields.io/badge/Raspberry%20Pi-4-c51a4a?logo=raspberrypi&logoColor=white)
![Python](https://img.shields.io/badge/Python-3%20(stdlib%20only)-3776ab?logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-untested%20on%20real%20hardware-orange)

</div>

NostalgiaBox turns a Raspberry Pi into a retro kids-TV channel box. This project adds the part
that makes it friendly for a family: **install once, then do everything from your phone.**

> **Heads-up:** this was built and tested against stand-ins for NostalgiaBox and the network
> (see [Tests](#tests)). It has **not yet been run on a real Pi 4 with a TV**. See
> [Honest notes](#honest-notes) and please open an issue if something doesn't behave.

## ✨ What you get

- **Channel drop-down.** Pick how many channels; each one gets its own tab.
- **Two ways to fill a channel.**
  - **Upload** videos straight from your phone or computer (files, folders, drag and drop, with progress).
  - **Network folder.** Point a channel at a share on your Unraid / NAS / Windows PC (**SMB or NFS**) and pick the folder with a built-in browser. Read-only: the box can never change your server.
- **Everything on one page.** Playback, sound output, the CRT look, daily screen time, the page password, time zone, restart, reboot and shut down.
- **"Box is ready" on the TV.** After install the TV shows the address and login, and tells you to log in and change the password.
- **Daily screen-time limit.** After N hours the TV goes to "OFF THE AIR" static until the next day. Survives unplugging.
- **Works with your Plex library.** Point at the same folders Plex reads. No Plex token needed.
- **Nothing about the TV changes.** Shows still play through NostalgiaBox itself (banner, CRT curve, the remote).

## 🧰 What you need

| | |
|---|---|
| Computer | Raspberry Pi 4 (the same hardware NostalgiaBox uses) |
| OS | Raspberry Pi OS Lite, 64-bit |
| Remote | Flirc + any remote, as in the NostalgiaBox README |
| Network | Wi-Fi or Ethernet, same network as your phone |
| Shows | Uploaded to the Pi, or on a network share (SMB / NFS) |

## 🚀 Quick start

**1. Flash the card.** In Raspberry Pi Imager choose *Raspberry Pi 4*, *Raspberry Pi OS Lite (64-bit)*,
then **Edit Settings**: hostname `nostalgiabox`, a username and password, your Wi-Fi, and **Enable SSH**.
Put the card in the Pi, connect the TV and power, and wait a minute.

**2. Install (the only terminal step).** Connect to the Pi (`ssh <user>@nostalgiabox.local`, or use
Termius) and run:

```bash
sudo apt install -y git
git clone https://github.com/Ryanmnolan/NostalgiaBoxBusyParent.git ~/NostalgiaBox
bash ~/NostalgiaBox/setup/install.sh
```

It installs NostalgiaBox first if it's missing (answer `y` if asked), then the setup page. It takes
several minutes. When the box with the web address appears, you can close the terminal for good.

**3. Log in.** The TV now shows **BOX IS READY** with the address. On a phone or computer on the same
network open it (for example `http://192.168.1.57:8080` or `http://nostalgiabox.local:8080`) and log in:

| Username | Password |
|---|---|
| `admin` | `nostalgia` |

Then **change the password** (the yellow banner takes you there).

**4. Set up channels.** Choose the number of channels, name each one, add shows (below), then tap
**Save & apply**. The TV restarts with your channels.

## 📡 Adding shows

### Upload
Tap *Choose files* or *Choose a folder*, or drag videos onto the box. Season sub-folders are kept.
Uploads land in `/media/nostalgiabox/channel-N/` on the SD card, so watch the free-space readout.

### Network folder (best if the shows are on Unraid, a NAS or a PC)
1. Choose **SMB** (Windows / Unraid / most NAS) or **NFS**.
2. Enter the **server** name or IP.
3. Enter the **share name** (SMB) or **export path**, like `/mnt/user/media` (NFS).
4. Enter a username and password for SMB, or leave both empty for a guest share.
5. Tap **Connect & choose folder…**, browse into the show's folder, then **Use this folder**.

The mount is read-only, saved in `/etc/fstab`, and retried every minute if the server is off, so it
recovers by itself. Use *Skip some episodes* to hide seasons (`6-25`) or names (`*special*`).

> **Using Plex?** The box reads the same files Plex does. On Unraid, turn on SMB (or NFS) export for
> the share. The page doesn't talk to Plex itself.

## ⏱ Daily screen time

Turn on **Limit how long the TV can play each day**, choose the hours and when a new day starts. Time
counts only while a show is playing and is saved to the SD card every 30 seconds. Set the **time zone**
at the bottom of the page first so "midnight" is your midnight.

## 🛠 Everyday use

| To do this | Do this |
|---|---|
| Add shows | Open the page, go to the channel's tab, upload or add to the network folder, then Save & apply |
| Change the password | *Password* section |
| Restart the picture | *This box*, *Restart the TV picture* |
| Turn it off safely | *Shut down* on the page, or the remote's volume-down at 0 |
| Update this project | `cd ~/NostalgiaBox && git pull && bash setup/install.sh` (settings and shows are kept) |
| Remove it | `bash ~/NostalgiaBox/setup/install.sh --uninstall` (videos and settings stay) |

## 🩺 Troubleshooting

- **TV says "NO SHOWS FOUND YET."** The settings are saved but no channel has a video. Look for a ⚠ on
  the channel tabs. For network folders it is usually the share name, folder or password.
- **Can't open the page.** Use the exact address on the TV, on the same network. `nostalgiabox.local`
  doesn't work on some Android phones; use the IP address.
- **"The server said no."** Check the username and password. For NFS, check the server allows this box's IP.
- **Logs.** `sudo journalctl -u nostalgiabox -f` (TV side) and `sudo journalctl -u nostalgiabox-web -f` (page side).
- **Forgot the page password.**
  `sudo rm /var/lib/nostalgiabox-setup/auth.json && sudo systemctl restart nostalgiabox-web`
  resets the login to `admin` / `nostalgia`.

## 🔍 Honest notes

- **Untested on real hardware.** Everything passes in automated tests (below), and the config this
  page writes is accepted by the real `nostalgiabox --check`. But real SMB/NFS mounts, Pi 4 speed
  and the actual TV output haven't been tried yet.
- **Depends on NostalgiaBox.** It needs NostalgiaBox's `--config` option and its
  `nostalgiabox.service`. The installer reads that service to learn how NostalgiaBox starts. If
  upstream changes those, this may need an update.
- **Channels come from this page, not folder discovery.** The page writes an explicit channel list,
  so NostalgiaBox's automatic "one folder = one channel" and USB-drive detection are not used.
- **Don't use NostalgiaBox's read-only SD "overlay" mode** with this. It would forget settings, uploads
  and screen-time at every power-off.
- **HTTP only.** The page uses a password over plain HTTP, like many home devices. Keep the box on your
  home network and don't expose it to the internet.
- **Default login is shown on the TV** until you change it, so change it right away.
- The page login is separate from the Pi's own login.

## 🧩 How it fits together

| Piece | What it does |
|---|---|
| `install.sh` | Installs it all, using the NostalgiaBox checkout it sits inside. |
| `app/server.py` + `app/index.html` | The setup page. Python standard library only; runs as your normal user on port 8080. |
| `app/controller.py` | Replaces the start command of NostalgiaBox's service. Chooses between the ready screen, your channels and off-air static, then runs NostalgiaBox. |
| `sbin/nostalgiabox-helper` | The only root component (mounts, reboot, time zone), reachable through one restricted `sudo` rule. It re-checks everything it is sent. |
| `app/screens.py` | Draws the ready and off-air screens. They play as one-channel stations through NostalgiaBox, so they reach the TV the same way your shows do. |
| `app/discover_base.py` | Reads NostalgiaBox's service at install time to learn how it starts. |
| `/var/lib/nostalgiabox-setup/` | Saved settings, hashed login, generated `config.yaml`, screen-time count |

## 🧪 Tests

```bash
python3 setup/tests/test_units.py  # settings, helper input checks, config generation
python3 setup/tests/e2e.py            # the page in a real browser (needs Playwright)
python3 setup/tests/test_controller.py   # TV mode switching, with a stand-in for NostalgiaBox
```

## 🤝 Contributing

Issues and pull requests are welcome, especially reports from a real Pi 4 and TV.

## 🙏 Credits & license

- This is a fork of [**NostalgiaBox**](https://github.com/landonbtw/NostalgiaBox) by landonbtw, which does the actual TV playback. The `setup/` folder is the add-on.
- Released under the repo's [MIT License](../LICENSE).
