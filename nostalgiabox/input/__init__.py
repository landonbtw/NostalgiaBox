"""Remote-control input backends and the manager that fans them into actions.

The application asks :class:`InputManager` for a queue of high-level
:class:`~nostalgiabox.actions.InputEvent` values and never touches raw devices
directly. Backends (keyboard/USB-IR remote via evdev, the TV remote via
HDMI-CEC, and the developer's keyboard via stdin) each run in a thread and push
normalised events onto that shared queue.
"""

from .manager import InputManager, create_backends
from .base import InputBackend

__all__ = ["InputManager", "InputBackend", "create_backends"]
