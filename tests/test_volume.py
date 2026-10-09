"""Volume stepping, the single saved level, and TV-vs-Pi routing."""

import pytest

from nostalgiabox.actions import Action, InputEvent
from nostalgiabox.app import TVApp
from nostalgiabox.config import config_from_dict
from nostalgiabox.input.cec import CecBackend
from nostalgiabox.input.keyboard import key_event_should_emit
from nostalgiabox.input.manager import InputManager
from nostalgiabox.player import build_mpv_options, playback_audio_options
from nostalgiabox.volume import resolve_volume_control
from tests.helpers import make_show
from tests.test_app import build_app, send


def _steps(values, action, *, allow_repeat=True):
    return sum(
        key_event_should_emit(value, action, allow_repeat=allow_repeat) for value in values
    )


def test_one_volume_press_is_one_step_even_with_repeats_and_no_key_up():
    # evdev: 1 = pressed, 2 = autorepeat, 0 = released.
    # A short hold, or a Flirc that never sends key-up, must not keep stepping.
    assert _steps([1, 2, 2, 2, 0], Action.VOLUME_UP) == 1
    assert _steps([1, 2, 2, 0], Action.VOLUME_DOWN) == 1
    assert _steps([1, 2, 0], Action.MUTE) == 1
    assert _steps([2, 2, 2], Action.VOLUME_UP) == 0
    assert _steps([0], Action.VOLUME_DOWN) == 0
    assert key_event_should_emit(1, Action.VOLUME_UP, allow_repeat=False) is True


def test_channel_keys_still_repeat_while_held():
    assert _steps([1, 2, 2, 0], Action.CHANNEL_UP) == 3
    assert _steps([1, 2, 2, 0], Action.CHANNEL_DOWN) == 3
    assert _steps([1, 2, 2, 0], Action.CHANNEL_UP, allow_repeat=False) == 1


def test_resolve_volume_control_matrix():
    assert resolve_volume_control("auto", cec_available=True) == "tv"
    assert resolve_volume_control("auto", cec_available=False) == "pi"
    assert resolve_volume_control("tv", cec_available=True) == "tv"
    assert resolve_volume_control("tv", cec_available=False) == "pi"
    assert resolve_volume_control("pi", cec_available=True) == "pi"
    assert resolve_volume_control("  TV ", cec_available=True) == "tv"
    with pytest.raises(ValueError, match="volume_control"):
        resolve_volume_control("alsa", cec_available=True)


def test_two_presses_take_exactly_two_steps(tmp_path):
    app, player, _ = build_app(tmp_path, initial_volume=70, volume_step=5)
    app.start()
    assert app.volume_mode == "pi"
    send(app, Action.VOLUME_UP)
    send(app, Action.VOLUME_UP)
    assert app.volume == 80
    assert player.volume == 80
    send(app, Action.VOLUME_DOWN)
    assert app.volume == 75
    assert player.volume == 75


def test_level_is_restored_when_a_new_file_resets_the_player(tmp_path):
    app, player, _ = build_app(tmp_path, initial_volume=80, volume_step=5)
    app.start()
    send(app, Action.VOLUME_DOWN)  # 75, and unmute path is a no-op
    assert app.volume == 75

    real_play = player.play

    def play_and_drop(path, *, start=0.0):
        real_play(path, start=start)
        # A new file that brings its own gain, the way mpv can after loadfile.
        player.volume = 0
        player.muted = True

    player.play = play_and_drop
    player.finish_current()
    app.step()
    assert app.volume == 75
    assert player.volume == 75
    assert player.muted is False


def test_level_survives_a_channel_change(tmp_path):
    app, player, clock = build_app(tmp_path, initial_volume=70, volume_step=5)
    app.start()
    send(app, Action.VOLUME_UP)  # 75
    send(app, Action.CHANNEL_UP)  # preloads; the cut happens after the bridge
    player.volume = 40
    clock.advance(1.0)
    app.step()
    assert app.lineup.current.number == 3
    assert app.volume == 75
    assert player.volume == 75


class _FakeCec:
    name = "cec"

    def __init__(self, *, ok=True):
        self.commands = []
        self.ignore_volume_keys = False
        self.ok = ok
        self.started = False

    def send_command(self, command: str) -> bool:
        self.commands.append(command)
        return self.ok

    def start(self, queue):
        self.started = True

    def stop(self):
        pass


def _app_with_cec(tmp_path, cec, **overrides):
    for name in ("dragon", "arthur"):
        make_show(tmp_path, name, 2)
    data = {
        "shuffle_seed": 1,
        "start_channel": 2,
        "start_offset": 0,
        "power_off_command": [],
        "initial_volume": 100,
        "channels": [
            {"number": 2, "name": "Dragon Tales", "path": str(tmp_path / "dragon")},
            {"number": 3, "name": "Arthur", "path": str(tmp_path / "arthur")},
        ],
    }
    data.update(overrides)
    from nostalgiabox.player import MockPlayer

    player = MockPlayer()
    app = TVApp(config_from_dict(data), player, InputManager([cec]))
    return app, player


