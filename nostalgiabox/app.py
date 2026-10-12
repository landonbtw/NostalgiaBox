"""The television itself: the state machine that ties everything together.

:class:`TVApp` owns the channel lineup, the player, the overlays and the input
queue, and turns remote-control actions into TV behaviour: changing channels
(with a burst of static and a channel banner), adjusting and muting the volume,
direct channel entry by number, an info banner, a "last channel" jump, and a
standby/off mode. When an episode ends it automatically rolls into the next one
on that channel's shuffle, so the box never stops "broadcasting".

The class is written to be testable without a display: pass it a
:class:`~nostalgiabox.player.MockPlayer` and a fake clock and you can single-step
the whole thing (see ``step`` / ``handle_event`` / ``process_pending``).
"""

from __future__ import annotations

import logging
import queue
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional

from .actions import Action, InputEvent
from .channel import Channel, ChannelLineup, PlayRequest, build_lineup
from .config import Config
from .input.manager import InputManager, create_backends
from .overlay import OverlayManager
from .player import END_EOF, END_ERROR, MockPlayer, Player
from .volume import resolve_volume_control
from .static_gen import (
    COLORBARS_FILENAME,
    DEFAULT_ASSETS_DIR,
    GLITCH_FILENAME,
    STATIC_FILENAME,
)

log = logging.getLogger(__name__)


