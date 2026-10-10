#!/usr/bin/env bash
# NostalgiaBox Setup: installs NostalgiaBox plus a web page to set it up from
# your phone or computer (channels, uploads, network folders, screen time).
#
#   bash install.sh              install or update
#   bash install.sh --uninstall  remove the setup page (your shows and settings stay)
#
# Run it as your normal user (the one NostalgiaBox runs as), not as root.
# It asks for your password when it needs sudo.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NB_REPO="https://github.com/landonbtw/NostalgiaBox.git"
APP_DIR=/opt/nostalgiabox-setup
STATE_DIR=/var/lib/nostalgiabox-setup
ETC_DIR=/etc/nostalgiabox-setup
MEDIA_DIR=/media/nostalgiabox
MOUNT_DIR=/mnt/nostalgiabox
HELPER=/usr/local/sbin/nostalgiabox-helper
PORT=8080

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# ---- who is this for? -------------------------------------------------------
if [ "$(id -u)" -eq 0 ]; then
  if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
    APP_USER="$SUDO_USER"
  else
    die "Run this as your normal user, not root:  bash install.sh   (it uses sudo when needed)"
  fi
  SUDO=""
else
  APP_USER="$(id -un)"
  SUDO="sudo"
fi
APP_GROUP="$(id -gn "$APP_USER")"
APP_UID="$(id -u "$APP_USER")"
APP_GID="$(id -g "$APP_USER")"
APP_HOME="$(getent passwd "$APP_USER" | cut -d: -f6)"

# ---- uninstall --------------------------------------------------------------
if [ "${1:-}" = "--uninstall" ]; then
  say "Removing the NostalgiaBox setup page"
  $SUDO systemctl disable --now nostalgiabox-web.service 2>/dev/null || true
  $SUDO rm -f /etc/systemd/system/nostalgiabox-web.service
  $SUDO rm -rf /etc/systemd/system/nostalgiabox.service.d
  $SUDO systemctl daemon-reload
  for mp in "$MOUNT_DIR"/ch* "$MOUNT_DIR/.browse"; do
    [ -d "$mp" ] && mountpoint -q "$mp" && $SUDO umount "$mp" 2>/dev/null || true
  done
  $SUDO sed -i '/# >>> nostalgiabox-setup/,/# <<< nostalgiabox-setup/d' /etc/fstab
  $SUDO rm -f "$HELPER" /etc/sudoers.d/nostalgiabox-setup
  $SUDO rm -rf "$APP_DIR" "$ETC_DIR"
  $SUDO systemctl restart nostalgiabox.service 2>/dev/null || true
  echo "Done. NostalgiaBox is back to starting from its own config.yaml."
  echo "Your videos ($MEDIA_DIR) and settings ($STATE_DIR) were left in place."
  exit 0
fi

[ -f "$SRC/app/server.py" ] || die "Run install.sh from inside the setup folder."

# ---- 1. packages ------------------------------------------------------------
say "Installing packages (a minute or two)"
$SUDO apt-get update
$SUDO apt-get install -y git python3 python3-yaml python3-pil fonts-dejavu-core ffmpeg cifs-utils nfs-common
python3 -c "import yaml, PIL" || die "Python libraries (yaml, PIL) are missing."

# ---- 2. NostalgiaBox itself -------------------------------------------------
# When this folder lives inside a NostalgiaBox checkout (like the BusyParent fork),
# use that checkout. Otherwise fetch NostalgiaBox next to it.
if [ -f "$SRC/../scripts/install.sh" ] && [ -d "$SRC/../nostalgiabox" ]; then
  NB_HOME="$(cd "$SRC/.." && pwd)"
else
  NB_HOME="$APP_HOME/NostalgiaBox"
fi
as_user() { if [ -n "$SUDO" ]; then "$@"; else sudo -u "$APP_USER" "$@"; fi; }
if systemctl cat nostalgiabox.service >/dev/null 2>&1; then
  say "NostalgiaBox is already installed. Keeping it."
