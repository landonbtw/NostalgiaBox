"""Pick a USB partition to mount as the NostalgiaBox show drive.

The installer calls ``python -m nostalgiabox.usb`` and mounts whatever path it
prints. Selection is pure data so it can be tested without a Raspberry Pi:

* ignore the disk the operating system is running from
* ignore internal disks
* prefer a partition labeled ``NOSTALGIA``, ``NOSTALGIABOX``, or ``SHOWS``
* otherwise use the largest usable USB partition
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import AbstractSet, Iterable, List, Optional, Sequence

# Filesystems a kids' show drive is likely to use. Mac and Windows users are
# told to format as exFAT so episode files over 4 GB work on every machine.
USABLE_FILESYSTEMS = frozenset({
    "vfat",
    "exfat",
    "ntfs",
    "ntfs3",
    "ext2",
    "ext3",
    "ext4",
    "ext4dev",
    "btrfs",
    "xfs",
})

PREFERRED_LABELS = frozenset({"nostalgia", "nostalgiabox", "shows"})


@dataclass(frozen=True)
class BlockDevice:
    """One row from ``lsblk``, flattened so disks and partitions look the same."""

    name: str
    path: str
    type: str
    tran: str = ""
    fstype: str = ""
    label: str = ""
    size: int = 0
    pkname: str = ""


def choose_usb_partition(
    devices: Sequence[BlockDevice],
    *,
    exclude_disks: AbstractSet[str] = frozenset(),
) -> Optional[str]:
    """Return the ``/dev/...`` path of the USB partition to mount, if any."""
    excluded = {name for name in exclude_disks if name}
    usb_disks = {
        device.name
        for device in devices
        if device.type == "disk"
        and device.tran == "usb"
        and device.name not in excluded
    }
    candidates: List[BlockDevice] = []
    for device in devices:
        if device.type != "part" or not device.path:
            continue
        parent = device.pkname
        on_usb = device.tran == "usb" or parent in usb_disks
        if not on_usb:
            continue
        if device.name in excluded or parent in excluded:
            continue
        if device.fstype.lower() not in USABLE_FILESYSTEMS:
            continue
        candidates.append(device)
    if not candidates:
        return None

    def sort_key(device: BlockDevice) -> tuple:
        label = device.label.strip().lower()
        return (label in PREFERRED_LABELS, device.size, device.path)

    return max(candidates, key=sort_key).path


def flatten_lsblk(data: dict) -> List[BlockDevice]:
    """Flatten an ``lsblk -J`` document, inheriting ``tran`` from parent disks."""
    devices: List[BlockDevice] = []

    def walk(nodes: Iterable[dict], parent_tran: str = "", parent_name: str = "") -> None:
        for node in nodes:
            name = str(node.get("name") or "")
            node_type = str(node.get("type") or "")
            tran = str(node.get("tran") or parent_tran or "")
            pkname = str(node.get("pkname") or "")
            if not pkname and node_type != "disk":
                pkname = parent_name
            devices.append(
                BlockDevice(
                    name=name,
                    path=str(node.get("path") or ""),
                    type=node_type,
                    tran=tran,
                    fstype=str(node.get("fstype") or ""),
                    label=str(node.get("label") or ""),
                    size=_as_int(node.get("size")),
                    pkname=pkname,
                )
            )
            children = node.get("children") or []
            next_tran = tran if node_type == "disk" else parent_tran
            walk(children, next_tran, name or parent_name)

    walk(data.get("blockdevices") or [])
    return devices


def load_lsblk() -> dict:
    """Run ``lsblk`` and return its JSON document, or ``{}`` if that fails."""
    try:
        raw = subprocess.check_output(
            ["lsblk", "-J", "-b", "-o", "NAME,PATH,TRAN,TYPE,FSTYPE,LABEL,SIZE,PKNAME"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def root_disk_names() -> set[str]:
    """Disk and partition names that hold ``/``, so we never mount the OS drive."""
    try:
        source = subprocess.check_output(
            ["findmnt", "-n", "-o", "SOURCE", "/"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return set()
    source = source.splitlines()[0].strip() if source else ""
    if not source:
        return set()
    names = set()
    base = source.rsplit("/", 1)[-1]
    if base:
        names.add(base)
    try:
        pk = subprocess.check_output(
            ["lsblk", "-no", "PKNAME", source],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        pk = ""
    if pk:
        names.add(pk.splitlines()[0].strip())
    return {name for name in names if name}


def main() -> int:
    """Print the chosen device path, or nothing when no USB library drive exists."""
    chosen = choose_usb_partition(flatten_lsblk(load_lsblk()), exclude_disks=root_disk_names())
    if chosen:
        print(chosen)
    return 0


def _as_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
