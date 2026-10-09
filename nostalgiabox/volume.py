"""Which knob the remote's volume keys turn.

The Pi's software volume and the television's volume are different controls.
``volume_control`` in config.yaml picks one:

* ``auto`` (the default) — send HDMI-CEC volume to the TV when ``cec-client``
  is available, otherwise adjust the Pi.
* ``tv`` — same as auto when CEC is up; if it is not, fall back to the Pi.
* ``pi`` — always adjust the Pi, and leave the TV alone.

The running app stores the level. This module only resolves the mode.
"""

from __future__ import annotations

VOLUME_CONTROLS = ("auto", "tv", "pi")


def resolve_volume_control(requested: str, *, cec_available: bool) -> str:
    """Return ``"tv"`` or ``"pi"``.

    ``tv`` is only returned when a CEC sender is actually available. ``auto``
    and ``tv`` both fall back to ``pi`` otherwise, so a config that asks for
    the television still makes sound on a setup with no CEC.
    """
    mode = str(requested or "auto").strip().lower()
    if mode not in VOLUME_CONTROLS:
        raise ValueError(
            f"volume_control must be one of {VOLUME_CONTROLS}, got {requested!r}"
        )
    if mode == "pi" or not cec_available:
        return "pi"
    return "tv"


__all__ = ["VOLUME_CONTROLS", "resolve_volume_control"]
