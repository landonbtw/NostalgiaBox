"""``nostalgiabox --check``: a plain-English setup report.

Each section says what was found and, when something is wrong, the exact
command that fixes it. The exit code is 0 when at least one episode is ready
to play and the player tools are installed.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence, TextIO

from .channel import scan_episodes
from .config import (
    DEFAULT_MEDIA_ROOT,
    Config,
    ConfigError,
)

# Directories that belong to the program. Anything else full of videos was
# almost certainly dropped in the wrong place (see issue #33).
_PACKAGE_DIRS = frozenset({"input", "assets", "__pycache__"})


@dataclass(frozen=True)
class ServiceStatus:
    """systemd unit state. ``installed`` is false when the unit does not exist."""

    installed: bool
    active: str
    enabled: str


def probe_python_mpv() -> tuple[bool, str]:
    """Whether the Python mpv bindings can be imported."""
    try:
        import mpv  # type: ignore  # noqa: F401
    except Exception as exc:  # noqa: BLE001 - missing lib is the interesting case
        return False, str(exc)
    return True, "installed"


def probe_service() -> ServiceStatus:
    """Read the nostalgiabox systemd unit, if systemd is available."""
    if not shutil.which("systemctl"):
        return ServiceStatus(False, "unavailable", "unavailable")
    active = _systemctl("is-active")
    enabled = _systemctl("is-enabled")
    installed = enabled != "not-found"
    return ServiceStatus(installed, active, enabled)


def no_shows_advice(config: Config) -> str:
    """What to tell someone whose library has no channels yet."""
    root = config.media_root or DEFAULT_MEDIA_ROOT
    lines = [
        f"Put each show in its own folder inside {root}",
        'The folder name becomes the channel name. Example: "Dragon Tales/S01E01.mp4".',
    ]
    if config.usb_media_root is not None:
        lines.append(
            "Or put those show folders on a USB drive and plug it into the Pi. "
            f"NostalgiaBox looks for it at {config.usb_media_root}."
        )
    lines.append(
        "Shows do not go in the program folder (the folder that contains app.py)."
    )
    return "\n".join(lines)


def wait_for_shows(
    load: Callable[[], Config],
    sleep: Callable[[float], None],
    announce: Callable[[Config], None],
    *,
    interval: float = 5.0,
    remind_every: float = 30.0,
) -> Config:
    """Block until ``load`` returns a config that has at least one channel.

    ``announce`` is called immediately and again every ``remind_every`` seconds
    so a service log explains what the box is waiting for without flooding.
    """
    elapsed = 0.0
    next_reminder = 0.0
    while True:
        config = load()
        if config.channels:
            return config
        if elapsed >= next_reminder:
            announce(config)
            next_reminder = elapsed + remind_every
        sleep(interval)
        elapsed += interval


def misplaced_show_dirs(package_dir: Path, extensions: Sequence[str]) -> List[Path]:
    """Show folders a user dropped inside the Python package directory."""
    if not package_dir.is_dir():
        return []
    found: List[Path] = []
    try:
        children = list(package_dir.iterdir())
    except OSError:
        return []
    for child in children:
        if not child.is_dir() or child.name.startswith(".") or child.name in _PACKAGE_DIRS:
            continue
        if scan_episodes(child, extensions):
            found.append(child)
    found.sort(key=lambda path: path.name.lower())
    return found


def run_check(
    config: Config,
    config_path: Path,
    *,
    which: Optional[Callable[[str], Optional[str]]] = None,
    python_mpv: Optional[Callable[[], tuple[bool, str]]] = None,
    service: Optional[Callable[[], ServiceStatus]] = None,
    package_dir: Optional[Path] = None,
    mount_source: Optional[Callable[[Path], Optional[str]]] = None,
    out: Optional[TextIO] = None,
) -> int:
    """Print the setup report and return 0 when the box is ready to play."""
    # Resolved at call time so tests can replace the probe functions.
    if which is None:
        which = shutil.which
    if python_mpv is None:
        python_mpv = probe_python_mpv
    if service is None:
        service = probe_service
    if mount_source is None:
        mount_source = _mount_source
    sink = out or sys.stdout
    package = package_dir if package_dir is not None else Path(__file__).resolve().parent
    problems: List[str] = []

    def emit(text: str = "") -> None:
        print(text, file=sink)

    emit("NostalgiaBox check")
    emit("==================")
    emit()
    emit("Config")
    emit(f"  OK   {config_path}")
    emit()

    _report_library(config, mount_source, emit, problems)
    emit()
    total = _report_channels(config, emit, problems)
    emit()
    _report_loose_files(config, total, emit, problems)
    _report_misplaced(config, package, emit, problems)
    _report_tools(which, python_mpv, emit, problems)
    emit()
    status = service()
    _report_service(status, emit)
    emit()
    _report_summary(problems, total, status, emit)
    return 0 if not problems else 1


def report_config_error(exc: ConfigError, *, out: Optional[TextIO] = None) -> int:
    """Report a missing or unreadable config file."""
    sink = out or sys.stdout
    print("NostalgiaBox check", file=sink)
    print("==================", file=sink)
    print(file=sink)
    print("Config", file=sink)
    lines = str(exc).splitlines() or ["configuration error"]
    print(f"  FIX  {lines[0]}", file=sink)
    for line in lines[1:]:
        print(f"       {line}", file=sink)
    print(file=sink)
    print("Not ready yet. Fix the config file, then run: nostalgiabox --check", file=sink)
    return 2


def _report_library(config, mount_source, emit, problems) -> None:
    emit("Shows")
    if config.media_source == "channels":
        emit("  OK   Using the channel list in the config file.")
        emit("       Folder discovery is off while that list is present.")
        if config.media_root is not None:
            emit(f"       media_root is set to {config.media_root} and is not used for discovery.")
        return

    active = config.active_media_root
    if config.media_source == "usb" and active is not None:
        source = mount_source(active)
        if source:
            emit(f"  OK   Using the USB drive at {active}")
            emit(f"       (device {source}).")
        else:
            emit(f"  OK   Using show folders in {active}")
        if config.media_root is not None:
            emit(f"       The SD card folder {config.media_root} is used when this drive is unplugged.")
        return

    # SD card (or a USB path that was the only root and has a problem).
    if config.media_error:
        emit(f"  FIX  {config.media_error}")
        root = config.media_root or active
        emit("       The installer creates this folder. From any directory, run:")
        emit("         bash ~/NostalgiaBox/scripts/install.sh")
        if root is not None:
            emit("       Or create it yourself:")
            emit(f"         sudo mkdir -p {_quote(root)}")
            emit(f"         sudo chown \"$USER\":\"$USER\" {_quote(root)}")
        problems.append("media")
        return

    if active is None:
        emit("  FIX  No media folder is configured.")
        emit("       Add this line to config.yaml:")
        emit("         media_root: /media/nostalgiabox")
        problems.append("media")
        return

    emit(f"  OK   Using the SD card folder {active}")
    if config.usb_media_root is not None:
        usb_source = mount_source(config.usb_media_root)
        if usb_source:
            emit(f"       A USB drive is mounted at {config.usb_media_root} ({usb_source})")
            emit("       but it has no show folders with videos, so it was left unused.")
        else:
            emit(f"       No USB show drive is mounted at {config.usb_media_root}.")
            emit("       Plug one in to use it, or keep shows in the SD card folder above.")


def _report_channels(config: Config, emit, problems) -> int:
    emit("Channels")
    if not config.channels:
        if config.media_error:
            emit("  FIX  No channels, because the media folder could not be read.")
        else:
            emit("  FIX  No show folders found.")
            for line in no_shows_advice(config).splitlines():
                emit(f"       {line}")
        problems.append("episodes")
        return 0

    rows = []
    for channel in config.channels:
        episodes = scan_episodes(
            channel.path,
            config.video_extensions,
            recursive=config.scan_recursive,
            exclude=channel.exclude,
            exclude_seasons=channel.exclude_seasons,
        )
        rows.append((channel, len(episodes), channel.path.exists()))
    total = sum(count for _, count, _ in rows)
    missing_paths = sum(1 for _, _, exists in rows if not exists)

    for channel, count, exists in rows:
        if not exists:
            flag = "FIX"
            note = "folder does not exist"
        elif count == 0:
            # One empty channel does not stop the others from playing.
            flag = "FIX" if total == 0 else "!!"
            note = "no video files in this folder"
        else:
            flag = "OK"
            note = ""
        suffix = f"  ({note})" if note else ""
        label = "episode" if count == 1 else "episodes"
        emit(
            f"  {flag:<3}  CH {channel.number:>3}  {channel.name:<28} "
            f"{count:>4} {label}{suffix}"
        )
        emit(f"         {channel.path}")

    if missing_paths and config.media_source == "channels":
        emit("       Those folders are listed in config.yaml and were not found.")
        emit("       Easiest fix: delete the whole channels: list from config.yaml")
        emit("       and keep this line (it discovers one channel per folder):")
        emit("         media_root: /media/nostalgiabox")
        emit("       Then put one folder per show in /media/nostalgiabox.")
        emit('       Folder names can contain spaces. "Dragon Tales" is a fine name.')

    if total == 0:
        problems.append("episodes")
        if config.media_source != "channels":
            emit("       A folder is only a channel when it contains video files")
            emit("       such as .mp4 or .mkv. Season subfolders are fine.")
    else:
        word = "episode" if total == 1 else "episodes"
        emit(f"       {total} {word} in {len(config.channels)} channels.")
    return total


def _loose_roots(config: Config) -> List[Path]:
    """Library folders whose top-level video files would be skipped."""
    roots: List[Path] = []
    if config.media_source != "channels" and config.active_media_root is not None:
        roots.append(config.active_media_root)
    usb = config.usb_media_root
    if usb is not None and usb not in roots and config.media_source != "usb" and usb.is_dir():
        roots.append(usb)
    return roots


def _report_loose_files(config: Config, total: int, emit, problems) -> None:
    """Video files sitting in a library root never become a channel."""
    reported = False
    blocks_playback = False
    for root in _loose_roots(config):
        loose = scan_episodes(root, config.video_extensions, recursive=False)
        if not loose:
            continue
        if not reported:
            emit("Loose video files")
            reported = True
        # Loose files are the whole library only when nothing else can play.
        flag = "FIX" if total == 0 else "!!"
        emit(f"  {flag:<3}  {len(loose)} video file(s) are directly inside {root}")
        emit("       A channel is a folder, so these files are skipped.")
        emit("       Move them into a show folder. Example:")
        emit(f"         mkdir {_quote(root / 'Dragon Tales')}")
        names = " ".join(_quote(path) for path in loose[:5])
        emit(f"         mv {names} {_quote(root / 'Dragon Tales')}/")
        if len(loose) > 5:
            emit(f"       ({len(loose) - 5} more files not listed)")
        if total == 0:
            blocks_playback = True
    if blocks_playback:
        problems.append("loose")
    if reported:
        emit()


def _report_misplaced(config: Config, package: Path, emit, problems) -> None:
    found = misplaced_show_dirs(package, config.video_extensions)
    if not found:
        return
    emit("Shows in the program folder")
    emit(f"  FIX  Video folders were found inside {package}")
    emit("       That directory is the NostalgiaBox program, not the video library.")
    dest = config.media_root or DEFAULT_MEDIA_ROOT
    for folder in found:
        count = len(scan_episodes(folder, config.video_extensions))
        emit(f"       {folder.name} ({count} episodes)")
        emit(f"         mv {_quote(folder)} {_quote(dest)}/")
    emit(f"       Then run: nostalgiabox --check")
    problems.append("misplaced")
    emit()


def _report_tools(which, python_mpv, emit, problems) -> None:
    emit("Player")
    tool_ok = True
    for name, hint in (
        ("mpv", "sudo apt-get install -y mpv"),
        ("ffmpeg", "sudo apt-get install -y ffmpeg"),
    ):
        path = which(name)
        if path:
            emit(f"  OK   {name} ({path})")
        else:
            tool_ok = False
            emit(f"  FIX  {name} is not installed.")
            emit(f"       {hint}")
            emit("       Or re-run: bash ~/NostalgiaBox/scripts/install.sh")
    ok, detail = python_mpv()
    if ok:
        emit("  OK   Python video library (python-mpv)")
    else:
        tool_ok = False
        emit("  FIX  The Python video library (python-mpv) is not installed.")
        emit(f"       ({detail})")
        emit("       Re-run: bash ~/NostalgiaBox/scripts/install.sh")
    if not tool_ok:
        problems.append("tools")


def _report_service(status: ServiceStatus, emit) -> None:
    emit("Boot-to-TV service")
    if status.active == "unavailable":
        emit("  --   systemd is not available on this computer.")
        emit("       On the Raspberry Pi, the installer enables the service.")
        return
    if not status.installed:
        emit("  FIX  The nostalgiabox service is not installed.")
        emit("       From any folder, run:")
        emit("         bash ~/NostalgiaBox/scripts/install.sh")
        return
    if status.active == "active" and status.enabled == "enabled":
        emit("  OK   Running, and it starts when the Pi is powered on.")
        return
    if status.active == "active":
        emit("  FIX  It is running now, but it will not start on power-up.")
        emit("       sudo systemctl enable nostalgiabox")
        return
    if status.enabled == "enabled":
        emit(f"  FIX  It is enabled for boot, but right now it is {status.active}.")
        emit("       sudo systemctl restart nostalgiabox")
        emit("       journalctl -u nostalgiabox -n 50 --no-pager")
        return
    emit(f"  FIX  The service is {status.active} and boot is {status.enabled}.")
    emit("       bash ~/NostalgiaBox/scripts/install.sh")


def _report_summary(problems, total, status: ServiceStatus, emit) -> None:
    if problems:
        emit("Not ready yet. Fix the lines marked FIX above, then run: nostalgiabox --check")
        return
    if status.active == "active" and status.enabled == "enabled":
        emit("Ready. The TV should be playing on the HDMI port.")
        if total:
            emit("If the screen is blank, run: sudo systemctl restart nostalgiabox")
            emit("To watch the log: journalctl -u nostalgiabox -f")
        return
    if status.active == "unavailable":
        emit("The shows and the player tools look ready.")
        emit("This computer has no systemd, so boot-to-TV can only be confirmed on the Pi")
        emit("after: bash ~/NostalgiaBox/scripts/install.sh")
        return
    emit("The shows are ready. The TV program is not running right now.")
    if not status.installed:
        emit("Turn on boot-to-TV with: bash ~/NostalgiaBox/scripts/install.sh")
    else:
        emit("Start it with: sudo systemctl restart nostalgiabox")
        emit("To watch the log: journalctl -u nostalgiabox -f")


def _systemctl(verb: str) -> str:
    try:
        result = subprocess.run(
            ["systemctl", verb, "nostalgiabox"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return "unknown"
    text = (result.stdout or result.stderr or "").strip().splitlines()
    return text[0].strip() if text else "unknown"


def _mount_source(path: Path) -> Optional[str]:
    if not shutil.which("findmnt"):
        return None
    try:
        result = subprocess.run(
            ["findmnt", "-n", "-o", "SOURCE", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    return text.splitlines()[0].strip() if text else None


def _quote(path: Path) -> str:
    import shlex

    return shlex.quote(str(path))
