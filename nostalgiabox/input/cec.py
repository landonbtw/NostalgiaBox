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

from ..actions import Action
from .base import InputBackend
from .keymap import cec_key_to_event

log = logging.getLogger(__name__)

_KEY_PRESSED_RE = re.compile(r"key pressed:\s*(.+?)\s*(?:\(|$)", re.IGNORECASE)

# cec-client interactive commands. One process both reads keys and sends them;
# a second cec-client cannot share the adapter.
_CEC_VOLUME_COMMANDS = {
    "volup": "volume up",
    "voldown": "volume down",
    "mute": "mute",
}

# Actions that are volume on the way in. When we are the ones sending volup /
# voldown / mute, cec-client echoes them back as "key pressed:" lines. Handling
# that echo would send the command again.
_VOLUME_ACTIONS = frozenset({Action.VOLUME_UP, Action.VOLUME_DOWN, Action.MUTE})


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
        # Set by the app before start() when volume keys are forwarded to the
        # TV, so the echo of our own volup/voldown/mute is not a new press.
        self.ignore_volume_keys = False

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
                # stdin stays open so send_command can write volup/voldown/mute.
                stdin=subprocess.PIPE,
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
        if event is None:
            return
        if self.ignore_volume_keys and event.action in _VOLUME_ACTIONS:
            return
        self.emit(event)

    def send_command(self, command: str) -> bool:
        """Send one cec-client command, such as ``volup``, ``voldown``, or ``mute``.

        Returns False when the client is not running. The caller leaves the Pi
        volume unchanged in that case.
        """
        proc = self._proc
        if proc is None or proc.stdin is None:
            return False
        line = str(command).strip().lower()
        if line not in _CEC_VOLUME_COMMANDS:
            log.warning("refusing unknown HDMI-CEC command %r", command)
            return False
        try:
            proc.stdin.write(line + "\n")
            proc.stdin.flush()
            return True
        except (OSError, ValueError):
            log.warning("HDMI-CEC command %s failed", line, exc_info=True)
            return False

    def _close(self) -> None:
        proc = self._proc
        if proc is None:
            return
        self._proc = None
        try:
            if proc.stdin is not None:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
        except OSError:
            pass


__all__ = ["CecBackend"]