else
  say "Installing NostalgiaBox"
  if [ -f "$NB_HOME/scripts/install.sh" ]; then
    :  # already have the code; do not pull over your own changes
  else
    as_user git clone "$NB_REPO" "$NB_HOME"
  fi
  echo "(If it asks whether to continue, answer y.)"
  ( cd "$NB_HOME" && as_user ./scripts/install.sh )
  say "Setting NostalgiaBox up to start on boot"
  ( cd "$NB_HOME" && as_user ./scripts/install.sh --service )
fi
systemctl cat nostalgiabox.service >/dev/null 2>&1 || \
  die "NostalgiaBox's service isn't there. Run './scripts/install.sh --service' in $NB_HOME, then run this again."

# ---- 3. folders -------------------------------------------------------------
say "Creating folders"
$SUDO install -d -o "$APP_USER" -g "$APP_GROUP" -m 755 "$MEDIA_DIR" "$STATE_DIR"
$SUDO install -d -m 755 "$ETC_DIR" "$MOUNT_DIR" "$APP_DIR"
$SUDO install -d -m 700 "$ETC_DIR/creds"

# ---- 4. the app and the root helper ----------------------------------------
say "Installing the setup page"
for f in nbcommon.py server.py controller.py screens.py index.html; do
  $SUDO install -m 644 -o root -g root "$SRC/app/$f" "$APP_DIR/$f"
done
$SUDO install -m 755 -o root -g root "$SRC/sbin/nostalgiabox-helper" "$HELPER"
printf '{"uid": %s, "gid": %s}\n' "$APP_UID" "$APP_GID" | $SUDO tee "$ETC_DIR/helper.json" >/dev/null
$SUDO chmod 644 "$ETC_DIR/helper.json"

SUDOERS_TMP="$(mktemp)"
echo "$APP_USER ALL=(root) NOPASSWD: $HELPER" > "$SUDOERS_TMP"
$SUDO visudo -cf "$SUDOERS_TMP" >/dev/null || die "Couldn't create the sudo rule."
$SUDO install -m 440 -o root -g root "$SUDOERS_TMP" /etc/sudoers.d/nostalgiabox-setup
rm -f "$SUDOERS_TMP"

# ---- 5. learn how NostalgiaBox's service starts it --------------------------
say "Reading NostalgiaBox's service"
$SUDO python3 "$SRC/app/discover_base.py" --unit nostalgiabox.service --out "$ETC_DIR/base-command.json"
$SUDO chmod 644 "$ETC_DIR/base-command.json"
UNIT_USER="$(python3 -c "import json;print(json.load(open('$ETC_DIR/base-command.json')).get('user') or '')")"
if [ -n "$UNIT_USER" ] && [ "$UNIT_USER" != "$APP_USER" ]; then
  die "NostalgiaBox runs as '$UNIT_USER' but you ran this as '$APP_USER'. Log in as '$UNIT_USER' and run it again."
fi

# ---- 6. services ------------------------------------------------------------
say "Setting up the services"
$SUDO install -d /etc/systemd/system/nostalgiabox.service.d
$SUDO install -m 644 "$SRC/systemd/10-setup.conf" /etc/systemd/system/nostalgiabox.service.d/10-setup.conf
sed "s/__USER__/$APP_USER/" "$SRC/systemd/nostalgiabox-web.service" | $SUDO tee /etc/systemd/system/nostalgiabox-web.service >/dev/null
$SUDO systemctl daemon-reload
$SUDO systemctl enable nostalgiabox.service nostalgiabox-web.service
$SUDO systemctl restart nostalgiabox-web.service
$SUDO systemctl restart nostalgiabox.service

sleep 2
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
HOST="$(hostname)"
cat <<EOF

=========================================================================
  NostalgiaBox setup is installed.

  In a minute the TV shows a "Box is ready" screen. From your phone or
  computer (same network) open:

      http://${IP:-<the box's address>}:${PORT}
      or  http://${HOST}.local:${PORT}

  Username:  admin
  Password:  nostalgia      <- change it after you log in

  Then: pick how many channels, fill in each tab, tap Save & apply.
=========================================================================
EOF
