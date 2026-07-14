"""HDMI-CEC input: use the TV's own remote to drive the box.

Many TVs can forward remote button presses to attached HDMI devices over CEC
(Samsung "Anynet+", LG "SimpLink", Sony "BRAVIA Sync", etc.). On a Raspberry Pi
the easiest way to receive those is libCEC's ``cec-client`` utility, which
prints a line like ``key pressed: up (1)`` for every button. This backend spawns
``cec-client`` and turns those lines into actions - so the kids can just use the
TV remote they already point at the screen, no separate remote required.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from typing import List, Optional

from .base import InputBackend
from .keymap import cec_key_to_event

log = logging.getLogger(__name__)

_KEY_PRESSED_RE = re.compile(r"key pressed:\s*(.+?)\s*(?:\(|$)", re.IGNORECASE)


class CecBackend(InputBackend):
    """Reads TV-remote button presses forwarded over HDMI-CEC."""

    name = "cec"

    def __init__(
        self,
        *,
        binary: str = "cec-client",
        osd_name: str = "NostalgiaBox",
        extra_args: Optional[List[str]] = None,
    ) -> None:
        super().__init__()
        self._binary = binary
        self._osd_name = osd_name
        self._extra_args = list(extra_args) if extra_args else []
        self._proc: Optional[subprocess.Popen] = None

    @staticmethod
    def is_available(binary: str = "cec-client") -> bool:
        return shutil.which(binary) is not None

    def _run(self) -> None:
        if not self.is_available(self._binary):
            log.info("%s not found; HDMI-CEC input disabled", self._binary)
            return
        cmd = [
            self._binary,
            "-t", "p",            # register as a Playback device
            "-o", self._osd_name,  # the name the TV shows for this device
            "-d", "8",            # log level: include the key-press traffic
            *self._extra_args,
        ]
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            log.warning("could not start %s: %s", self._binary, exc)
            return

        log.info("HDMI-CEC input active via %s", self._binary)
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            if self.stopping:
                break
            self._handle_line(line)

    def _handle_line(self, line: str) -> None:
        match = _KEY_PRESSED_RE.search(line)
        if not match:
            return
        event = cec_key_to_event(match.group(1))
        if event is not None:
            self.emit(event)

    def _close(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        except OSError:
            pass
        self._proc = None


__all__ = ["CecBackend"]