class TVApp:
    """The retro-TV application state machine."""

    def __init__(
        self,
        config: Config,
        player: Player,
        input_manager: InputManager,
        *,
        overlay: Optional[OverlayManager] = None,
        clock: Callable[[], float] = time.monotonic,
        assets_dir: Optional[Path] = None,
    ) -> None:
        self.config = config
        self.player = player
        self.input = input_manager
        self.overlay = overlay or OverlayManager(player, config, clock=clock)
        self._clock = clock

        self.lineup: ChannelLineup = build_lineup(config)

        # Runtime state. ``volume`` / ``muted`` are the only Pi level. mpv is
        # told this number at startup and again after every file; it is not
        # read back, and nothing else (ALSA, a saved per-show gain) writes it.
        self.volume = config.initial_volume
        self.muted = False
        # "tv" sends volup/voldown/mute over HDMI-CEC and leaves this level
        # alone. "pi" steps ``self.volume``. Refined in start() once we know
        # whether a CEC backend exists.
        self.volume_mode = "pi"
        # "" until a settled choice is logged, so a CEC probe still in flight
        # does not announce "no TV" before the television has had a chance to
        # answer.
        self._volume_logged = ""
        self.standby = False
        self.powered_off = False
        self._playing_path: Optional[Path] = None
        self._last_channel_number: Optional[int] = None
        self._running = False

        # Direct channel entry ("type 1 then 2 -> channel 12").
        self._digit_buffer = ""
        self._digit_deadline = 0.0
        self._digit_entry_timeout = 2.0
        # In-order channels checkpoint their place every few seconds so a
        # reboot mid-episode does not lose the whole show.
        self._next_progress_save = 0.0

        # Pending "bridge" switch: keep the old show playing until this deadline,
        # then cut to the channel that was preloaded. The channel banner is shown
        # at the moment of the cut-over, not when the button is pressed.
        self._switch_deadline: Optional[float] = None
        self._pending_banner: Optional[tuple[int, str]] = None

        # Playback-finished events from the player (may arrive on any thread).
        self._ended: "queue.Queue[str]" = queue.Queue()
        self.player.on_end = self._ended.put

        # Filler assets.
        self._assets_dir = assets_dir or config.assets_dir or DEFAULT_ASSETS_DIR
        self._colorbars_path = self._resolve_asset(COLORBARS_FILENAME)
        # The channel-change transition clip depends on the configured effect.
        self._transition_path = self._resolve_transition_asset()

    # -- construction -------------------------------------------------------
    @classmethod
    def from_config(
        cls,
        config: Config,
        *,
        player: Optional[Player] = None,
        input_manager: Optional[InputManager] = None,
        dry_run: bool = False,
        assets_dir: Optional[Path] = None,
    ) -> "TVApp":
        """Build a fully wired app, creating real hardware backends by default.

        ``dry_run`` swaps in a :class:`MockPlayer` and disables all real input
        backends (a stdin backend is added if a TTY is available), which is how
        the box can be exercised on a development machine.
        """
        if player is None:
            if dry_run:
                player = MockPlayer(verbose=True)
            else:
                from .crt import write_shader
                from .player import MpvPlayer

                assets = assets_dir or config.assets_dir or DEFAULT_ASSETS_DIR
                shader_path = write_shader(config.crt)
                player = MpvPlayer(
                    glsl_shaders=str(shader_path) if shader_path else None,
                    fonts_dir=assets / "fonts",
                    force_4_3=config.force_4_3,
                    audio_device=config.audio_device,
                )

        if input_manager is None:
            if dry_run:
                backends = create_backends({"keyboard": False, "cec": False, "stdin": True})
            else:
                backends = create_backends(config.input_options)
            input_manager = InputManager(backends)

        return cls(config, player, input_manager, assets_dir=assets_dir)

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> None:
        """Power on: set volume, start input, and tune to the first channel."""
        self._resolve_volume_mode()
        self._apply_output_volume()
        self.input.start()
        self._select_start_channel()
        self.tune_current(show_static=False)

    def run(self) -> None:
        """Run the blocking main loop until a QUIT action is received."""
        self.start()
        self._running = True
        log.info("NostalgiaBox is on the air. %d channels.", len(self.lineup))
        try:
            while self._running:
                self.step(block=True)
        except KeyboardInterrupt:  # pragma: no cover - interactive convenience
            log.info("interrupted; shutting down")
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        self._running = False
        try:
            self._remember_position()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.overlay.clear_all()
        except Exception:  # noqa: BLE001
            pass
        self.input.stop()
        self.player.close()

    # -- main-loop step (small and testable) --------------------------------
    def step(self, *, block: bool = False, timeout: float = 0.1) -> None:
        """Advance the state machine by one iteration.

        Handles overlay expiry, channel-entry timeouts, finished episodes, and
        at most one queued input event.
        """
        now = self._clock()
        self._resolve_volume_mode()
        self._maybe_checkpoint(now)
        self.overlay.tick()
        self._maybe_commit_switch(now)
        self._maybe_commit_digits(now)
        self._drain_playback_events()

        event = self.input.get(timeout=timeout if block else 0.0)
        if event is not None:
            self.handle_event(event)

    def _maybe_commit_switch(self, now: float) -> None:
        """Cut over to the preloaded channel once the bridge window has elapsed."""
        if self._switch_deadline is not None and now >= self._switch_deadline:
            self._switch_deadline = None
            self.player.commit_switch()
            self._apply_output_volume()
            # Flash the channel banner right as the picture actually changes.
            if self._pending_banner is not None:
                self.overlay.show_channel_bug(*self._pending_banner)
                self._pending_banner = None

    # -- input handling -----------------------------------------------------
    def handle_event(self, event: InputEvent) -> None:
        action = event.action

        if action == Action.QUIT:
            self._running = False
            return
        if action == Action.POWER:
            self._toggle_standby()
            return

        # While in standby, ignore everything except POWER/QUIT (handled above).
        if self.standby:
            return

        handlers = {
            Action.CHANNEL_UP: self._channel_up,
            Action.CHANNEL_DOWN: self._channel_down,
            Action.VOLUME_UP: self._volume_up,
            Action.VOLUME_DOWN: self._volume_down,
            Action.MUTE: self._toggle_mute,
            Action.INFO: self._show_info,
            Action.LAST_CHANNEL: self._jump_last_channel,
            Action.ENTER: self._confirm_digits,
        }
        if action == Action.DIGIT:
            self._push_digit(event.value or 0)
        else:
            handler = handlers.get(action)
            if handler is not None:
                handler()

    # -- channel changing ---------------------------------------------------
    def _channel_up(self) -> None:
        self._remember_position()
        self._last_channel_number = self.lineup.current.number
        self.lineup.up()
        self.tune_current()

    def _channel_down(self) -> None:
        self._remember_position()
        self._last_channel_number = self.lineup.current.number
        self.lineup.down()
        self.tune_current()

    def _jump_last_channel(self) -> None:
        if self._last_channel_number is None:
            return
        target = self._last_channel_number
        if not self.lineup.has_number(target):
            return
        self._remember_position()
        self._last_channel_number = self.lineup.current.number
        self.lineup.select_number(target)
        self.tune_current()

    def select_channel_number(self, number: int) -> bool:
        """Tune directly to a channel number. Returns False if it doesn't exist."""
        if not self.lineup.has_number(number):
            self.overlay.show_message(f"CH {number:02d}  -  NO CHANNEL")
            return False
        if number == self.lineup.current.number:
            self._show_info()
            return True
        self._remember_position()
        self._last_channel_number = self.lineup.current.number
        self.lineup.select_number(number)
        self.tune_current()
        return True

    def tune_current(self, *, show_static: bool = True) -> None:
        """Tune into the currently selected channel."""
        channel = self.lineup.current
        self.overlay.clear_standby()

        request = channel.tune_in()
        self._persist_if_in_order(channel)
        self._pending_banner = None

        if request is None:
            # No episodes on this channel: show the "no signal" screen.
            self.overlay.show_channel_bug(channel.number, channel.name)
            self._show_no_signal(channel)
            return

        if not show_static:
            # Not a channel change (first tune / waking from standby): play now.
            self._switch_deadline = None
            self.overlay.show_channel_bug(channel.number, channel.name)
            self._play_request(request)
        elif self._transition_path is not None:
            # Transition clip (glitch/static) + preloaded episode.
            self._switch_deadline = None
            self.overlay.show_channel_bug(channel.number, channel.name)
            self._playing_path = request.path
            self.player.play_transition(
                self._transition_path,
                request.path,
                start=request.start,
                static_seconds=self.config.transition_duration,
            )
            self._apply_output_volume()
        elif self.config.bridge_seconds > 0 and self._playing_path is not None:
            # No transition effect: keep the current show playing while the next
            # channel preloads, then cut over (no frozen frame). The banner is
            # shown at the cut-over (see _maybe_commit_switch), not right now.
            self._playing_path = request.path
            self.player.preload_next(request.path, start=request.start)
            self._switch_deadline = self._clock() + self.config.bridge_seconds
            self._pending_banner = (channel.number, channel.name)
        else:
            self._switch_deadline = None
            self.overlay.show_channel_bug(channel.number, channel.name)
            self._play_request(request)

    def _play_request(self, request: PlayRequest) -> None:
        self._playing_path = request.path
        self.player.play(request.path, start=request.start)
        self._apply_output_volume()

    def _show_no_signal(self, channel: Channel) -> None:
        self._switch_deadline = None
        self._pending_banner = None
        self._playing_path = None
        if self._colorbars_path is not None:
            self.player.play_loop(self._colorbars_path)
        else:
            self.player.stop()
        self._apply_output_volume()
        self.overlay.show_message(
            f"CH {channel.number:02d}  {channel.name}  -  NO SIGNAL", duration=6.0
        )

    # -- volume -------------------------------------------------------------
    def _resolve_volume_mode(self) -> None:
        """Pick TV passthrough or the Pi knob.

        ``auto`` uses the TV only after cec-client has actually found one.
        While that probe is still running, and when no TV answers, the Pi
        volume is used and nothing is drawn on screen. The ignore flag is set
        only in TV mode: cec-client echoes a volume key it just transmitted,
        and treating that echo as another press would run the level away.
        """
        cec = self._cec_backend()
        presence = getattr(cec, "tv_present", None) if cec is not None else False
        requested = str(self.config.volume_control).lower()
        # None means "still looking". Stay on the Pi quietly until it settles.
        if presence is None and requested != "pi":
            self.volume_mode = "pi"
            if cec is not None:
                cec.ignore_volume_keys = False
            return
        tv = presence is True
        self.volume_mode = resolve_volume_control(
            self.config.volume_control, cec_available=tv
        )
        if cec is not None:
            cec.ignore_volume_keys = self.volume_mode == "tv"
        if self.volume_mode == self._volume_logged:
            return
        self._volume_logged = self.volume_mode
        if self.volume_mode == "tv":
            log.info("volume keys control the TV over HDMI-CEC; Pi output stays at %s", self.volume)
        elif requested != "pi":
            log.info("no HDMI-CEC television; the remote controls the Pi volume")

    def _cec_backend(self):
        for backend in self.input.backends:
            send = getattr(backend, "send_command", None)
            if callable(send):
                return backend
        return None

    def _apply_output_volume(self) -> None:
        """Push the remembered Pi level. Does not move the on-screen bar."""
        self.player.set_volume(self.volume)
        self.player.set_mute(self.muted)

    def _volume_up(self) -> None:
        self._resolve_volume_mode()
        if self.volume_mode == "tv":
            self._tv_volume("volup", "TV VOL +")
            return
        self._set_volume(self.volume + self.config.volume_step, unmute=True)

    def _volume_down(self) -> None:
        self._resolve_volume_mode()
        if self.volume_mode == "tv":
            self._tv_volume("voldown", "TV VOL -")
            return
        # Pi mode only: one press below zero cleanly powers off the box.
        # In TV mode the keys never move this counter, so they cannot shut down.
        if self.config.power_off_on_min_volume and not self.muted and self.volume <= 0:
            self._power_off()
            return
        self._set_volume(self.volume - self.config.volume_step, unmute=True)

    def _set_volume(self, value: int, *, unmute: bool = False) -> None:
        self.volume = max(0, min(100, value))
        if unmute and self.muted:
            self.muted = False
        self._apply_output_volume()
        self.overlay.show_volume(self.volume, self.muted)

    def _tv_volume(self, command: str, message: str) -> None:
        """One Flirc volume press becomes one CEC command. The Pi level stays."""
        cec = self._cec_backend()
        sent = bool(cec.send_command(command)) if cec is not None else False
        if sent:
            self.overlay.show_message(message)
            return
        log.warning("HDMI-CEC %s was not sent; Pi volume left at %s", command, self.volume)
        self.overlay.show_message("NO TV VOLUME")

    def _power_off(self) -> None:
        """Cleanly shut the Pi down so it's safe to unplug."""
        log.info("powering off (volume floor)")
        self.powered_off = True
        self._switch_deadline = None
        self._pending_banner = None
        try:
            self.overlay.clear_all()
            self.overlay.show_message("GOODBYE", duration=0)
            self.player.stop()
        except Exception:  # noqa: BLE001
            pass
        self._run_power_off_command()
        self._running = False  # exit the main loop

    def _run_power_off_command(self) -> None:
        command = list(self.config.power_off_command)
        if not command:
            return  # disabled / test mode
        try:
            subprocess.Popen(command)
        except Exception:  # noqa: BLE001
            log.exception("power-off command failed: %s", command)

    def _toggle_mute(self) -> None:
        self._resolve_volume_mode()
        if self.volume_mode == "tv":
            self._tv_volume("mute", "TV MUTE")
            return
        self.muted = not self.muted
        self._apply_output_volume()
        self.overlay.show_volume(self.volume, self.muted)

    # -- info / standby -----------------------------------------------------
    def _show_info(self) -> None:
        channel = self.lineup.current
        self.overlay.show_channel_bug(channel.number, channel.name)

    def _toggle_standby(self) -> None:
        self.standby = not self.standby
        if self.standby:
            self._remember_position()
            self._switch_deadline = None
            self._pending_banner = None
            self.player.stop()
            self.overlay.clear_all()
            self.overlay.show_standby()
        else:
            self.overlay.clear_standby()
            self.tune_current(show_static=False)

    # -- direct channel entry ----------------------------------------------
    def _push_digit(self, digit: int) -> None:
        self._digit_buffer = (self._digit_buffer + str(digit))[-3:]
        self._digit_deadline = self._clock() + self._digit_entry_timeout
        self.overlay.show_message(f"CH {self._digit_buffer}_", duration=self._digit_entry_timeout)

    def _confirm_digits(self) -> None:
        if not self._digit_buffer:
            return
        number = int(self._digit_buffer)
        self._digit_buffer = ""
        self._digit_deadline = 0.0
        self.select_channel_number(number)

    def _maybe_commit_digits(self, now: float) -> None:
        if self._digit_buffer and now >= self._digit_deadline:
            self._confirm_digits()

    # -- playback-finished handling ----------------------------------------
    def _drain_playback_events(self) -> None:
        advanced = False
        while True:
            try:
                reason = self._ended.get_nowait()
            except queue.Empty:
                break
            # Coalesce: only advance once even if several events queued up.
            if reason in (END_EOF, END_ERROR) and not advanced and not self.standby:
                self._advance_current()
                advanced = True

    def _advance_current(self) -> None:
        channel = self.lineup.current
        request = channel.advance()
        self._persist_if_in_order(channel)
        if request is None:
            self._show_no_signal(self.lineup.current)
        else:
            self._play_request(request)

    # -- helpers ------------------------------------------------------------
    def _remember_position(self) -> None:
        channel = self.lineup.current
        in_order = channel.config.order == "in_order" and channel.tune_in_mode != "broadcast"
        if self.config.tune_in != "resume" and not in_order:
            return
        if self._playing_path is None:
            return
        pos = self.player.get_time_pos()
        if pos is None:
            return
        channel.remember(self._playing_path, pos)
        if in_order:
            self._persist_if_in_order(channel)

    def _maybe_checkpoint(self, now: float) -> None:
        if now < self._next_progress_save:
            return
        self._next_progress_save = now + 5.0
        channel = self.lineup.current
        if channel.config.order != "in_order" or channel.tune_in_mode == "broadcast":
            return
        if self._playing_path is None:
            return
        pos = self.player.get_time_pos()
        if pos is None:
            return
        channel.remember(self._playing_path, pos)
        self._persist_if_in_order(channel)

    def _persist_if_in_order(self, channel) -> None:
        """Write an in-order channel's place. Shuffle channels are not saved."""
        state = getattr(self.lineup, "state", None)
        if state is None or channel.config.order != "in_order":
            return
        state.set(channel.config.path, channel.bookmark())
        state.save()

    def _select_start_channel(self) -> None:
        if self.config.start_channel is not None and self.lineup.has_number(
            self.config.start_channel
        ):
            self.lineup.select_number(self.config.start_channel)

    def _resolve_asset(self, filename: str) -> Optional[Path]:
        path = self._assets_dir / filename
        return path if path.is_file() else None

    def _resolve_transition_asset(self) -> Optional[Path]:
        effect = self.config.transition_effect
        if effect == "none":
            return None
        filename = GLITCH_FILENAME if effect == "glitch" else STATIC_FILENAME
        return self._resolve_asset(filename)


def run_from_config(config: Config, *, dry_run: bool = False) -> None:
    """Convenience entry point used by the CLI."""
    if not config.channels:
        root = config.media_root or "/media/nostalgiabox"
        raise RuntimeError(
            "No show folders found. Put one folder per show in "
            f"{root} (the folder name is the channel name), then start again."
        )
    app = TVApp.from_config(config, dry_run=dry_run)
    app.run()


__all__ = ["TVApp", "run_from_config"]
