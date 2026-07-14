"""Mapping from raw remote/keyboard keys to high-level actions.

Two worlds feed in here:

* Linux input-event key *names* (``KEY_VOLUMEUP`` etc.) - used by both the
  evdev backend (real USB/IR remotes and keyboards) and the stdin dev backend
  after it translates characters to these names.
* HDMI-CEC user-control *names* (``volume up`` etc.) - used by the CEC backend.

Cheap USB/IR "media remotes" report a grab-bag of different key codes, so the
map is deliberately generous: several physical keys can map to the same action.
"""

from __future__ import annotations

from typing import Dict, Optional

from ..actions import Action, InputEvent

# --------------------------------------------------------------------------
# Linux evdev key names -> InputEvent
# --------------------------------------------------------------------------
_EVDEV_ACTIONS: Dict[str, InputEvent] = {
    # Channel changing. Dedicated channel keys, page keys, and the D-pad all
    # work so almost any remote can drive it.
    "KEY_CHANNELUP": InputEvent(Action.CHANNEL_UP),
    "KEY_PAGEUP": InputEvent(Action.CHANNEL_UP),
    "KEY_UP": InputEvent(Action.CHANNEL_UP),
    "KEY_CHANNELDOWN": InputEvent(Action.CHANNEL_DOWN),
    "KEY_PAGEDOWN": InputEvent(Action.CHANNEL_DOWN),
    "KEY_DOWN": InputEvent(Action.CHANNEL_DOWN),
    # Volume.
    "KEY_VOLUMEUP": InputEvent(Action.VOLUME_UP),
    "KEY_RIGHT": InputEvent(Action.VOLUME_UP),
    "KEY_EQUAL": InputEvent(Action.VOLUME_UP),
    "KEY_KPPLUS": InputEvent(Action.VOLUME_UP),
    "KEY_VOLUMEDOWN": InputEvent(Action.VOLUME_DOWN),
    "KEY_LEFT": InputEvent(Action.VOLUME_DOWN),
    "KEY_MINUS": InputEvent(Action.VOLUME_DOWN),
    "KEY_KPMINUS": InputEvent(Action.VOLUME_DOWN),
    "KEY_MUTE": InputEvent(Action.MUTE),
    "KEY_M": InputEvent(Action.MUTE),
    # Select / confirm a typed channel number.
    "KEY_ENTER": InputEvent(Action.ENTER),
    "KEY_KPENTER": InputEvent(Action.ENTER),
    "KEY_OK": InputEvent(Action.ENTER),
    "KEY_SELECT": InputEvent(Action.ENTER),
    "KEY_SPACE": InputEvent(Action.ENTER),
    # Info banner.
    "KEY_INFO": InputEvent(Action.INFO),
    "KEY_I": InputEvent(Action.INFO),
    # Jump to previous channel (the classic "last" / "back" button).
    "KEY_LAST": InputEvent(Action.LAST_CHANNEL),
    "KEY_PREVIOUS": InputEvent(Action.LAST_CHANNEL),
    "KEY_BACK": InputEvent(Action.LAST_CHANNEL),
    # Power / standby.
    "KEY_POWER": InputEvent(Action.POWER),
    "KEY_SLEEP": InputEvent(Action.POWER),
    # Quit the application (mostly for keyboards during setup).
    "KEY_ESC": InputEvent(Action.QUIT),
    "KEY_Q": InputEvent(Action.QUIT),
}

# Digit keys (top row and numeric keypad) -> DIGIT events.
for _d in range(10):
    _EVDEV_ACTIONS[f"KEY_{_d}"] = InputEvent.digit(_d)
    _EVDEV_ACTIONS[f"KEY_KP{_d}"] = InputEvent.digit(_d)


def evdev_key_to_event(key_name: str) -> Optional[InputEvent]:
    """Map an evdev key name (e.g. ``KEY_VOLUMEUP``) to an InputEvent."""
    return _EVDEV_ACTIONS.get(key_name)


# --------------------------------------------------------------------------
# stdin characters -> evdev key names (so they reuse the map above)
# --------------------------------------------------------------------------
# Single printable characters typed at a terminal (dev/testing mode).
_CHAR_TO_KEY: Dict[str, str] = {
    "+": "KEY_VOLUMEUP",
    "=": "KEY_VOLUMEUP",
    "-": "KEY_VOLUMEDOWN",
    "_": "KEY_VOLUMEDOWN",
    "m": "KEY_MUTE",
    "M": "KEY_MUTE",
    "i": "KEY_INFO",
    "I": "KEY_INFO",
    "l": "KEY_LAST",
    "L": "KEY_LAST",
    "p": "KEY_POWER",
    "P": "KEY_POWER",
    "q": "KEY_Q",
    "Q": "KEY_Q",
    "\r": "KEY_ENTER",
    "\n": "KEY_ENTER",
    " ": "KEY_ENTER",
    "\x1b": "KEY_ESC",
}
for _d in range(10):
    _CHAR_TO_KEY[str(_d)] = f"KEY_{_d}"

# Terminal escape sequences for the arrow keys.
_ESCAPE_TO_KEY: Dict[str, str] = {
    "[A": "KEY_UP",
    "[B": "KEY_DOWN",
    "[C": "KEY_RIGHT",
    "[D": "KEY_LEFT",
}


def stdin_char_to_event(char: str) -> Optional[InputEvent]:
    key = _CHAR_TO_KEY.get(char)
    return evdev_key_to_event(key) if key else None


def stdin_escape_to_event(seq: str) -> Optional[InputEvent]:
    key = _ESCAPE_TO_KEY.get(seq)
    return evdev_key_to_event(key) if key else None


# --------------------------------------------------------------------------
# HDMI-CEC user-control names -> InputEvent
# --------------------------------------------------------------------------
# Names as emitted by libCEC / `cec-client` "key pressed:" lines.
_CEC_ACTIONS: Dict[str, InputEvent] = {
    "up": InputEvent(Action.CHANNEL_UP),
    "channel up": InputEvent(Action.CHANNEL_UP),
    "down": InputEvent(Action.CHANNEL_DOWN),
    "channel down": InputEvent(Action.CHANNEL_DOWN),
    "right": InputEvent(Action.VOLUME_UP),
    "volume up": InputEvent(Action.VOLUME_UP),
    "left": InputEvent(Action.VOLUME_DOWN),
    "volume down": InputEvent(Action.VOLUME_DOWN),
    "mute": InputEvent(Action.MUTE),
    "select": InputEvent(Action.ENTER),
    "ok": InputEvent(Action.ENTER),
    "enter": InputEvent(Action.ENTER),
    "info": InputEvent(Action.INFO),
    "electronic program guide": InputEvent(Action.INFO),
    "display information": InputEvent(Action.INFO),
    "previous channel": InputEvent(Action.LAST_CHANNEL),
    "exit": InputEvent(Action.LAST_CHANNEL),
    "power": InputEvent(Action.POWER),
    "power toggle function": InputEvent(Action.POWER),
    "power off function": InputEvent(Action.POWER),
}
for _d in range(10):
    _CEC_ACTIONS[f"number {_d}"] = InputEvent.digit(_d)
    _CEC_ACTIONS[str(_d)] = InputEvent.digit(_d)


def cec_key_to_event(name: str) -> Optional[InputEvent]:
    """Map a CEC user-control name to an InputEvent (case-insensitive)."""
    return _CEC_ACTIONS.get(name.strip().lower())


__all__ = [
    "evdev_key_to_event",
    "stdin_char_to_event",
    "stdin_escape_to_event",
    "cec_key_to_event",
]
