#!/usr/bin/env bash
#
# NostalgiaBox installer for Raspberry Pi OS (Bookworm) / Debian-based systems.
#
# Installs system + Python dependencies, generates the filler assets, and
# optionally installs a systemd service so the box boots straight into "TV mode".
#
# Usage:
#   ./scripts/install.sh              # install deps + assets
#   ./scripts/install.sh --service    # ...and install & enable the systemd unit
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_SERVICE=0
for arg in "$@"; do
  case "$arg" in
    --service) INSTALL_SERVICE=1 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

echo "==> Installing system packages (mpv/libmpv, ffmpeg, cec-utils, python)"
sudo apt-get update
sudo apt-get install -y \
  mpv libmpv2 \
  ffmpeg \
  cec-utils \
  python3 python3-pip python3-venv \
  python3-evdev

echo "==> Creating a virtual environment in ${REPO_DIR}/.venv"
python3 -m venv --system-site-packages "${REPO_DIR}/.venv"
# shellcheck source=/dev/null
source "${REPO_DIR}/.venv/bin/activate"

echo "==> Installing NostalgiaBox and Python dependencies"
pip install --upgrade pip
# Editable install so that a plain `git pull` picks up code updates without
# needing to reinstall (just restart the service afterwards).
pip install -e "${REPO_DIR}[pi]"

echo "==> Generating filler assets (static + colour bars)"
python -m nostalgiabox.static_gen || echo "   (asset generation skipped/failed - box still works)"

echo "==> Installing the retro OSD font (VT323)"
# NostalgiaBox also copies this into mpv's font dir at runtime, but installing it
# system-wide makes it available everywhere (and to fontconfig).
mkdir -p "${HOME}/.local/share/fonts" "${HOME}/.config/mpv/fonts"
if compgen -G "${REPO_DIR}/nostalgiabox/assets/fonts/*.ttf" > /dev/null; then
  cp "${REPO_DIR}"/nostalgiabox/assets/fonts/*.ttf "${HOME}/.local/share/fonts/" || true
  cp "${REPO_DIR}"/nostalgiabox/assets/fonts/*.ttf "${HOME}/.config/mpv/fonts/" || true
  command -v fc-cache > /dev/null && fc-cache -f "${HOME}/.local/share/fonts" || true
fi

if [[ ! -f "${REPO_DIR}/config.yaml" ]]; then
  echo "==> Creating a starter config.yaml (edit it to point at your shows!)"
  cp "${REPO_DIR}/config.example.yaml" "${REPO_DIR}/config.yaml"
fi

echo "==> Validating configuration"
nostalgiabox --check --config "${REPO_DIR}/config.yaml" || \
  echo "   (fix config.yaml, then re-run: nostalgiabox --check)"

if [[ "${INSTALL_SERVICE}" -eq 1 ]]; then
  echo "==> Installing systemd service"
  "${REPO_DIR}/scripts/install-service.sh"
fi

cat <<EOF

==> Done!

Next steps:
  1. Edit ${REPO_DIR}/config.yaml so the channels point at your show folders.
  2. Copy your episodes onto the SD card (e.g. under /media/nostalgiabox/<show>/).
  3. Test it:   nostalgiabox --check
                nostalgiabox                 # starts the TV
  4. Auto-start on boot:   ./scripts/install.sh --service

Enjoy your nostalgia box!
EOF
