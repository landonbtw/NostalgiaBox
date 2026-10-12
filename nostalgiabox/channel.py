"""Channels: the folders of episodes and how they decide what to play.

A :class:`Channel` wraps one show (a folder of episode files) and knows how to
answer two questions:

* "I just tuned in - what should I play?" (:meth:`Channel.tune_in`)
* "The episode ended - what's next?" (:meth:`Channel.advance`)

The answer depends on the configured ``tune_in`` mode (see ``config.py``):
random, resume, or broadcast. :class:`ChannelLineup` holds all the channels and
provides the up/down/by-number navigation a remote needs.
"""

from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import AbstractSet, Dict, List, Optional, Sequence

# Split a path into text and integer chunks so "Ep 2" sorts before "Ep 10".
_NATURAL_SPLIT = re.compile(r"(\d+)")

# Patterns for pulling a season number out of a file/folder path.
_SEASON_PATTERNS = (
    re.compile(r"s(\d{1,2})[ ._-]?e\d{1,3}", re.IGNORECASE),   # S06E01, s6e1
    re.compile(r"\bseason[ ._-]*(\d{1,2})\b", re.IGNORECASE),  # Season 6
    re.compile(r"\b(\d{1,2})x\d{1,3}\b"),                       # 6x01
)

from .config import ChannelConfig, Config
from .playback_state import ChannelBookmark, PlaybackState, default_state_path
from .playlist import ShuffleBag
from .probe import DEFAULT_EPISODE_SECONDS, probe_duration

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlayRequest:
    """An instruction to the player: play ``path`` starting at ``start`` sec."""

    path: Path
    start: float = 0.0


def detect_season(text: str) -> Optional[int]:
    """Best-effort extraction of a season number from a path/filename."""
    for pattern in _SEASON_PATTERNS:
        match = pattern.search(text)
        if match:
            return int(match.group(1))
    return None


def natural_sort_key(text: str) -> tuple:
    """Sort key that compares numbers by value, not as letters.

    ``Ep 2`` comes before ``Ep 10``. ``101``, ``102``, ``103``, ``S01E02``,
    ``S01E10``, and ``1x02`` do the same. Season folders (``Season 1``,
    ``Season 2``, ``Season 10``) sort in season order because the whole
    relative path is compared, not just the filename.
    """
    parts: list[tuple] = []
    for piece in _NATURAL_SPLIT.split(text.lower()):
        if not piece:
            continue
        if piece.isdigit():
            parts.append((0, int(piece)))
        else:
            parts.append((1, piece))
    return tuple(parts)


