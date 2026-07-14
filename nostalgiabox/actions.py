"""The abstract "remote control" vocabulary.

Every input backend (a USB/IR remote seen as a keyboard, the TV's own remote
over HDMI-CEC, or the developer's keyboard over stdin) is translated into one
of these high-level :class:`Action` values. The rest of the application only
ever deals with actions, never with raw key codes, which keeps the input
handling decoupled from the application logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional


class Action(Enum):
    """A single high-level intent produced by a remote control."""

    CHANNEL_UP = auto()
    CHANNEL_DOWN = auto()
    VOLUME_UP = auto()
    VOLUME_DOWN = auto()
    MUTE = auto()
    DIGIT = auto()          # carries which digit in InputEvent.value (0-9)
    ENTER = auto()          # confirm a direct channel entry ("OK" / select)
    INFO = auto()           # re-show the channel banner
    LAST_CHANNEL = auto()   # jump back to the previously watched channel
    POWER = auto()          # toggle standby (blank screen)
    QUIT = auto()           # shut the application down entirely


@dataclass(frozen=True)
class InputEvent:
    """An action plus optional payload, as emitted by an input backend.

    ``value`` currently only carries the pressed digit for :attr:`Action.DIGIT`
    events, but exists as a general-purpose slot so future actions can carry
    data without changing the queue contract.
    """

    action: Action
    value: Optional[int] = None

    @classmethod
    def digit(cls, number: int) -> "InputEvent":
        if not 0 <= number <= 9:
            raise ValueError(f"digit must be 0-9, got {number}")
        return cls(Action.DIGIT, number)


__all__ = ["Action", "InputEvent"]
