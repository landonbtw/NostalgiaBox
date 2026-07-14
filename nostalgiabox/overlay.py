"""On-screen display: the channel banner, the volume bar, and messages.

These are the little touches that sell the "it's a TV" illusion: the translucent
channel number that flashes in the corner when you flip channels, and the
segmented volume bar that slides up from the bottom. They are drawn as ASS
overlays on a fixed 1280x720 virtual canvas (mpv scales it to whatever the TV
is), and cleared automatically after a few seconds by :meth:`OverlayManager.tick`,
which the main loop calls on every iteration.
"""

from __future__ import annotations

import time
from typing import Callable, Dict, Optional

from .config import Config
from .player import Player

# Virtual canvas the overlays are laid out on. mpv scales this to the display,
# so the layout looks the same on a 720p or a 1080p TV.
CANVAS_W = 1280
CANVAS_H = 720

# Overlay slots (ids). Each kind of overlay owns one id so it can be replaced
# or cleared independently.
_ID_CHANNEL = 1
_ID_VOLUME = 2
_ID_STANDBY = 3

# ASS colour helpers: format is &HAABBGGRR (alpha then blue/green/red).
_WHITE = "&H00FFFFFF"
_BLACK = "&H00000000"
_DIM = "&H60000000"     # translucent black (box backgrounds)
_ACCENT = "&H0033CCFF"  # warm amber, very "cable box readout"


