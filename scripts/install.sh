#!/usr/bin/env bash
#
# NostalgiaBox installer for Raspberry Pi OS / Debian.
#
# One command does the whole setup, and it is safe to run again:
#
#   bash ~/NostalgiaBox/scripts/install.sh
#
# The path above works from any folder. You do not need to "cd" first, and
# you should not put "sudo" in front of this script. It asks for your
# password when it needs administrator rights.
#
# What it does:
#   - installs mpv, ffmpeg, and the Python packages
#   - puts the "nostalgiabox" command on PATH (so it works from any folder)
#   - creates /media/nostalgiabox for show folders, owned by you
#   - mounts a USB show drive at /media/nostalgiabox-usb when one is plugged in
#   - creates config.yaml if you do not already have one
#   - turns on the boot-to-TV service
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_SERVICE=1

usage() {
  cat <<EOF
Install NostalgiaBox. Safe to run more than once, from any directory.

  bash ${REPO_DIR}/scripts/install.sh

Options:
  --service       Turn on boot-to-TV. This is already the default.
  --no-service    Install everything except the boot-to-TV service.
  --help          Show this message.

Repository: ${REPO_DIR}
EOF
}

for arg in "$@"; do
  case "${arg}" in
    --help|-h)
      usage
      exit 0
      ;;
    --service)
      INSTALL_SERVICE=1
      ;;
    --no-service)
      INSTALL_SERVICE=0
      ;;
    *)
      echo "unknown argument: ${arg}" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "${EUID}" -eq 0 ]]; then
  echo "error: run this as the user you SSH in as, without sudo." >&2
  echo "The script will ask for your password when it needs it." >&2
  echo "  bash ${REPO_DIR}/scripts/install.sh" >&2
  exit 1
fi

on_error() {
  local line="$1"
  echo ""
  echo "==> Install stopped at line ${line}."
  echo "    Read the error just above this message."
  echo "    It is safe to run the same command again:"
  echo "      bash ${REPO_DIR}/scripts/install.sh"
}
trap 'on_error ${LINENO}' ERR

RUN_USER="$(id -un)"
RUN_UID="$(id -u)"
RUN_GID="$(id -g)"
RUN_GROUP="$(id -gn)"
MEDIA_ROOT="/media/nostalgiabox"
USB_ROOT="/media/nostalgiabox-usb"

echo "==> Installing NostalgiaBox from ${REPO_DIR}"
echo "    This is safe to run more than once."

echo "==> Installing system packages (mpv, ffmpeg, Python, USB filesystems)"
sudo apt-get update
packages=(
  git
  mpv
  ffmpeg
  cec-utils
  python3
  python3-pip
  python3-venv
  python3-evdev
  exfatprogs
  ntfs-3g
)
if apt-cache show libmpv2 >/dev/null 2>&1; then
  packages+=(libmpv2)
elif apt-cache show libmpv1 >/dev/null 2>&1; then
  packages+=(libmpv1)
fi
sudo apt-get install -y "${packages[@]}"

echo "==> Creating a virtual environment in ${REPO_DIR}/.venv"
python3 -m venv --system-site-packages "${REPO_DIR}/.venv"
# shellcheck disable=SC1091
source "${REPO_DIR}/.venv/bin/activate"

echo "==> Installing NostalgiaBox and its Python packages"
python -m pip install --upgrade pip
# Editable install: a later "git pull" plus this installer picks up code changes.
python -m pip install -e "${REPO_DIR}[pi]"

if [[ ! -x "${REPO_DIR}/.venv/bin/nostalgiabox" ]]; then
  echo "error: ${REPO_DIR}/.venv/bin/nostalgiabox was not created." >&2
  exit 1
fi

echo "==> Putting the nostalgiabox command on PATH"
# The program lives in the virtual environment. A symlink in /usr/local/bin
# is what makes "nostalgiabox --check" work from any folder, including a
# brand-new SSH session that has not activated the virtual environment.
sudo ln -sfn "${REPO_DIR}/.venv/bin/nostalgiabox" /usr/local/bin/nostalgiabox

echo "==> Generating the static and colour-bar clips"
python -m nostalgiabox.static_gen || echo "    (clip generation failed; the TV still works without them)"

