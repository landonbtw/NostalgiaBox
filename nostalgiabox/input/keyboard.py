"""Keyboard / USB / IR remote input via Linux evdev.

Most cheap "media remotes" (and IR remotes bridged through a USB receiver or
LIRC's uinput) show up to Linux as ordinary keyboard-like input devices. This
backend reads their key-down events straight from ``/dev/input/event*`` using
the ``evdev`` package - no X server or desktop required, which is exactly what
we want on a headless Pi wired to a TV.
"""

from __future__ import annotations

import logging
import select
from typing import List, Optional, Sequence

from .base import InputBackend
from .keymap import evdev_key_to_event

log = logging.getLogger(__name__)

# Key-event values reported by evdev: 0=up, 1=down, 2=autorepeat.
_KEY_DOWN = 1
_KEY_REPEAT = 2


class KeyboardBackend(InputBackend):
    """Reads remote/keyboard events from evdev input devices."""

    name = "keyboard"

    def __init__(
        self,
        *,
        device_paths: Optional[Sequence[str]] = None,
        name_filter: Optional[str] = None,
        grab: bool = False,
        allow_repeat: bool = True,
    ) -> None:
        super().__init__()
        self._device_paths = list(device_paths) if device_paths else None
        self._name_filter = name_filter.lower() if name_filter else None
        self._grab = grab
        self._allow_repeat = allow_repeat
        self._devices: List = []

    @staticmethod
    def is_available() -> bool:
        try:
            import evdev  # noqa: F401
        except ImportError:
            return False
        return True

    def _open_devices(self):
        import evdev
        from evdev import ecodes

        paths = self._device_paths or evdev.list_devices()
        devices = []
        for path in paths:
            try:
                dev = evdev.InputDevice(path)
            except (OSError, PermissionError) as exc:
                log.warning("cannot open input device %s: %s", path, exc)
                continue
            caps = dev.capabilities()
            if ecodes.EV_KEY not in caps:
                dev.close()
                continue
            if self._name_filter and self._name_filter not in (dev.name or "").lower():
                dev.close()
                continue
            if self._grab:
                try:
                    dev.grab()
                except OSError:
                    log.warning("could not grab %s (continuing ungrabbed)", dev.name)
            log.info("listening to input device: %s (%s)", dev.name, path)
            devices.append(dev)
        return devices

    def _run(self) -> None:
        if not self.is_available():
            log.error("evdev is not installed; keyboard/remote input disabled")
            return
        self._devices = self._open_devices()
        if not self._devices:
            log.warning("no usable input devices found for the keyboard backend")
            return

        from evdev import ecodes

        fd_to_device = {dev.fd: dev for dev in self._devices}
        while not self.stopping:
            try:
                r, _, _ = select.select(fd_to_device, [], [], 0.5)
            except (OSError, ValueError):
                break
            for fd in r:
                dev = fd_to_device.get(fd)
                if dev is None:
                    continue
                try:
                    for event in dev.read():
                        if event.type != ecodes.EV_KEY:
                            continue
                        self._handle_key_event(event)
                except OSError:
                    log.warning("input device %s disappeared", getattr(dev, "path", "?"))
                    fd_to_device.pop(fd, None)

    def _handle_key_event(self, event) -> None:
        from evdev import ecodes

        if event.value == _KEY_DOWN:
            pass
        elif event.value == _KEY_REPEAT and self._allow_repeat:
            pass
        else:
            return  # key-up, or repeats when disabled

        key_name = _code_to_name(ecodes.KEY, event.code)
        if key_name is None:
            return
        input_event = evdev_key_to_event(key_name)
        if input_event is None:
            return
        # Only volume/channel keys should auto-repeat when held; ignore repeats
        # for digits, enter, power, etc. so a held button doesn't misbehave.
        from ..actions import Action

        if event.value == _KEY_REPEAT and input_event.action not in (
            Action.VOLUME_UP,
            Action.VOLUME_DOWN,
            Action.CHANNEL_UP,
            Action.CHANNEL_DOWN,
        ):
            return
        self.emit(input_event)

    def _close(self) -> None:
        for dev in self._devices:
            try:
                if self._grab:
                    dev.ungrab()
            except OSError:
                pass
            try:
                dev.close()
            except OSError:
                pass
        self._devices = []


def _code_to_name(key_table, code: int) -> Optional[str]:
    """evdev's KEY table maps a code to a name or a list of aliases."""
    name = key_table.get(code)
    if name is None:
        return None
    if isinstance(name, (list, tuple)):
        return name[0] if name else None
    return name


__all__ = ["KeyboardBackend"]
