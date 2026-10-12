"""Which knob the remote's volume keys turn.

The Pi's software volume and the television's volume are different controls.
``volume_control`` in config.yaml picks one:

* ``auto`` (the default) — send HDMI-CEC volume to the TV when ``cec-client``
  has found a television. If the program is missing, the adapter does not
  open, or no TV answers, the Pi volume is used and nothing is shown on screen.
* ``tv`` — ask for the TV, and fall back to the Pi when no TV is found.
* ``pi`` — always adjust the Pi, and leave the TV alone.

The running app stores the level. This module only resolves the mode.
"""

from __future__ import annotations

VOLUME_CONTROLS = ("auto", "tv", "pi")


def resolve_volume_control(requested: str, *, cec_available: bool) -> str:
    """Return ``"tv"`` or ``"pi"``.

    ``cec_available`` means a television answered on the CEC bus, not merely
    that the ``cec-client`` program is installed. ``auto`` and ``tv`` both
    fall back to ``pi`` otherwise.
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