echo "==> Installing the retro on-screen font (VT323)"
mkdir -p "${HOME}/.local/share/fonts" "${HOME}/.config/mpv/fonts"
if compgen -G "${REPO_DIR}/nostalgiabox/assets/fonts/*.ttf" > /dev/null; then
  cp "${REPO_DIR}"/nostalgiabox/assets/fonts/*.ttf "${HOME}/.local/share/fonts/" || true
  cp "${REPO_DIR}"/nostalgiabox/assets/fonts/*.ttf "${HOME}/.config/mpv/fonts/" || true
  if command -v fc-cache >/dev/null 2>&1; then
    fc-cache -f "${HOME}/.local/share/fonts" || true
  fi
fi

echo "==> Creating the show folder ${MEDIA_ROOT}"
sudo mkdir -p "${MEDIA_ROOT}" "${USB_ROOT}"
sudo chown "${RUN_USER}:${RUN_GROUP}" "${MEDIA_ROOT}"
sudo chmod 775 "${MEDIA_ROOT}"
# The USB path stays owned by root until a drive is mounted on top of it.
sudo chown root:root "${USB_ROOT}"
sudo chmod 755 "${USB_ROOT}"

echo "==> Preparing the config file"
sudo mkdir -p /etc/nostalgiabox
if [[ ! -f "${REPO_DIR}/config.yaml" ]]; then
  cp "${REPO_DIR}/config.example.yaml" "${REPO_DIR}/config.yaml"
  echo "    Created ${REPO_DIR}/config.yaml"
  echo "    You usually do not need to edit it. Show folders become channels."
else
  echo "    Leaving your existing file in place: ${REPO_DIR}/config.yaml"
fi
sudo ln -sfn "${REPO_DIR}/config.yaml" /etc/nostalgiabox/config.yaml
sudo tee /etc/nostalgiabox/usb.env >/dev/null <<EOF
MOUNT_UID=${RUN_UID}
MOUNT_GID=${RUN_GID}
EOF
sudo chmod 644 /etc/nostalgiabox/usb.env

echo "==> Teaching the Pi to mount a USB show drive at ${USB_ROOT}"
usb_unit="/etc/systemd/system/nostalgiabox-usb.service"
usb_tmp="$(mktemp)"
sed "s|__REPO_DIR__|${REPO_DIR}|g" "${REPO_DIR}/scripts/nostalgiabox-usb.service" > "${usb_tmp}"
sudo cp "${usb_tmp}" "${usb_unit}"
rm -f "${usb_tmp}"
rules_tmp="$(mktemp)"
sed "s|__MOUNT_SCRIPT__|${REPO_DIR}/scripts/mount-usb.sh|g" \
  "${REPO_DIR}/scripts/99-nostalgiabox-usb.rules" > "${rules_tmp}"
sudo cp "${rules_tmp}" /etc/udev/rules.d/99-nostalgiabox-usb.rules
rm -f "${rules_tmp}"
sudo chmod 755 "${REPO_DIR}/scripts/mount-usb.sh"
if command -v udevadm >/dev/null 2>&1; then
  sudo udevadm control --reload-rules || true
fi
sudo systemctl daemon-reload
sudo systemctl enable nostalgiabox-usb.service
if ! sudo systemctl start nostalgiabox-usb.service; then
  echo "    warning: the USB mount helper did not start."
  echo "    Shows on the SD card still work. Details:"
  echo "      systemctl status nostalgiabox-usb.service --no-pager"
fi

if [[ "${INSTALL_SERVICE}" -eq 1 ]]; then
  echo "==> Turning on boot-to-TV"
  "${REPO_DIR}/scripts/install-service.sh"
else
  echo "==> Skipping the boot-to-TV service (--no-service)."
  echo "    Turn it on later with: bash ${REPO_DIR}/scripts/install.sh"
fi

echo "==> Checking the setup (it is normal to have no shows yet)"
set +e
/usr/local/bin/nostalgiabox --check
check_status=$?
set -e
if [[ "${check_status}" -eq 2 ]]; then
  echo "error: the configuration file has a problem. The report above says how to fix it." >&2
  exit 1
fi

if [[ ":${PATH}:" != *":/usr/local/bin:"* ]]; then
  echo "warning: /usr/local/bin is not on PATH in this shell."
  echo "         Log out of SSH and back in, then run: nostalgiabox --check"
fi

cat <<EOF

==> NostalgiaBox is installed.

The nostalgiabox command works from any folder. Try:

    nostalgiabox --check

NEXT STEP — add your shows.

Each show goes in its own folder. The folder name is the channel name
(for example a folder named "Dragon Tales").

Easiest: put those folders on a USB drive, plug it into the Pi, wait
15 seconds, then run:

    nostalgiabox --check

A USB drive with show folders is used automatically.

To store shows on the SD card instead, copy them into:

    ${MEDIA_ROOT}

The TV starts by itself when the Pi powers on. After the shows are in
place, start it now with:

    sudo systemctl restart nostalgiabox

If the picture does not appear, view the log with:

    journalctl -u nostalgiabox -f

EOF
