"""Where each in-order channel left off.

Shuffle forgets on purpose: the next visit should be a different episode.
In-order playback is a series, so the episode and the position are written
here and read back after a channel change or a reboot.

The file lives under the XDG state directory (``~/.local/state/nostalgiabox/
playback.json`` unless ``XDG_STATE_HOME`` is set). A ``state_file`` line in
config.yaml can point somewhere else.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

STATE_VERSION = 1


def default_state_path() -> Path:
    """The playback bookmark file for this user."""
    base = os.environ.get("XDG_STATE_HOME")
    root = Path(base) if base else Path.home() / ".local" / "state"
    return root / "nostalgiabox" / "playback.json"


@dataclass
class ChannelBookmark:
    """One channel's saved place. ``episode`` is relative to the show folder."""

    episode: str = ""
    position: float = 0.0
    # Wall-clock start of an in-order broadcast schedule, so a reboot does not
    # jump the station back to episode 1.
    epoch: Optional[float] = None


class PlaybackState:
    """A small JSON file of :class:`ChannelBookmark` values, keyed by folder."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._channels: dict[str, ChannelBookmark] = {}

    @classmethod
    def load(cls, path: Path) -> "PlaybackState":
        state = cls(path)
        if not path.is_file():
            return state
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.warning("could not read playback state %s; starting fresh", path)
            return state
        channels = raw.get("channels") if isinstance(raw, dict) else None
        if not isinstance(channels, dict):
            return state
        for key, item in channels.items():
            if not isinstance(item, dict):
                continue
            epoch = item.get("epoch")
            try:
                position = float(item.get("position") or 0.0)
            except (TypeError, ValueError):
                position = 0.0
            try:
                epoch_f = float(epoch) if epoch is not None else None
            except (TypeError, ValueError):
                epoch_f = None
            state._channels[str(key)] = ChannelBookmark(
                episode=str(item.get("episode") or ""),
                position=max(0.0, position),
                epoch=epoch_f,
            )
        return state

    def get(self, channel_path: Path) -> Optional[ChannelBookmark]:
        return self._channels.get(_key(channel_path))

    def set(self, channel_path: Path, bookmark: ChannelBookmark) -> None:
        self._channels[_key(channel_path)] = bookmark

    def save(self) -> None:
        """Write the file atomically. A half-written bookmark must not stick."""
        payload = {
            "version": STATE_VERSION,
            "channels": {
                key: {
                    "episode": mark.episode,
                    "position": mark.position,
                    "epoch": mark.epoch,
                }
                for key, mark in self._channels.items()
            },
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            log.warning("could not save playback state %s", self.path, exc_info=True)


def _key(channel_path: Path) -> str:
    try:
        return str(channel_path.expanduser().resolve())
    except OSError:
        return str(channel_path)


__all__ = ["ChannelBookmark", "PlaybackState", "default_state_path"]
