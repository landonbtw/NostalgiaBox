"""USB partition selection, without a real drive."""

from nostalgiabox.usb import BlockDevice, choose_usb_partition, flatten_lsblk


def _disk(name, tran):
    return BlockDevice(name, f"/dev/{name}", "disk", tran=tran)


def _part(name, parent, fstype, *, label="", size=1, tran=""):
    return BlockDevice(
        name,
        f"/dev/{name}",
        "part",
        tran=tran,
        fstype=fstype,
        label=label,
        size=size,
        pkname=parent,
    )


def test_picks_usb_partition_and_ignores_the_sd_card():
    devices = [
        _disk("mmcblk0", "mmc"),
        _part("mmcblk0p2", "mmcblk0", "ext4", size=1000),
        _disk("sda", "usb"),
        _part("sda1", "sda", "exfat", size=50),
    ]
    chosen = choose_usb_partition(devices, exclude_disks={"mmcblk0", "mmcblk0p2"})
    assert chosen == "/dev/sda1"


def test_labeled_show_drive_beats_a_larger_usb_disk():
    devices = [
        _disk("sda", "usb"),
        _disk("sdb", "usb"),
        _part("sda1", "sda", "exfat", label="BACKUP", size=999),
        _part("sdb1", "sdb", "vfat", label="NOSTALGIA", size=10),
    ]
    assert choose_usb_partition(devices) == "/dev/sdb1"


def test_internal_disks_and_unusable_filesystems_are_ignored():
    devices = [
        _disk("nvme0n1", "nvme"),
        _part("nvme0n1p1", "nvme0n1", "ext4", size=100),
        _disk("sda", "usb"),
        _part("sda1", "sda", "swap", size=100),
    ]
    assert choose_usb_partition(devices) is None


def test_os_disk_is_excluded_even_when_it_is_usb():
    devices = [
        _disk("sda", "usb"),
        _disk("sdb", "usb"),
        _part("sda2", "sda", "ext4", size=500),
        _part("sdb1", "sdb", "ext4", label="shows", size=20),
    ]
    chosen = choose_usb_partition(devices, exclude_disks={"sda", "sda2"})
    assert chosen == "/dev/sdb1"


def test_live_picker_does_not_return_the_os_disk():
    """If lsblk works here, the chosen device must not be the disk mounted at /."""
    from nostalgiabox.usb import flatten_lsblk, load_lsblk, root_disk_names

    chosen = choose_usb_partition(
        flatten_lsblk(load_lsblk()),
        exclude_disks=root_disk_names(),
    )
    if not chosen:
        return
    excluded = root_disk_names()
    name = chosen.rsplit("/", 1)[-1]
    assert name not in excluded
    # A partition's parent disk (sda1 -> sda, mmcblk0p2 -> mmcblk0) is excluded too.
    for disk in excluded:
        assert not name.startswith(disk)


def test_flatten_lsblk_inherits_usb_transport():
    data = {
        "blockdevices": [
            {
                "name": "sda",
                "path": "/dev/sda",
                "tran": "usb",
                "type": "disk",
                "size": 100,
                "children": [
                    {
                        "name": "sda1",
                        "path": "/dev/sda1",
                        "type": "part",
                        "fstype": "exfat",
                        "label": "Shows",
                        "size": "90",
                    }
                ],
            }
        ]
    }
    devices = flatten_lsblk(data)
    part = next(device for device in devices if device.name == "sda1")
    assert part.tran == "usb"
    assert part.pkname == "sda"
    assert part.size == 90
    assert choose_usb_partition(devices) == "/dev/sda1"
