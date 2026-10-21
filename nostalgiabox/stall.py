"""Detect a frozen picture and remember the files that cause it.

The player already skips a file that reports an error, and it rolls to the
next episode at a real end. A freeze is neither of those: the last frame stays
on screen, the sound stops, and nothing asks for the next episode. This module
notices that.

Two shapes count as a stall, after a short grace for the file to open:

* The playback clock stops moving. The episode is stuck at a timestamp; it is
  not still playing behind a frozen image.
* The clock keeps moving, but a frame timecode that was changing has stopped.
  The player thinks it is playing and the picture is stuck.

The first time, the app seeks past that spot. If the same play freezes again,
it skips to the next episode. A file that freezes on several plays is flagged
and skipped the next time it is chosen. Every event is one line in
``problem-files.log``, next to the in-order bookmark file, and the same line
is written to the service log.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

STATE_VERSION = 1

# A move smaller than this is noise (a property read between frames). Real
# playback passes it within a fraction of a second.
POSITION_EPSILON = 0.25

# Keys on mpv's ``video-frame-info`` that name the frame on screen. A value
# that never changes is ignored; only a timecode that has already moved can
# prove the picture later froze.
_PICTURE_KEYS = (
    "smpte-timecode",
    "smpte_timecode",
    "gop-timecode",
    "gop_timecode",
)


@dataclass(frozen=True)
class PlaybackSample:
    """One look at the player. ``picture`` is a frame id, or None if unknown."""

    position: Optional[float] = None
    audio_position: Optional[float] = None
    picture: Optional[str] = None
    paused: bool = False
    idle: bool = False
    ended: bool = False
    failed: bool = False


@dataclass(frozen=True)
class Stall:
    """A freeze the app should recover from.

    ``action`` is ``seek`` (jump ahead once) or ``skip`` (give up on this play).
    ``kind`` is ``timestamp`` (clock stopped), ``picture`` (clock moving, frame
    stuck), or ``player`` (paused, idle, or not answering).
    """

    path: Path
    position: Optional[float]
    action: str
    kind: str
    detail: str


def format_timestamp(seconds: float) -> str:
    """``754`` -> ``12:34``. Hours are included only past 60 minutes."""
    total = int(max(0.0, seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def picture_token(info: object) -> Optional[str]:
    """A frame timecode from an mpv ``video-frame-info`` value, if it has one."""
    if not isinstance(info, dict):
        return None
    for key in _PICTURE_KEYS:
        value = info.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def problem_directory(state_file: Optional[Path] = None) -> Path:
    """Folder that holds ``problem-files.log`` (beside the bookmark file)."""
    if state_file is not None:
        return Path(state_file).expanduser().parent
    base = os.environ.get("XDG_STATE_HOME")
    root = Path(base) if base else Path.home() / ".local" / "state"
    return root / "nostalgiabox"


def format_problem_line(
    path: Path,
    position: Optional[float],
    message: str,
    channel: str,
    *,
    now: Optional[datetime] = None,
) -> str:
    """One grep-friendly log line. ``channel`` may be empty."""
    stamp = now or datetime.now(timezone.utc)
    when = stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    where = ""
    if position is not None:
        where = f" at {format_timestamp(position)} ({position:.1f}s)"
    suffix = f"; {channel}" if channel else ""
    return f"{when} problem file: {path}{where}; {message}{suffix}"


class StallWatchdog:
    """Decide when the current episode has stopped making progress.

    Call :meth:`arm` when a file starts (or the picture cuts to a new one) and
    :meth:`observe` on each pass of the main loop. The returned :class:`Stall`
    is latched until :meth:`note_seek` or :meth:`arm`, so a stuck file reports
    once per recovery attempt.
    """

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        grace: float = 8.0,
        epsilon: float = POSITION_EPSILON,
    ) -> None:
        self.timeout = timeout
        self.grace = grace
        self.epsilon = epsilon
        self.path: Optional[Path] = None
        self._grace_until = 0.0
        self._last_progress_at = 0.0
        self._baseline_pos: Optional[float] = None
        self._baseline_audio: Optional[float] = None
        self._last_picture: Optional[str] = None
        self._picture_moves = False
        self._last_good_position: Optional[float] = None
        self._attempts = 0
        self._reported = False

    def arm(self, path: Path, now: float) -> None:
        """Start watching ``path``. The attempt count resets."""
        self.path = path
        self._grace_until = now + self.grace
        self._last_progress_at = now
        self._baseline_pos = None
        self._baseline_audio = None
        self._last_picture = None
        self._picture_moves = False
        self._last_good_position = None
        self._attempts = 0
        self._reported = False

    def disarm(self) -> None:
        """Standby, no-signal, or shutdown: nothing is supposed to be moving."""
        self.path = None
        self._reported = False

    def note_seek(self, now: float) -> None:
        """A seek was just issued. Keep the attempt count; allow time to land."""
        self._grace_until = now + self.grace
        self._last_progress_at = now
        self._baseline_pos = None
        self._baseline_audio = None
        self._last_picture = None
        self._picture_moves = False
        self._reported = False

    def observe(self, sample: PlaybackSample, now: float) -> Optional[Stall]:
        """Return a stall once the clock (or the picture) has been still too long."""
        if self.path is None or self._reported:
            return None
        if sample.ended:
            # A real end of file is the player's job. Don't also skip.
            self._last_progress_at = now
            self._absorb(sample)
            return None

        clock_moved, picture_moved, picture_stuck = self._signals(sample)
        self._absorb(sample)
        if self._healthy(sample, clock_moved, picture_moved, picture_stuck):
            self._last_progress_at = now
            return None
        if now < self._grace_until:
            return None
        if now - self._last_progress_at < self.timeout:
            return None

        self._reported = True
        self._attempts += 1
        position = sample.position if sample.position is not None else self._last_good_position
        kind, detail = self._classify(sample, clock_moved, picture_stuck)
        # No clock means there is nowhere to seek. Idle or a hard failure
        # likewise: jump ahead in a player that isn't running.
        if self._attempts >= 2 or position is None or sample.failed or sample.idle:
            action = "skip"
        else:
            action = "seek"
        return Stall(self.path, position, action, kind, detail)

    def _signals(self, sample: PlaybackSample) -> tuple[bool, bool, bool]:
        clock_moved = self._advanced(self._baseline_pos, sample.position) or self._advanced(
            self._baseline_audio, sample.audio_position
        )
        picture_moved = False
        picture_stuck = False
        if sample.picture is not None and self._last_picture is not None:
            if sample.picture != self._last_picture:
                picture_moved = True
            elif self._picture_moves:
                picture_stuck = True
        return clock_moved, picture_moved, picture_stuck

    def _advanced(self, baseline: Optional[float], value: Optional[float]) -> bool:
        """True when ``value`` has moved far enough from a known baseline.

        The first reading only establishes the baseline. A file that opens
        already frozen must not look like progress.
        """
        if value is None or baseline is None:
            return False
        if value > baseline + self.epsilon:
            return True
        if value < baseline - 1.0:
            return True
        return False

    def _absorb(self, sample: PlaybackSample) -> None:
        if sample.position is not None:
            if self._baseline_pos is None or self._advanced(self._baseline_pos, sample.position):
                self._baseline_pos = sample.position
            self._last_good_position = sample.position
        if sample.audio_position is not None:
            if self._baseline_audio is None or self._advanced(self._baseline_audio, sample.audio_position):
                self._baseline_audio = sample.audio_position
        if sample.picture is not None:
            if self._last_picture is not None and sample.picture != self._last_picture:
                self._picture_moves = True
            self._last_picture = sample.picture

    def _healthy(
        self,
        sample: PlaybackSample,
        clock_moved: bool,
        picture_moved: bool,
        picture_stuck: bool,
    ) -> bool:
        if sample.failed:
            return False
        # Timecode was changing and then stuck while the clock ran: the image
        # is frozen even though the player still says it is playing.
        if self._picture_moves and picture_stuck and clock_moved:
            return False
        if picture_moved or clock_moved:
            return True
        return False

    def _classify(
        self,
        sample: PlaybackSample,
        clock_moved: bool,
        picture_stuck: bool,
    ) -> tuple[str, str]:
        if sample.failed or sample.idle or (sample.paused and not clock_moved):
            return "player", "player stopped responding"
        if self._picture_moves and picture_stuck and clock_moved:
            return "picture", "playback clock still moving but the picture is frozen"
        return "timestamp", "playback position stopped advancing (stuck at this timestamp)"


@dataclass
class _FileRecord:
    stalls: int = 0
    last_position: Optional[float] = None


class ProblemLog:
    """Append-only text log plus a small JSON count of freezes per file."""

    def __init__(self, directory: Path, *, flag_after: int = 2) -> None:
        self.directory = directory
        self.log_path = directory / "problem-files.log"
        self.state_path = directory / "problem-files.json"
        self.flag_after = max(1, int(flag_after))
        self._files: dict[str, _FileRecord] = {}
        self._load()

    def stalls(self, path: Path) -> int:
        record = self._files.get(_key(path))
        return record.stalls if record is not None else 0

    def is_flagged(self, path: Path) -> bool:
        """True when this file has frozen often enough to skip on sight."""
        return self.stalls(path) >= self.flag_after

    def note_stall(
        self,
        path: Path,
        position: Optional[float],
        message: str,
        channel: str,
    ) -> bool:
        """Count one freeze, log it, and return whether the file is now flagged."""
        key = _key(path)
        record = self._files.get(key)
        if record is None:
            record = _FileRecord()
            self._files[key] = record
        record.stalls += 1
        if position is not None:
            record.last_position = position
        self._save()
        self.write(path, position, message, channel)
        return record.stalls >= self.flag_after

    def write(self, path: Path, position: Optional[float], message: str, channel: str) -> None:
        """Append one line and mirror it to the service log."""
        line = format_problem_line(path, position, message, channel)
        log.warning("%s", line)
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            log.warning("could not append %s", self.log_path, exc_info=True)

    def _load(self) -> None:
        if not self.state_path.is_file():
            return
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.warning("could not read %s; starting the problem-file list fresh", self.state_path)
            return
        files = raw.get("files") if isinstance(raw, dict) else None
        if not isinstance(files, dict):
            return
        for key, item in files.items():
            if not isinstance(item, dict):
                continue
            try:
                stalls = int(item.get("stalls") or 0)
            except (TypeError, ValueError):
                stalls = 0
            position = item.get("last_position")
            try:
                last = float(position) if position is not None else None
            except (TypeError, ValueError):
                last = None
            self._files[str(key)] = _FileRecord(stalls=max(0, stalls), last_position=last)

    def _save(self) -> None:
        payload = {
            "version": STATE_VERSION,
            "files": {
                key: {"stalls": record.stalls, "last_position": record.last_position}
                for key, record in self._files.items()
            },
        }
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            tmp.replace(self.state_path)
        except OSError:
            log.warning("could not save %s", self.state_path, exc_info=True)


def _key(path: Path) -> str:
    try:
        return str(path.expanduser().resolve())
    except OSError:
        return str(path)


__all__ = [
    "PlaybackSample",
    "Stall",
    "StallWatchdog",
    "ProblemLog",
    "format_timestamp",
    "format_problem_line",
    "picture_token",
    "problem_directory",
    "POSITION_EPSILON",
]