class OverlayManager:
    """Draws and expires the TV's on-screen overlays."""

    def __init__(
        self,
        player: Player,
        config: Config,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._player = player
        self._config = config
        self._clock = clock
        # overlay id -> wall time (monotonic) at which it should disappear.
        self._expiry: Dict[int, float] = {}

    # -- public API ---------------------------------------------------------
    def show_channel_bug(
        self, number: int, name: str, *, duration: Optional[float] = None
    ) -> None:
        """Flash the channel number + name, like changing channels on a cable box."""
        dur = self._config.channel_bug_seconds if duration is None else duration
        ass = _channel_bug_ass(number, name)
        self._player.set_overlay(_ID_CHANNEL, ass, CANVAS_W, CANVAS_H)
        self._arm(_ID_CHANNEL, dur)

    def show_volume(
        self, level: int, muted: bool, *, duration: Optional[float] = None
    ) -> None:
        dur = self._config.osd_duration if duration is None else duration
        ass = _volume_ass(level, muted)
        self._player.set_overlay(_ID_VOLUME, ass, CANVAS_W, CANVAS_H)
        self._arm(_ID_VOLUME, dur)

    def show_message(self, text: str, *, duration: Optional[float] = None) -> None:
        dur = self._config.osd_duration if duration is None else duration
        self._player.show_text(text, dur)

    def show_standby(self) -> None:
        """Persistent 'no signal / standby' notice (does not auto-expire)."""
        ass = _standby_ass()
        self._player.set_overlay(_ID_STANDBY, ass, CANVAS_W, CANVAS_H)
        self._expiry.pop(_ID_STANDBY, None)

    def clear_standby(self) -> None:
        self._player.clear_overlay(_ID_STANDBY)
        self._expiry.pop(_ID_STANDBY, None)

    def tick(self) -> None:
        """Clear any overlays whose time is up. Call this every loop iteration."""
        now = self._clock()
        for overlay_id, when in list(self._expiry.items()):
            if now >= when:
                self._player.clear_overlay(overlay_id)
                self._expiry.pop(overlay_id, None)

    def clear_all(self) -> None:
        for overlay_id in (_ID_CHANNEL, _ID_VOLUME, _ID_STANDBY):
            self._player.clear_overlay(overlay_id)
        self._expiry.clear()

    # -- internals ----------------------------------------------------------
    def _arm(self, overlay_id: int, duration: float) -> None:
        if duration <= 0:
            # duration 0 means "leave it until explicitly cleared"
            self._expiry.pop(overlay_id, None)
        else:
            self._expiry[overlay_id] = self._clock() + duration


# --------------------------------------------------------------------------
# ASS builders. Kept as free functions so they are easy to unit test.
# --------------------------------------------------------------------------
def _channel_bug_ass(number: int, name: str) -> str:
    """A translucent panel in the top-right with the channel number and name."""
    num = f"{number:02d}"
    safe_name = _escape(name.upper())
    # Box in the top-right corner.
    box = _rounded_box(x=CANVAS_W - 360, y=40, w=320, h=120, fill=_DIM)
    # Big amber channel number.
    number_txt = (
        rf"{{\an7\pos({CANVAS_W - 340},58)\fs74\b1\c{_ACCENT}\bord2\3c{_BLACK}}}{num}"
    )
    # Show name under the number, white.
    name_txt = (
        rf"{{\an7\pos({CANVAS_W - 340},140)\fs30\b1\c{_WHITE}\bord2\3c{_BLACK}}}{safe_name}"
    )
    # Small "CH" label to the right of the number.
    ch_lbl = (
        rf"{{\an7\pos({CANVAS_W - 220},70)\fs26\b1\c{_WHITE}\bord2\3c{_BLACK}}}CH"
    )
    return "\n".join([box, number_txt, ch_lbl, name_txt])


def _volume_ass(level: int, muted: bool) -> str:
    """A segmented volume bar sliding up from the bottom centre."""
    level = max(0, min(100, int(level)))
    segments = 20
    filled = 0 if muted else round(level / 100 * segments)

    bar_w = 600
    bar_h = 34
    x0 = (CANVAS_W - bar_w) // 2
    y0 = CANVAS_H - 110
    gap = 4
    seg_w = (bar_w - gap * (segments - 1)) / segments

    parts = [_rounded_box(x=x0 - 24, y=y0 - 54, w=bar_w + 48, h=bar_h + 96, fill=_DIM)]

    label = "MUTE" if muted else "VOLUME"
    label_colour = _ACCENT if muted else _WHITE
    parts.append(
        rf"{{\an7\pos({x0},{y0 - 44})\fs28\b1\c{label_colour}\bord2\3c{_BLACK}}}{label}"
    )
    if not muted:
        parts.append(
            rf"{{\an7\pos({x0 + bar_w - 70},{y0 - 44})\fs28\b1\c{_WHITE}\bord2\3c{_BLACK}}}{level:3d}%"
        )

    # Draw each segment as a small rectangle; filled ones amber, rest dim.
    for i in range(segments):
        sx = x0 + i * (seg_w + gap)
        colour = _ACCENT if i < filled else "&H00333333"
        parts.append(_filled_rect(x=sx, y=y0, w=seg_w, h=bar_h, fill=colour))
    return "\n".join(parts)


def _standby_ass() -> str:
    """A simple centred 'standby' notice for when the box is 'off'."""
    return (
        rf"{{\an5\pos({CANVAS_W // 2},{CANVAS_H // 2})\fs54\b1\c{_WHITE}"
        rf"\bord3\3c{_BLACK}}}STANDBY"
    )


def _filled_rect(*, x: float, y: float, w: float, h: float, fill: str) -> str:
    """An ASS drawing (\\p1) filled rectangle at absolute canvas coordinates."""
    x, y = round(x), round(y)
    w, h = round(w), round(h)
    draw = f"m 0 0 l {w} 0 l {w} {h} l 0 {h}"
    return rf"{{\an7\pos({x},{y})\p1\c{fill}\bord0\shad0}}{draw}{{\p0}}"


def _rounded_box(*, x: int, y: int, w: int, h: int, fill: str) -> str:
    """A background box. (Rendered as a plain rectangle - ASS has no easy
    rounded rect, but the translucent fill reads fine on a TV.)"""
    return _filled_rect(x=x, y=y, w=w, h=h, fill=fill)


def _escape(text: str) -> str:
    """Escape characters that are meaningful inside an ASS override block."""
    return (
        text.replace("\\", "\\\\")
        .replace("{", "(")
        .replace("}", ")")
    )


__all__ = ["OverlayManager", "CANVAS_W", "CANVAS_H"]