def episode_rel(root: Path, path: Path) -> str:
    """Path of an episode relative to its show folder, using ``/`` separators."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def scan_episodes(
    root: Path,
    extensions: Sequence[str],
    *,
    recursive: bool = True,
    exclude: Sequence[str] = (),
    exclude_seasons: AbstractSet[int] = frozenset(),
) -> List[Path]:
    """Return a sorted list of episode files under ``root``.

    Sorting is natural (``Ep 2`` before ``Ep 10``, ``Season 1`` before
    ``Season 2``) so in-order playback follows the series. Hidden files and
    typical sidecar files are ignored.

    ``exclude`` is a list of case-insensitive glob patterns; any episode whose
    relative path or filename matches one is dropped. ``exclude_seasons`` drops
    episodes whose detected season number is in the set.
    """
    if not root.exists():
        log.warning("channel folder does not exist: %s", root)
        return []
    exts = {e.lower() for e in extensions}
    patterns = [p.lower() for p in exclude]
    walker = root.rglob("*") if recursive else root.glob("*")
    episodes = [
        p
        for p in walker
        if p.is_file()
        and p.suffix.lower() in exts
        and not p.name.startswith(".")
        and not _is_excluded(p, root, patterns, exclude_seasons)
    ]
    episodes.sort(key=lambda p: natural_sort_key(episode_rel(root, p)))
    return episodes


def _is_excluded(
    path: Path,
    root: Path,
    patterns: Sequence[str],
    exclude_seasons: AbstractSet[int],
) -> bool:
    import fnmatch

    try:
        rel = path.relative_to(root).as_posix().lower()
    except ValueError:  # pragma: no cover - path always under root here
        rel = path.name.lower()
    name = path.name.lower()
    for pat in patterns:
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat):
            return True
    if exclude_seasons:
        season = detect_season(rel)
        if season is not None and season in exclude_seasons:
            return True
    return False


class BroadcastSchedule:
    """A never-ending running order for a channel.

    Given episode durations and a fixed start epoch, it can report exactly what
    "would be airing" at any wall-clock moment - the illusion that the station
    kept broadcasting while nobody was watching. Shuffle mode uses one shuffled
    order that loops forever. In-order mode uses the episode list as given
    (natural filename order) and loops the same way.
    """

    def __init__(
        self,
        episodes: Sequence[Path],
        durations: Sequence[float],
        *,
        epoch: float,
        rng: random.Random,
        in_order: bool = False,
    ) -> None:
        if len(episodes) != len(durations):
            raise ValueError("episodes and durations must be the same length")
        order = list(range(len(episodes)))
        if not in_order:
            rng.shuffle(order)
        self._episodes = [episodes[i] for i in order]
        self._durations = [max(1.0, float(durations[i])) for i in order]
        self._epoch = epoch
        self._cycle = sum(self._durations)

    def at(self, when: float) -> PlayRequest:
        """What is airing at wall-clock time ``when`` (and how far into it)."""
        elapsed = (when - self._epoch) % self._cycle
        for path, dur in zip(self._episodes, self._durations):
            if elapsed < dur:
                return PlayRequest(path=path, start=elapsed)
            elapsed -= dur
        # Floating point rounding safety net.
        return PlayRequest(path=self._episodes[-1], start=0.0)


class Channel:
    """A single TV channel backed by a folder of episodes."""

    def __init__(
        self,
        config: ChannelConfig,
        episodes: Sequence[Path],
        *,
        tune_in: str = "random",
        start_offset_min: float = 0.0,
        start_offset_max: Optional[float] = None,
        rng: Optional[random.Random] = None,
        bookmark: Optional[ChannelBookmark] = None,
    ) -> None:
        self.config = config
        self.episodes: List[Path] = list(episodes)
        self.tune_in_mode = tune_in
        # Start each episode a random number of seconds in (within this range) so
        # the picture appears already "in the show" and channel switches land at
        # varied points instead of always the same spot.
        self.start_offset_min = max(0.0, start_offset_min)
        self.start_offset_max = (
            self.start_offset_min
            if start_offset_max is None
            else max(self.start_offset_min, start_offset_max)
        )
        self._rng = rng or random.Random()
        self._in_order = config.order == "in_order"
        # The shuffle bag is only the shuffle. In-order playback walks
        # ``episodes`` from ``_cursor`` and does not draw from the bag.
        self._bag: Optional[ShuffleBag[Path]] = (
            ShuffleBag(self.episodes, self._rng)
            if self.episodes and not self._in_order
            else None
        )
        # Where this channel left off. Shuffle+resume keeps it in memory.
        # In-order restores it from the bookmark file.
        self._cursor = 0
        self._resume_path: Optional[Path] = None
        self._resume_position: float = 0.0
        self._saved_epoch: Optional[float] = None
        # Set once a broadcast schedule exists, so it can be written out.
        self.broadcast_epoch: Optional[float] = None
        # Broadcast schedule (built lazily on first use in "broadcast" mode).
        self._broadcast: Optional[BroadcastSchedule] = None
        if bookmark is not None and self._in_order:
            self._saved_epoch = bookmark.epoch
            self._restore(bookmark)

    # -- identity -----------------------------------------------------------
    @property
    def number(self) -> int:
        return self.config.number

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def is_empty(self) -> bool:
        return not self.episodes

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Channel {self.number} {self.name!r} ({len(self.episodes)} eps)>"

    # -- playback selection -------------------------------------------------
    def _next_shuffled(self) -> PlayRequest:
        """Pick the next shuffle-bag episode.

        This is the default next-episode choice: one draw from the bag, started
        a few seconds in. In-order channels never call it.
        """
        assert self._bag is not None
        if self.start_offset_max > self.start_offset_min:
            start = self._rng.uniform(self.start_offset_min, self.start_offset_max)
        else:
            start = self.start_offset_min
        return PlayRequest(path=self._bag.next(), start=start)

    def _current_in_order(self) -> PlayRequest:
        """The saved episode, from the saved spot. New episodes start at 0.

        ``start_offset`` is a shuffle feeling (you tuned in late). A series
        played in order starts at the beginning, or where the viewer paused.
        """
        path = self.episodes[self._cursor]
        if self._resume_path == path:
            start = self._resume_position
        else:
            self._resume_path = path
            self._resume_position = 0.0
            start = 0.0
        return PlayRequest(path=path, start=start)

    def _advance_in_order(self) -> PlayRequest:
        """The next file in natural order, wrapping to the first at the end."""
        self._cursor = (self._cursor + 1) % len(self.episodes)
        self._resume_position = 0.0
        self._resume_path = self.episodes[self._cursor]
        return PlayRequest(path=self._resume_path, start=0.0)

    def tune_in(self, *, now: Optional[float] = None) -> Optional[PlayRequest]:
        """Decide what to play the instant a viewer switches to this channel."""
        if self.is_empty:
            return None
        now = time.time() if now is None else now

        if self.tune_in_mode == "broadcast":
            epoch = now
            if self._in_order and self._saved_epoch is not None:
                epoch = self._saved_epoch
            elif self._in_order:
                # First time this series becomes a station: remember the epoch
                # so a reboot continues the same schedule.
                self._saved_epoch = now
                epoch = now
            schedule = self._ensure_broadcast(epoch=epoch)
            if schedule is not None:
                return schedule.at(now)
            # Fall through if the schedule could not be built.

        if self._in_order:
            # random and resume both continue the series. The difference
            # between those tune-in modes only matters for shuffle.
            return self._current_in_order()

        if self.tune_in_mode == "resume" and self._resume_path is not None:
            return PlayRequest(path=self._resume_path, start=self._resume_position)

        return self._next_shuffled()

    def advance(self) -> Optional[PlayRequest]:
        """Decide what to play when the current episode ends naturally."""
        if self.is_empty:
            return None
        if self.tune_in_mode == "broadcast" and self._broadcast is not None:
            # Roll straight into whatever airs next in the running order.
            return self._broadcast.at(time.time())
        if self._in_order:
            return self._advance_in_order()
        return self._next_shuffled()

    def remember(self, path: Path, position: float) -> None:
        """Record where the viewer left off.

        Shuffle uses this only for the in-memory resume tune-in mode. In-order
        playback uses it across channel flips, and the app writes it to disk.
        """
        self._resume_path = path
        self._resume_position = max(0.0, position)
        if not self._in_order:
            return
        for index, episode in enumerate(self.episodes):
            if episode == path:
                self._cursor = index
                return

    def bookmark(self) -> ChannelBookmark:
        """The place to write down for this channel."""
        episode = ""
        position = 0.0
        if self.episodes and self.tune_in_mode != "broadcast":
            path = self._resume_path or self.episodes[self._cursor]
            episode = episode_rel(self.config.path, path)
            if self._resume_path == path:
                position = self._resume_position
        return ChannelBookmark(
            episode=episode,
            position=position,
            epoch=self.broadcast_epoch if self.broadcast_epoch is not None else self._saved_epoch,
        )

    def _restore(self, bookmark: ChannelBookmark) -> None:
        if not bookmark.episode or not self.episodes:
            return
        for index, episode in enumerate(self.episodes):
            if episode_rel(self.config.path, episode) == bookmark.episode:
                self._cursor = index
                self._resume_path = episode
                self._resume_position = max(0.0, bookmark.position)
                return

    # -- broadcast schedule -------------------------------------------------
    def _ensure_broadcast(self, *, epoch: float) -> Optional[BroadcastSchedule]:
        if self._broadcast is not None:
            return self._broadcast
        if self.is_empty:
            return None
        durations: List[float] = []
        for path in self.episodes:
            dur = probe_duration(path)
            durations.append(dur if dur else DEFAULT_EPISODE_SECONDS)
        # Use a channel-stable epoch offset so different channels are out of
        # phase with each other, but keep it deterministic per run.
        self.broadcast_epoch = epoch
        self._broadcast = BroadcastSchedule(
            self.episodes,
            durations,
            epoch=epoch,
            rng=self._rng,
            in_order=self._in_order,
        )
        return self._broadcast


class ChannelLineup:
    """An ordered set of channels with remote-style navigation."""

    def __init__(self, channels: Sequence[Channel]) -> None:
        if not channels:
            raise ValueError("a lineup needs at least one channel")
        # Present channels in ascending channel-number order, like a real tuner.
        self._channels: List[Channel] = sorted(channels, key=lambda c: c.number)
        self._by_number: Dict[int, Channel] = {c.number: c for c in self._channels}
        self._index = 0
        # Filled in by build_lineup so the app can save in-order bookmarks.
        self.state: Optional[PlaybackState] = None

    def __len__(self) -> int:
        return len(self._channels)

    def __iter__(self):
        return iter(self._channels)

    @property
    def current(self) -> Channel:
        return self._channels[self._index]

    @property
    def numbers(self) -> List[int]:
        return [c.number for c in self._channels]

    def has_number(self, number: int) -> bool:
        return number in self._by_number

    def index_of(self, number: int) -> Optional[int]:
        for i, ch in enumerate(self._channels):
            if ch.number == number:
                return i
        return None

    def up(self) -> Channel:
        self._index = (self._index + 1) % len(self._channels)
        return self.current

    def down(self) -> Channel:
        self._index = (self._index - 1) % len(self._channels)
        return self.current

    def select_number(self, number: int) -> Optional[Channel]:
        idx = self.index_of(number)
        if idx is None:
            return None
        self._index = idx
        return self.current

    def select_index(self, index: int) -> Channel:
        self._index = index % len(self._channels)
        return self.current


def preview_episodes(
    root: Path,
    episodes: Sequence[Path],
    *,
    order: str,
    bookmark: Optional[ChannelBookmark] = None,
    limit: int = 3,
) -> List[Path]:
    """The first episodes ``--check`` should list.

    In-order channels start at the saved episode (then wrap). Shuffle channels
    list the natural filename order; playback itself still shuffles.
    """
    if not episodes or limit <= 0:
        return []
    start = 0
    if order == "in_order" and bookmark is not None and bookmark.episode:
        for index, episode in enumerate(episodes):
            if episode_rel(root, episode) == bookmark.episode:
                start = index
                break
    count = min(limit, len(episodes))
    if order == "in_order":
        return [episodes[(start + offset) % len(episodes)] for offset in range(count)]
    return list(episodes[:count])


def build_lineup(config: Config, *, rng: Optional[random.Random] = None) -> ChannelLineup:
    """Scan every configured channel folder and build the full lineup."""
    state = PlaybackState.load(config.state_file or default_state_path())
    base_rng = rng or random.Random(config.shuffle_seed)
    channels: List[Channel] = []
    for i, ch_cfg in enumerate(config.channels):
        episodes = scan_episodes(
            ch_cfg.path,
            config.video_extensions,
            recursive=config.scan_recursive,
            exclude=ch_cfg.exclude,
            exclude_seasons=ch_cfg.exclude_seasons,
        )
        if not episodes:
            log.warning(
                "channel %s (%s) has no playable episodes in %s",
                ch_cfg.number, ch_cfg.name, ch_cfg.path,
            )
        # Give each channel its own RNG stream so they shuffle independently
        # but reproducibly when a seed is configured.
        if config.shuffle_seed is not None:
            # Derive a distinct-but-deterministic integer seed per channel.
            ch_rng = random.Random(hash((config.shuffle_seed, ch_cfg.number, i)) & 0xFFFFFFFF)
        else:
            ch_rng = random.Random()
        channels.append(
            Channel(
                ch_cfg,
                episodes,
                tune_in=config.tune_in,
                start_offset_min=config.start_offset_min,
                start_offset_max=config.start_offset_max,
                rng=ch_rng,
                bookmark=state.get(ch_cfg.path),
            )
        )
    lineup = ChannelLineup(channels)
    lineup.state = state
    return lineup


__all__ = [
    "Channel",
    "ChannelLineup",
    "PlayRequest",
    "BroadcastSchedule",
    "scan_episodes",
    "detect_season",
    "natural_sort_key",
    "episode_rel",
    "preview_episodes",
    "build_lineup",
]
