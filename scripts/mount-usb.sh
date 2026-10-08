#!/usr/bin/env bash
#
# Mount a USB drive at /media/nostalgiabox-usb so NostalgiaBox can play shows
# from it. Safe to run more than once, and from any directory.
#
#   bash ~/NostalgiaBox/scripts/mount-usb.sh
#   bash ~/NostalgiaBox/scripts/mount-usb.sh --unmount
#   bash ~/NostalgiaBox/scripts/mount-usb.sh --wait 20
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MOUNTPOINT="${NOSTALGIABOX_USB_MOUNT:-/media/nostalgiabox-usb}"
ENV_FILE="/etc/nostalgiabox/usb.env"
WAIT_SECONDS=8
MODE="mount"

usage() {
  cat <<EOF
Mount a USB show drive at ${MOUNTPOINT}.

Usage:
  bash ${REPO_DIR}/scripts/mount-usb.sh [--wait SECONDS]
  bash ${REPO_DIR}/scripts/mount-usb.sh --unmount

This command works from any directory. It asks for your password when it
needs administrator rights.
EOF
}

# --help must work without root. Every other invocation re-runs as root with
# the original arguments (parsing them first would throw those arguments away).
if [[ "${EUID}" -ne 0 ]]; then
  for arg in "$@"; do
    case "${arg}" in
      --help|-h)
        usage
        exit 0
        ;;
    esac
  done
  exec sudo -- "$0" "$@"
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --unmount)
      MODE="unmount"
      shift
      ;;
    --unmount-if-gone)
      MODE="unmount-if-gone"
      shift
      ;;
    --wait)
      if [[ $# -lt 2 ]]; then
        echo "error: --wait needs a number of seconds" >&2
        exit 2
      fi
      WAIT_SECONDS="$2"
      shift 2
      ;;
    --wait=*)
      WAIT_SECONDS="${1#*=}"
      shift
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
fi
MOUNT_UID="${MOUNT_UID:-0}"
MOUNT_GID="${MOUNT_GID:-0}"

mkdir -p "${MOUNTPOINT}"

if [[ "${MODE}" == "unmount" || "${MODE}" == "unmount-if-gone" ]]; then
  if ! findmnt -n "${MOUNTPOINT}" >/dev/null 2>&1; then
    exit 0
  fi
  src="$(findmnt -n -o SOURCE "${MOUNTPOINT}" || true)"
  src="${src%%$'\n'*}"
  if [[ "${MODE}" == "unmount-if-gone" && -n "${src}" && -e "${src}" ]]; then
    exit 0
  fi
  if ! umount "${MOUNTPOINT}"; then
    umount -l "${MOUNTPOINT}" || true
  fi
  echo "Unmounted ${MOUNTPOINT}"
  exit 0
fi

if findmnt -n "${MOUNTPOINT}" >/dev/null 2>&1; then
  echo "USB drive already mounted at ${MOUNTPOINT}"
  exit 0
fi

PYTHON="${REPO_DIR}/.venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="$(command -v python3 || true)"
fi
if [[ -z "${PYTHON}" ]]; then
  echo "error: python3 is not installed." >&2
  exit 1
fi

export PYTHONPATH="${REPO_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

deadline=$((SECONDS + WAIT_SECONDS))
dev=""
while true; do
  dev="$("${PYTHON}" -m nostalgiabox.usb 2>/dev/null || true)"
  dev="${dev%%$'\n'*}"
  if [[ -n "${dev}" && -e "${dev}" ]]; then
    break
  fi
  dev=""
  if (( SECONDS >= deadline )); then
    echo "No USB drive found to mount at ${MOUNTPOINT}."
    echo "Plug in a USB drive, or copy shows to /media/nostalgiabox on the SD card."
    exit 0
  fi
  sleep 1
done

# The drive may already be mounted somewhere else (a desktop automounter).
# Bind it into the path NostalgiaBox looks at.
if findmnt -S "${dev}" >/dev/null 2>&1; then
  existing="$(findmnt -n -o TARGET -S "${dev}" || true)"
  existing="${existing%%$'\n'*}"
  if [[ -n "${existing}" && "${existing}" != "${MOUNTPOINT}" ]]; then
    mount --bind "${existing}" "${MOUNTPOINT}"
    echo "Using the USB drive already mounted at ${existing}"
    echo "Show folders are visible at ${MOUNTPOINT}"
    exit 0
  fi
fi

fstype="$(blkid -o value -s TYPE "${dev}" 2>/dev/null || true)"
mounted=0
case "${fstype}" in
  vfat|exfat|ntfs|ntfs3)
    if mount -o "uid=${MOUNT_UID},gid=${MOUNT_GID},umask=0022" "${dev}" "${MOUNTPOINT}"; then
      mounted=1
    fi
    ;;
esac
if [[ "${mounted}" -eq 0 ]]; then
  mount "${dev}" "${MOUNTPOINT}"
fi
echo "Mounted ${dev} (${fstype:-unknown filesystem}) at ${MOUNTPOINT}"
