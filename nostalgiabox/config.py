"""Configuration loading and validation.

The whole box is described by a single YAML file (see ``config.example.yaml``).
This module turns that file into validated :class:`Config` /
:class:`ChannelConfig` objects and fills in sensible defaults so a minimal
config still produces a working television.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


# Video containers we consider "an episode" when scanning a channel folder.
DEFAULT_VIDEO_EXTENSIONS: tuple[str, ...] = (
    ".mp4", ".mkv", ".avi", ".m4v", ".mov", ".webm", ".mpg", ".mpeg", ".ts",
)


class ConfigError(Exception):
    """Raised when the configuration file is missing or invalid."""


# How a channel behaves the moment you tune into it.
#   random    - start a fresh random episode from the beginning (the default,
#               and what most people picture: flip to the channel, a show
#               starts). Episodes keep rolling on a shuffle after that.
#   resume    - remember where you were on that channel and pick up there,
#               so flipping away and back does not restart the episode.
#   broadcast - the channel behaves like a real station that is "always on":
#               a fixed shuffled running order advances in real time whether
#               or not anyone is watching, so you tune in partway through
#               whatever "would" be airing right now.
TUNE_IN_MODES = ("random", "resume", "broadcast")

# Effect shown briefly while changing channels.
#   glitch - a short burst of digital corruption (default)
#   static - classic analog snow
#   none   - cut straight to the next channel
TRANSITION_EFFECTS = ("glitch", "static", "none")


@dataclass(frozen=True)
class UiConfig:
    """Look of the on-screen overlays (the green digital TV readouts)."""

    font: str = "VT323"             # bundled retro terminal font (OFL)
    color: str = "#4DFF5A"          # bright CRT phosphor green
    dim_color: str = "#123B18"      # unlit volume segment / dot colour
    glow: bool = True               # soft glow around text for that CRT bloom


@dataclass(frozen=True)
class CrtConfig:
    """The CRT picture effect applied to the 4:3 video via a GLSL shader."""

    enabled: bool = True
    curvature: float = 0.12         # barrel "bulge" amount (0 = perfectly flat)
    corner_radius: float = 0.065    # rounded-corner size (fraction of screen)
    vignette: float = 0.25          # darkening toward the edges
    scanlines: bool = True
    scanline_intensity: float = 0.12


@dataclass(frozen=True)
class ChannelConfig:
    """A single television channel backed by a folder of episodes."""

    number: int
    name: str
    path: Path
    shuffle: bool = True
    # Episodes to leave out. `exclude` is a list of case-insensitive glob
    # patterns matched against each file's path (and name); `exclude_seasons` is
    # a set of season numbers detected from the path (e.g. S06E01, "Season 6").
    exclude: tuple[str, ...] = ()
    exclude_seasons: frozenset[int] = frozenset()

    def __post_init__(self) -> None:
        if self.number < 0:
            raise ConfigError(f"channel number must be >= 0, got {self.number}")
        if not self.name:
            raise ConfigError(f"channel {self.number} is missing a name")


@dataclass(frozen=True)
class Config:
    """Top-level configuration for the whole nostalgia box."""

    channels: List[ChannelConfig]
    video_extensions: tuple[str, ...] = DEFAULT_VIDEO_EXTENSIONS
    tune_in: str = "random"
    start_channel: Optional[int] = None

    # Presentation / "feel" of the TV.
    force_4_3: bool = False                # if true, letterbox everything to 4:3;
                                          #   default keeps each show's own aspect
    # Start each episode a random number of seconds in (between min and max), so
    # channel switches land at varied points in the show.
    start_offset_min: float = 6.0
    start_offset_max: float = 10.0
    transition_effect: str = "none"       # channel-change effect: none|glitch|static
    transition_duration: float = 0.4      # length of the channel-change effect
    # When there's no transition effect, keep the current show playing this many
    # seconds while the next channel preloads, then cut over (avoids a frozen
    # frame on channel change). 0 = switch immediately.
    bridge_seconds: float = 0.8
    channel_bug_seconds: float = 4.0      # how long the channel banner lingers
    osd_duration: float = 2.0             # how long volume/message overlays linger
    ui: UiConfig = field(default_factory=UiConfig)
    crt: CrtConfig = field(default_factory=CrtConfig)

    # Audio.
    initial_volume: int = 70              # 0-100
    volume_step: int = 5
    audio_device: Optional[str] = None    # mpv audio device (e.g. HDMI); None = auto

    # Playback.
    scan_recursive: bool = True           # look in sub-folders for episodes
    shuffle_seed: Optional[int] = None    # set for deterministic ordering (tests)

    # Assets (generated by scripts/install.sh via nostalgiabox.static_gen).
    assets_dir: Optional[Path] = None

    # Options for the input backends (see input/manager.create_backends).
    input_options: Mapping[str, Any] = field(default_factory=dict)

    def channel_numbers(self) -> List[int]:
        return [c.number for c in self.channels]

    def with_channels(self, channels: List[ChannelConfig]) -> "Config":
        return replace(self, channels=channels)


def _as_path(value: Any, base: Optional[Path]) -> Path:
    p = Path(os.path.expanduser(str(value)))
    if not p.is_absolute() and base is not None:
        p = (base / p)
    return p


def _discover_channels(
    media_root: Path,
    *,
    start_number: int,
    default_shuffle: bool,
) -> List[ChannelConfig]:
    """Turn every immediate sub-folder of ``media_root`` into a channel.

    This is the "just drop show folders on the SD card" workflow: a folder
    called ``Dragon Tales`` becomes a channel named "Dragon Tales". Channels
    are numbered sequentially starting at ``start_number`` in alphabetical
    order of the folder name.
    """
    if not media_root.is_dir():
        raise ConfigError(f"media_root does not exist or is not a directory: {media_root}")

    subdirs = sorted(
        (p for p in media_root.iterdir() if p.is_dir() and not p.name.startswith(".")),
        key=lambda p: p.name.lower(),
    )
    channels: List[ChannelConfig] = []
    for offset, folder in enumerate(subdirs):
        channels.append(
            ChannelConfig(
                number=start_number + offset,
                name=_prettify_name(folder.name),
                path=folder,
                shuffle=default_shuffle,
            )
        )
    return channels


def _prettify_name(folder_name: str) -> str:
    """Turn a folder name like ``dragon_tales`` into ``Dragon Tales``."""
    cleaned = folder_name.replace("_", " ").replace("-", " ").strip()
    cleaned = " ".join(cleaned.split())
    return cleaned.title() if cleaned.islower() else cleaned


def _parse_channels(raw: Any, base: Optional[Path], default_shuffle: bool) -> List[ChannelConfig]:
    if not isinstance(raw, list):
        raise ConfigError("'channels' must be a list")
    channels: List[ChannelConfig] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ConfigError(f"channel #{i} must be a mapping, got {type(entry).__name__}")
        if "path" not in entry:
            raise ConfigError(f"channel #{i} is missing required key 'path'")
        number = entry.get("number", i + 2)  # old TVs often started around ch. 2
        name = entry.get("name") or _prettify_name(Path(str(entry["path"])).name)
        channels.append(
            ChannelConfig(
                number=int(number),
                name=str(name),
                path=_as_path(entry["path"], base),
                shuffle=bool(entry.get("shuffle", default_shuffle)),
                exclude=_parse_str_list(entry.get("exclude"), "exclude"),
                exclude_seasons=_parse_seasons(entry.get("exclude_seasons")),
            )
        )
    return channels


def _parse_str_list(raw: Any, name: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, list):
        return tuple(str(x) for x in raw)
    raise ConfigError(f"'{name}' must be a string or a list of strings")


def _parse_seasons(raw: Any) -> frozenset[int]:
    """Parse season numbers from an int, a 'start-end' range, or a list of those."""
    if raw is None:
        return frozenset()
    items = raw if isinstance(raw, list) else [raw]
    seasons: set[int] = set()
    for item in items:
        if isinstance(item, int):
            seasons.add(item)
        elif isinstance(item, str) and "-" in item:
            lo_s, hi_s = item.split("-", 1)
            try:
                lo, hi = int(lo_s), int(hi_s)
            except ValueError as exc:
                raise ConfigError(f"invalid season range '{item}'") from exc
            seasons.update(range(min(lo, hi), max(lo, hi) + 1))
        else:
            try:
                seasons.add(int(item))
            except (TypeError, ValueError) as exc:
                raise ConfigError(f"invalid season number '{item}'") from exc
    return frozenset(seasons)


def config_from_dict(data: Dict[str, Any], *, base_dir: Optional[Path] = None) -> Config:
    """Build a :class:`Config` from an already-parsed mapping.

    ``base_dir`` is used to resolve relative paths (normally the directory the
    config file lives in).
    """
    if not isinstance(data, dict):
        raise ConfigError("configuration root must be a mapping")

    default_shuffle = bool(data.get("shuffle", True))

    exts = data.get("video_extensions")
    if exts is None:
        extensions = DEFAULT_VIDEO_EXTENSIONS
    else:
        if not isinstance(exts, list) or not exts:
            raise ConfigError("'video_extensions' must be a non-empty list")
        extensions = tuple(e if e.startswith(".") else f".{e}" for e in (s.lower() for s in exts))

    media_root_raw = data.get("media_root")
    media_root = _as_path(media_root_raw, base_dir) if media_root_raw else None

    if "channels" in data:
        channels = _parse_channels(data["channels"], media_root or base_dir, default_shuffle)
    elif media_root is not None:
        channels = _discover_channels(
            media_root,
            start_number=int(data.get("first_channel_number", 2)),
            default_shuffle=default_shuffle,
        )
    else:
        raise ConfigError("configuration must define either 'channels' or 'media_root'")

    if not channels:
        raise ConfigError("no channels found - check 'channels' or the folders under 'media_root'")

    _ensure_unique_numbers(channels)

    tune_in = str(data.get("tune_in", "random")).lower()
    if tune_in not in TUNE_IN_MODES:
        raise ConfigError(f"'tune_in' must be one of {TUNE_IN_MODES}, got '{tune_in}'")

    assets_dir_raw = data.get("assets_dir")
    assets_dir = _as_path(assets_dir_raw, base_dir) if assets_dir_raw else None

    start_channel = data.get("start_channel")
    start_channel = int(start_channel) if start_channel is not None else None

    initial_volume = _clamp_int(data.get("initial_volume", 70), 0, 100, "initial_volume")
    volume_step = _clamp_int(data.get("volume_step", 5), 1, 100, "volume_step")
    audio_device = data.get("audio_device")
    audio_device = str(audio_device) if audio_device else None

    return Config(
        channels=channels,
        video_extensions=extensions,
        tune_in=tune_in,
        start_channel=start_channel,
        force_4_3=bool(data.get("force_4_3", False)),
        start_offset_min=_offset_range(data)[0],
        start_offset_max=_offset_range(data)[1],
        transition_effect=_valid_transition(data.get("transition", "none")),
        transition_duration=_clamp_float(data.get("transition_duration", 0.4), 0.0, 10.0, "transition_duration"),
        bridge_seconds=_clamp_float(data.get("bridge_seconds", 0.8), 0.0, 10.0, "bridge_seconds"),
        channel_bug_seconds=_clamp_float(data.get("channel_bug_seconds", 4.0), 0.0, 60.0, "channel_bug_seconds"),
        osd_duration=_clamp_float(data.get("osd_duration", 2.0), 0.0, 60.0, "osd_duration"),
        ui=_parse_ui(data.get("ui")),
        crt=_parse_crt(data.get("crt")),
        initial_volume=initial_volume,
        volume_step=volume_step,
        audio_device=audio_device,
        scan_recursive=bool(data.get("scan_recursive", True)),
        shuffle_seed=(int(data["shuffle_seed"]) if data.get("shuffle_seed") is not None else None),
        assets_dir=assets_dir,
        input_options=dict(data.get("input") or {}),
    )


def load_config(path: os.PathLike | str) -> Config:
    """Load and validate a YAML configuration file."""
    import yaml  # imported lazily so importing the package is cheap

    cfg_path = Path(path).expanduser()
    if not cfg_path.is_file():
        raise ConfigError(f"configuration file not found: {cfg_path}")
    try:
        with cfg_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - passthrough of parser error
        raise ConfigError(f"could not parse YAML in {cfg_path}: {exc}") from exc

    return config_from_dict(data, base_dir=cfg_path.parent)


def _parse_ui(raw: Any) -> UiConfig:
    if raw is None:
        return UiConfig()
    if not isinstance(raw, dict):
        raise ConfigError("'ui' must be a mapping")
    defaults = UiConfig()
    return UiConfig(
        font=str(raw.get("font", defaults.font)),
        color=_valid_color(raw.get("color", defaults.color), "ui.color"),
        dim_color=_valid_color(raw.get("dim_color", defaults.dim_color), "ui.dim_color"),
        glow=bool(raw.get("glow", defaults.glow)),
    )


def _parse_crt(raw: Any) -> CrtConfig:
    if raw is None:
        return CrtConfig()
    if not isinstance(raw, dict):
        raise ConfigError("'crt' must be a mapping")
    d = CrtConfig()
    return CrtConfig(
        enabled=bool(raw.get("enabled", d.enabled)),
        curvature=_clamp_float(raw.get("curvature", d.curvature), 0.0, 0.5, "crt.curvature"),
        corner_radius=_clamp_float(raw.get("corner_radius", d.corner_radius), 0.0, 0.3, "crt.corner_radius"),
        vignette=_clamp_float(raw.get("vignette", d.vignette), 0.0, 1.0, "crt.vignette"),
        scanlines=bool(raw.get("scanlines", d.scanlines)),
        scanline_intensity=_clamp_float(
            raw.get("scanline_intensity", d.scanline_intensity), 0.0, 1.0, "crt.scanline_intensity"
        ),
    )


def _offset_range(data: Dict[str, Any]) -> tuple[float, float]:
    """Resolve the (min, max) start-offset seconds from the config.

    Accepts ``start_offset`` as a single number or a ``[min, max]`` list, or
    explicit ``start_offset_min`` / ``start_offset_max`` keys.
    """
    if "start_offset_min" in data or "start_offset_max" in data:
        lo = _clamp_float(data.get("start_offset_min", 0.0), 0.0, 3600.0, "start_offset_min")
        hi = _clamp_float(data.get("start_offset_max", lo), 0.0, 3600.0, "start_offset_max")
    else:
        raw = data.get("start_offset", [6.0, 10.0])
        if isinstance(raw, (list, tuple)):
            if not raw:
                raise ConfigError("'start_offset' list cannot be empty")
            lo = _clamp_float(raw[0], 0.0, 3600.0, "start_offset")
            hi = _clamp_float(raw[1] if len(raw) > 1 else raw[0], 0.0, 3600.0, "start_offset")
        else:
            lo = hi = _clamp_float(raw, 0.0, 3600.0, "start_offset")
    return (lo, max(lo, hi))


def _valid_transition(value: Any) -> str:
    s = str(value).strip().lower()
    if s not in TRANSITION_EFFECTS:
        raise ConfigError(f"'transition' must be one of {TRANSITION_EFFECTS}, got '{value}'")
    return s


def _valid_color(value: Any, name: str) -> str:
    """Validate a ``#RRGGBB`` hex colour string."""
    import re

    s = str(value).strip()
    if not re.fullmatch(r"#?[0-9a-fA-F]{6}", s):
        raise ConfigError(f"'{name}' must be a hex colour like '#4DFF5A', got '{value}'")
    return s if s.startswith("#") else f"#{s}"


def _ensure_unique_numbers(channels: List[ChannelConfig]) -> None:
    seen: Dict[int, str] = {}
    for ch in channels:
        if ch.number in seen:
            raise ConfigError(
                f"duplicate channel number {ch.number} used by "
                f"'{seen[ch.number]}' and '{ch.name}'"
            )
        seen[ch.number] = ch.name


def _clamp_int(value: Any, lo: int, hi: int, name: str) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"'{name}' must be an integer") from exc
    return max(lo, min(hi, n))


def _clamp_float(value: Any, lo: float, hi: float, name: str) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"'{name}' must be a number") from exc
    return max(lo, min(hi, n))


__all__ = [
    "Config",
    "ChannelConfig",
    "UiConfig",
    "CrtConfig",
    "ConfigError",
    "load_config",
    "config_from_dict",
    "DEFAULT_VIDEO_EXTENSIONS",
    "TUNE_IN_MODES",
    "TRANSITION_EFFECTS",
]