def test_tv_mode_sends_one_cec_command_per_press_and_leaves_pi_at_100(tmp_path):
    cec = _FakeCec()
    app, player = _app_with_cec(tmp_path, cec, volume_control="tv")
    app.start()
    assert app.volume_mode == "tv"
    assert cec.ignore_volume_keys is True
    assert cec.started is True
    assert player.volume == 100

    send(app, Action.VOLUME_UP)
    send(app, Action.VOLUME_UP)
    send(app, Action.VOLUME_DOWN)
    send(app, Action.MUTE)
    # Volume-down at a full Pi must not power the box off; these keys are the TV's.
    send(app, Action.VOLUME_DOWN)

    assert cec.commands == ["volup", "volup", "voldown", "mute", "voldown"]
    assert app.volume == 100
    assert player.volume == 100
    assert app.muted is False
    assert app.powered_off is False
    # The message overlay shows the latest press only.
    assert "TV VOL -" in player.overlays.get(4, "")


def test_tv_mode_does_not_change_pi_volume_when_cec_send_fails(tmp_path):
    cec = _FakeCec(ok=False)
    app, player = _app_with_cec(tmp_path, cec, volume_control="auto")
    app.start()
    assert app.volume_mode == "tv"
    send(app, Action.VOLUME_UP)
    assert app.volume == 100
    assert player.volume == 100
    assert app.powered_off is False
    assert "NO TV VOLUME" in player.overlays.get(4, "")


def test_tv_requested_without_cec_falls_back_to_pi(tmp_path):
    app, player, _ = build_app(tmp_path, volume_control="tv", initial_volume=100)
    app.start()
    assert app.volume_mode == "pi"
    send(app, Action.VOLUME_DOWN)
    assert app.volume == 95
    assert player.volume == 95


def test_pi_mode_ignores_a_present_cec_sender(tmp_path):
    cec = _FakeCec()
    app, player = _app_with_cec(tmp_path, cec, volume_control="pi", initial_volume=50)
    app.start()
    assert app.volume_mode == "pi"
    assert cec.ignore_volume_keys is False
    send(app, Action.VOLUME_UP)
    assert cec.commands == []
    assert app.volume == 55
    assert player.volume == 55


def test_cec_echo_of_volume_keys_is_dropped_while_passthrough_is_on():
    backend = CecBackend()
    backend.ignore_volume_keys = True
    backend._handle_line("DEBUG: key pressed: volume up (65)")
    backend._handle_line("key pressed: Volume Down")
    backend._handle_line("key pressed: mute")
    backend._handle_line("key pressed: up (1)")
    assert backend._queue.qsize() == 1
    assert backend._queue.get_nowait().action == Action.CHANNEL_UP


def test_cec_volume_keys_still_reach_the_app_in_pi_mode():
    backend = CecBackend()
    backend._handle_line("key pressed: volume up (65)")
    event = backend._queue.get_nowait()
    assert event == InputEvent(Action.VOLUME_UP)


def test_send_command_writes_one_line_and_rejects_unknown():
    backend = CecBackend()
    assert backend.send_command("volup") is False

    class _Stdin:
        def __init__(self):
            self.buf = ""

        def write(self, text):
            self.buf += text

        def flush(self):
            pass

    class _Proc:
        def __init__(self):
            self.stdin = _Stdin()

    backend._proc = _Proc()
    assert backend.send_command("volup") is True
    assert backend.send_command("Voldown") is True
    assert backend.send_command("mute") is True
    assert backend.send_command("tx 10:44:41") is False
    assert backend.send_command("volup\nvoldown") is False
    assert backend._proc.stdin.buf == "volup\nvoldown\nmute\n"


def test_mpv_audio_is_unity_and_has_no_loudness_filter():
    audio = playback_audio_options()
    assert audio["volume"] == 100
    assert audio["volume_max"] == 100
    assert audio["replaygain"] == "no"
    assert audio["input_terminal"] is False

    options = build_mpv_options()
    for key, value in audio.items():
        assert options[key] == value
    assert options["input_default_bindings"] is False
    assert options["input_vo_keyboard"] is False
    blob = " ".join(str(v).lower() for v in options.values())
    assert "loudnorm" not in blob
    assert "dynaudnorm" not in blob
    assert "acompressor" not in blob
    # The 4:3 fit is a video filter, not an audio gain stage.
    assert options["vf"].startswith("lavfi=[scale=")
    assert "af" not in options
