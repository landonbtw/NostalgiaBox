#!/usr/bin/env bash
#
# Install & enable the NostalgiaBox systemd service so the Pi boots into TV mode.
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="${REPO_DIR}/scripts/nostalgiabox.service"
TARGET="/etc/systemd/system/nostalgiabox.service"

RUN_USER="${SUDO_USER:-$USER}"
RUN_UID="$(id -u "${RUN_USER}")"
RUN_HOME="$(getent passwd "${RUN_USER}" | cut -d: -f6)"

if [[ ! -x "${REPO_DIR}/.venv/bin/nostalgiabox" ]]; then
  echo "error: ${REPO_DIR}/.venv/bin/nostalgiabox not found." >&2
  echo "Run ./scripts/install.sh first." >&2
  exit 1
fi

echo "==> Rendering service unit for user '${RUN_USER}'"
tmp="$(mktemp)"
sed \
  -e "s|__USER__|${RUN_USER}|g" \
  -e "s|__UID__|${RUN_UID}|g" \
  -e "s|__HOME__|${RUN_HOME}|g" \
  -e "s|__REPO_DIR__|${REPO_DIR}|g" \
  "${TEMPLATE}" > "${tmp}"

echo "==> Installing ${TARGET}"
sudo cp "${tmp}" "${TARGET}"
rm -f "${tmp}"

echo "==> Allowing '${RUN_USER}' to power off without a password (for the"
echo "    volume-down-past-zero shutdown)"
sudo tee /etc/sudoers.d/nostalgiabox-poweroff > /dev/null <<EOF
${RUN_USER} ALL=(root) NOPASSWD: /sbin/poweroff, /usr/sbin/poweroff, /sbin/shutdown, /usr/sbin/shutdown, /usr/bin/systemctl poweroff
EOF
sudo chmod 440 /etc/sudoers.d/nostalgiabox-poweroff

echo "==> Enabling and starting the service"
sudo systemctl daemon-reload
sudo systemctl enable nostalgiabox.service
sudo systemctl restart nostalgiabox.service

cat <<EOF

==> Service installed.

Handy commands:
  systemctl status nostalgiabox     # is it running?
  journalctl -u nostalgiabox -f     # live logs
  sudo systemctl stop nostalgiabox  # stop the TV
  sudo systemctl disable nostalgiabox   # don't start on boot
EOF
