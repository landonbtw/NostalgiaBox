"""The video player abstraction.

The application talks to an abstract :class:`Player`; two implementations exist:

* :class:`MpvPlayer` - the real thing, backed by libmpv (via the ``python-mpv``
  package). This is what runs on the Raspberry Pi against the TV.
* :class:`MockPlayer` - a no-op player that records what it was asked to do and
  lets tests/dev drive "the episode ended" by hand. This lets the entire app be
  exercised on a laptop with no display, no libmpv, and no media files.

Keeping this boundary thin (load / stop / volume / a couple of OSD hooks) means
the interesting logic in ``app.py`` never has to know which one it is using.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, List, Optional, Tuple

log = logging.getLogger(__name__)

# Reason strings passed to the "playback finished" callback.
END_EOF = "eof"        # the file played to its natural end -> roll next episode
END_ERROR = "error"    # the file failed to play -> skip to next episode
END_STOPPED = "stopped"  # we stopped it on purpose (channel change) -> ignore


class Player(ABC):
    """Minimal video-player interface used by the application."""

    #: Called when playback of the current item finishes. Receives one of the
    #: END_* reason strings. Set by the application before playing anything.
    on_end: Optional[Callable[[str], None]] = None

    @abstractmethod
    def play(self, path: Path, *, start: float = 0.0) -> None:
        """Begin playing ``path`` from ``start`` seconds in."""

    @abstractmethod
    def play_loop(self, path: Path) -> None:
        """Play ``path`` on an endless loop (used for the static/no-signal clip)."""

    def play_transition(
        self,
        static_path: Path,
        target_path: Path,
        *,
        start: float = 0.0,
        static_seconds: float = 0.5,
    ) -> None:
        """Show a brief static burst, then the target episode.

        The default implementation just plays the target; players that can
        preload (see :class:`MpvPlayer`) override this to make the switch
        near-instant.
        """
        self.play(target_path, start=start)

    @abstractmethod
    def stop(self) -> None:
        """Stop playback and show a blank screen."""

    @abstractmethod
    def set_volume(self, volume: int) -> None:
        """Set the volume (0-100)."""

    @abstractmethod
    def set_mute(self, muted: bool) -> None: ...

    @abstractmethod
    def get_time_pos(self) -> Optional[float]:
        """Current playback position in seconds, or None if nothing is playing."""

    @abstractmethod
    def show_text(self, text: str, duration: float) -> None:
        """Show a plain OSD message for ``duration`` seconds."""

    @abstractmethod
    def set_overlay(self, overlay_id: int, ass: str, res_x: int, res_y: int) -> None:
        """Draw an ASS overlay with the given id (replacing any previous one)."""

    @abstractmethod
    def clear_overlay(self, overlay_id: int) -> None:
        """Remove a previously drawn overlay."""

    @abstractmethod
    def close(self) -> None:
        """Release resources."""


class MpvPlayer(Player):
    """A :class:`Player` backed by libmpv, tuned for a Raspberry Pi + TV."""

    def __init__(
        self,
        *,
        fullscreen: bool = True,
        hwdec: str = "auto-safe",
        glsl_shaders: Optional[str] = None,
        fonts_dir: Optional[Path] = None,
        force_4_3: bool = True,
        extra_options: Optional[dict] = None,
    ) -> None:
        try:
            import mpv  # type: ignore
        except ImportError as exc:  # pragma: no cover - only on machines w/o libmpv
            raise RuntimeError(
                "python-mpv/libmpv is not installed. On the Raspberry Pi run "
                "`scripts/install.sh` or `pip install .[pi]` and ensure libmpv "
                "is present (`sudo apt install libmpv2 mpv`)."
            ) from exc

        # Make our bundled retro font discoverable by libass (used for the OSD
        # overlays) by dropping it into mpv's config "fonts" directory.
        if fonts_dir is not None:
            _install_fonts_for_mpv(fonts_dir)

        options = dict(
            # We drive the OSD ourselves, so disable mpv's own on-screen
            # controller and default keybindings.
            osc=False,
            input_default_bindings=False,
            input_vo_keyboard=False,
            # Keep a window alive even with nothing playing so the screen never
            # drops to a console/desktop between episodes or on an empty channel.
            idle="yes",
            force_window="yes",
            # keep-open=yes means a file that reaches its end PAUSES on the last
            # frame and sets the "eof-reached" property instead of silently
            # unloading. We watch that property to roll the next episode. This
            # avoids a nasty race: replacing a file (on a channel change) also
            # fires an "end-file" event for the outgoing file, and its reason is
            # unreliable across mpv versions - reacting to it caused episodes to
            # be skipped or the picture to hang. "eof-reached" only ever trips on
            # a genuine end-of-file, so it is the robust signal.
            keep_open="yes",
            # Preload the next playlist entry while the current one plays. This
            # is what makes channel changes near-instant: during the ~0.5s of
            # static, mpv is already opening/decoding the episode, so it appears
            # the moment the static ends (see play_transition).
            prefetch_playlist="yes",
            fullscreen=fullscreen,
            # Hardware decode + a sensible video output for the Pi. gpu with the
            # drm context works headless on the Pi 4; libmpv falls back sanely.
            hwdec=hwdec,
            # 4:3 shows should be pillarboxed (not stretched) inside the frame.
            keepaspect="yes",
            video_unscaled="no",
            # Hide the mouse cursor - this is a TV, not a computer.
            cursor_autohide="always",
            # A pleasant, readable OSD font size relative to the window.
            osd_font_size=40,
        )
        if glsl_shaders:
            # CRT curvature/rounding/vignette/scanlines. Applied globally (always
            # on) so a newly-loaded episode is never shown for a frame or two
            # without the effect on a channel change.
            options["glsl_shaders"] = glsl_shaders
        if force_4_3:
            # Fit ANY source into a 4:3 raster (letterboxing 16:9 with black
            # bars), so every show - and the static/colour-bar clips - appears in
            # the same 4:3 tube-TV frame. mpv then pillarboxes that 4:3 image on
            # a 16:9 TV, and the CRT shader curves it.
            options["vf"] = (
                "lavfi=[scale=960:720:force_original_aspect_ratio=decrease,"
                "pad=960:720:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1]"
            )
        if extra_options:
            options.update(extra_options)

        self._mpv = mpv.MPV(**options)
        self._closed = False
        # True while a looping filler clip (static / colour bars) is showing, so
        # its (non-)ending never advances the channel.
        self._suppress = True

        @self._mpv.property_observer("eof-reached")
        def _on_eof(_name, value):  # pragma: no cover - needs libmpv + media
            if value and not self._suppress and self.on_end is not None:
                try:
                    self.on_end(END_EOF)
                except Exception:  # noqa: BLE001 - never let a callback kill mpv
                    log.exception("error in on_end (eof) callback")

        @self._mpv.event_callback("end-file")
        def _on_end_file(event):  # pragma: no cover - needs libmpv + media
            # We only care about *errors* here (e.g. a corrupt/missing file) so
            # we can skip to the next episode. Natural ends are handled by the
            # eof-reached observer above; intentional stops/replacements are
            # ignored.
            if self._suppress:
                return
            if _extract_end_reason(event) == END_ERROR and self.on_end is not None:
                try:
                    self.on_end(END_ERROR)
                except Exception:  # noqa: BLE001
                    log.exception("error in on_end (error) callback")

    # -- playback -----------------------------------------------------------
    def play(self, path: Path, *, start: float = 0.0) -> None:
        # Enable end detection only for real content.
        self._suppress = False
        try:
            self._mpv.loop_file = "no"
            if start and start > 0:
                # start is an mpv per-file option; +N seeks N seconds in.
                self._mpv.loadfile(str(path), "replace", start=f"+{start:.3f}")
            else:
                self._mpv.loadfile(str(path), "replace")
            self._mpv.pause = False  # keep-open can leave us paused; force play
        except Exception:  # noqa: BLE001
            log.exception("failed to play %s", path)
            if self.on_end is not None:
                self.on_end(END_ERROR)

    def play_loop(self, path: Path) -> None:
        self._suppress = True  # a looping clip should never trigger "next"
        try:
            self._mpv.loop_file = "inf"
            self._mpv.loadfile(str(path), "replace")
            self._mpv.pause = False
        except Exception:  # noqa: BLE001
            log.exception("failed to loop %s", path)

    def play_transition(
        self,
        static_path: Path,
        target_path: Path,
        *,
        start: float = 0.0,
        static_seconds: float = 0.5,
    ) -> None:
        # Build a 2-entry playlist: [static (cut to static_seconds), episode].
        # mpv plays the static burst and, thanks to prefetch-playlist, has the
        # episode ready to show the instant the static ends. keep-open=yes only
        # holds the LAST entry, so eof-reached (which advances the channel) only
        # ever trips for the episode - never the static.
        self._suppress = False
        try:
            self._mpv.loop_file = "no"
            self._mpv.loadfile(
                str(static_path), "replace", end=f"{max(0.05, static_seconds):.3f}"
            )
            if start and start > 0:
                self._mpv.loadfile(str(target_path), "append", start=f"+{start:.3f}")
            else:
                self._mpv.loadfile(str(target_path), "append")
            self._mpv.pause = False
        except Exception:  # noqa: BLE001
            log.exception("failed transition to %s", target_path)
            self.play(target_path, start=start)

    def stop(self) -> None:
        self._suppress = True
        try:
            self._mpv.command("stop")
        except Exception:  # noqa: BLE001 - stopping should never crash us
            log.debug("mpv stop failed", exc_info=True)

    # -- audio --------------------------------------------------------------
    def set_volume(self, volume: int) -> None:
        try:
            self._mpv.volume = max(0, min(100, int(volume)))
        except Exception:  # noqa: BLE001
            log.debug("could not set volume", exc_info=True)

    def set_mute(self, muted: bool) -> None:
        try:
            self._mpv.mute = bool(muted)
        except Exception:  # noqa: BLE001
            log.debug("could not set mute", exc_info=True)

    def get_time_pos(self) -> Optional[float]:
        try:
            pos = self._mpv.time_pos
            return float(pos) if pos is not None else None
        except Exception:  # noqa: BLE001
            return None

    # -- OSD ----------------------------------------------------------------
    def show_text(self, text: str, duration: float) -> None:
        try:
            self._mpv.command("show-text", text, int(duration * 1000))
        except Exception:  # noqa: BLE001
            log.debug("show-text failed", exc_info=True)

    def set_overlay(self, overlay_id: int, ass: str, res_x: int, res_y: int) -> None:
        try:
            # osd-overlay positional args: id, format, data, res_x, res_y.
            # (Trailing z/hidden/compute_bounds use their defaults.)
            self._mpv.command(
                "osd-overlay", overlay_id, "ass-events", ass, res_x, res_y
            )
        except Exception:  # noqa: BLE001
            # Fall back to a plain message so the viewer still gets feedback.
            log.debug("osd-overlay failed, falling back to show-text", exc_info=True)
            self.show_text(_strip_ass(ass), 3.0)

    def clear_overlay(self, overlay_id: int) -> None:
        try:
            self._mpv.command("osd-overlay", overlay_id, "none", "")
        except Exception:  # noqa: BLE001
            log.debug("clearing overlay failed", exc_info=True)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._mpv.terminate()
        except Exception:  # noqa: BLE001
            log.debug("mpv terminate failed", exc_info=True)


class MockPlayer(Player):
    """A headless stand-in that records commands - for tests and dev mode."""

    def __init__(self, *, verbose: bool = False) -> None:
        self.verbose = verbose
        self.current: Optional[Path] = None
        self.looping: Optional[Path] = None
        self.volume: int = 0
        self.muted: bool = False
        self.time_pos: float = 0.0
        self.closed = False
        # Recorded history, handy for assertions in tests.
        self.played: List[Tuple[Path, float]] = []
        self.transitions: List[Tuple[Path, Path, float]] = []
        self.messages: List[Tuple[str, float]] = []
        self.overlays: dict[int, str] = {}
        self.stops = 0

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"[player] {msg}")

    def play(self, path: Path, *, start: float = 0.0) -> None:
        self.current = path
        self.looping = None
        self.time_pos = start
        self.played.append((path, start))
        self._log(f"PLAY {path} @ {start:.1f}s")

    def play_loop(self, path: Path) -> None:
        self.looping = path
        self.current = path
        self._log(f"LOOP {path}")

    def play_transition(
        self,
        static_path: Path,
        target_path: Path,
        *,
        start: float = 0.0,
        static_seconds: float = 0.5,
    ) -> None:
        self.transitions.append((static_path, target_path, start))
        # The episode is what ends up playing (static is momentary).
        self.current = target_path
        self.looping = None
        self.time_pos = start
        self.played.append((target_path, start))
        self._log(f"TRANSITION static={static_path} -> {target_path} @ {start:.1f}s")

    def stop(self) -> None:
        self.current = None
        self.looping = None
        self.stops += 1
        self._log("STOP")

    def set_volume(self, volume: int) -> None:
        self.volume = max(0, min(100, int(volume)))
        self._log(f"VOLUME {self.volume}")

    def set_mute(self, muted: bool) -> None:
        self.muted = bool(muted)
        self._log(f"MUTE {self.muted}")

    def get_time_pos(self) -> Optional[float]:
        return self.time_pos if self.current is not None else None

    def show_text(self, text: str, duration: float) -> None:
        self.messages.append((text, duration))
        self._log(f"TEXT {text!r} ({duration}s)")

    def set_overlay(self, overlay_id: int, ass: str, res_x: int, res_y: int) -> None:
        self.overlays[overlay_id] = ass
        self._log(f"OVERLAY {overlay_id}")

    def clear_overlay(self, overlay_id: int) -> None:
        self.overlays.pop(overlay_id, None)
        self._log(f"CLEAR OVERLAY {overlay_id}")

    def close(self) -> None:
        self.closed = True
        self._log("CLOSE")

    # -- test/dev helper ----------------------------------------------------
    def finish_current(self, reason: str = END_EOF) -> None:
        """Simulate the current episode ending, triggering ``on_end``."""
        self.current = None
        if self.on_end is not None:
            self.on_end(reason)


def _extract_end_reason(event) -> str:  # pragma: no cover - libmpv specific
    """Normalise the many shapes of a python-mpv end-file event into a reason."""
    reason = None
    try:
        data = getattr(event, "data", event)
        if isinstance(data, dict):
            reason = data.get("reason")
        else:
            reason = getattr(data, "reason", None)
    except Exception:  # noqa: BLE001
        reason = None
    reason = str(reason).lower() if reason is not None else ""
    if "eof" in reason:
        return END_EOF
    if "error" in reason:
        return END_ERROR
    if "stop" in reason or "quit" in reason:
        return END_STOPPED
    # Unknown/redirect reasons: treat as a natural end so the channel keeps going.
    return END_EOF


def _install_fonts_for_mpv(fonts_dir: Path) -> None:
    """Copy bundled .ttf fonts into mpv's config 'fonts' dir so libass finds them.

    mpv automatically loads any fonts placed in ``<mpv config dir>/fonts``, which
    is the most reliable way to make our retro OSD font available to the ASS
    overlays without touching the system-wide fontconfig setup.
    """
    import os
    import shutil

    if not fonts_dir.is_dir():
        return
    config_home = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    dest = Path(config_home) / "mpv" / "fonts"
    try:
        dest.mkdir(parents=True, exist_ok=True)
        for ttf in fonts_dir.glob("*.ttf"):
            target = dest / ttf.name
            if not target.exists():
                shutil.copy2(ttf, target)
    except OSError:
        log.debug("could not install bundled fonts for mpv", exc_info=True)


def _strip_ass(ass: str) -> str:  # pragma: no cover - trivial
    """Very small ASS-tag stripper for the show-text fallback path."""
    import re

    text = re.sub(r"\{[^}]*\}", "", ass)
    text = text.replace("\\N", " ").replace("\\n", " ")
    return text.strip()


__all__ = [
    "Player",
    "MpvPlayer",
    "MockPlayer",
    "END_EOF",
    "END_ERROR",
    "END_STOPPED",
]
