import pytest

from nostalgiabox.actions import Action, InputEvent
from nostalgiabox.app import TVApp
from nostalgiabox.config import config_from_dict
from nostalgiabox.input.manager import InputManager
from nostalgiabox.player import END_EOF, MockPlayer
from nostalgiabox.stall import ProblemLog
from tests.helpers import FakeClock, make_show


def build_app(tmp_path, *, assets_dir=None, **overrides):
    for name in ("dragon", "arthur", "rugrats"):
        make_show(tmp_path, name, 4)
    data = {
        "shuffle_seed": 7,
        "start_channel": 2,
        "start_offset": 0,  # keep test assertions on start=0 unless overridden
        "power_off_command": [],  # no-op in tests (never actually shut down)
        "channels": [
            {"number": 2, "name": "Dragon Tales", "path": str(tmp_path / "dragon")},
            {"number": 3, "name": "Arthur", "path": str(tmp_path / "arthur")},
            {"number": 4, "name": "Rugrats", "path": str(tmp_path / "rugrats")},
        ],
    }
    data.update(overrides)
    config = config_from_dict(data)
    clock = FakeClock()
    player = MockPlayer()
    app = TVApp(
        config,
        player,
        InputManager([]),
        clock=clock,
        assets_dir=assets_dir,
    )
    return app, player, clock


def send(app, action, value=None):
    app.handle_event(InputEvent(action, value))


def test_start_tunes_to_start_channel_and_plays(tmp_path):
    app, player, _ = build_app(tmp_path)
    app.start()
    assert app.lineup.current.number == 2
    assert player.current is not None  # an episode is playing
    assert player.volume == 100
    assert player.overlays.get(1) and "Dragon Tales" in player.overlays[1]


def test_channel_up_down_wraps(tmp_path):
    app, player, _ = build_app(tmp_path)
    app.start()
    send(app, Action.CHANNEL_UP)
    assert app.lineup.current.number == 3
    send(app, Action.CHANNEL_UP)
    assert app.lineup.current.number == 4
    send(app, Action.CHANNEL_UP)
    assert app.lineup.current.number == 2  # wrapped
    send(app, Action.CHANNEL_DOWN)
    assert app.lineup.current.number == 4  # wrapped back


def test_volume_controls(tmp_path):
    app, player, _ = build_app(tmp_path, initial_volume=70)
    app.start()
    send(app, Action.VOLUME_UP)
    assert app.volume == 75 and player.volume == 75
    send(app, Action.VOLUME_DOWN)
    assert app.volume == 70
    # volume overlay was drawn
    assert "Volume" in player.overlays[2]


def test_volume_clamps(tmp_path):
    app, player, _ = build_app(tmp_path, initial_volume=98, volume_step=5)
    app.start()
    send(app, Action.VOLUME_UP)
    assert app.volume == 100
    for _ in range(30):
        send(app, Action.VOLUME_DOWN)
    assert app.volume == 0


def test_volume_down_at_zero_powers_off(tmp_path):
    app, player, _ = build_app(tmp_path, initial_volume=10, volume_step=5)
    app.start()
    send(app, Action.VOLUME_DOWN)   # 10 -> 5
    send(app, Action.VOLUME_DOWN)   # 5 -> 0
    assert app.volume == 0 and not app.powered_off
    send(app, Action.VOLUME_DOWN)   # one more at 0 -> power off
    assert app.powered_off is True
    assert app._running is False
    assert player.current is None   # playback stopped


def test_power_off_disabled(tmp_path):
    app, player, _ = build_app(
        tmp_path, initial_volume=0, power_off_on_min_volume=False
    )
    app.start()
    send(app, Action.VOLUME_DOWN)   # at 0, but feature disabled
    assert app.powered_off is False


def test_mute_toggle_and_unmute_on_volume(tmp_path):
    app, player, _ = build_app(tmp_path)
    app.start()
    send(app, Action.MUTE)
    assert app.muted and player.muted
    send(app, Action.VOLUME_UP)  # changing volume unmutes
    assert not app.muted and not player.muted


def test_direct_channel_entry_with_enter(tmp_path):
    app, player, _ = build_app(tmp_path)
    app.start()
    send(app, Action.DIGIT, 4)
    assert app.lineup.current.number == 2  # not committed yet
    send(app, Action.ENTER)
    assert app.lineup.current.number == 4


def test_direct_channel_entry_times_out(tmp_path):
    app, player, clock = build_app(tmp_path)
    app.start()
    send(app, Action.DIGIT, 3)
    assert app.lineup.current.number == 2
    clock.advance(2.1)  # past the entry timeout
    app.step()
    assert app.lineup.current.number == 3


def test_invalid_channel_entry_shows_message(tmp_path):
    app, player, _ = build_app(tmp_path)
    app.start()
    assert app.select_channel_number(99) is False
    assert "NO CHANNEL" in player.overlays.get(4, "")
    assert app.lineup.current.number == 2  # unchanged


def test_last_channel_jump(tmp_path):
    app, player, _ = build_app(tmp_path)
    app.start()
    send(app, Action.CHANNEL_UP)  # now on 3, last=2
    assert app.lineup.current.number == 3
    send(app, Action.LAST_CHANNEL)
    assert app.lineup.current.number == 2
    send(app, Action.LAST_CHANNEL)  # bounces back to 3
    assert app.lineup.current.number == 3


def test_episode_advances_on_end(tmp_path):
    app, player, _ = build_app(tmp_path)
    app.start()
    first = player.current
    player.finish_current(END_EOF)  # simulate the episode ending
    app._drain_playback_events()
    assert player.current is not None
    assert player.current != first  # rolled into the next shuffled episode


def test_standby_blanks_and_ignores_input(tmp_path):
    app, player, _ = build_app(tmp_path)
    app.start()
    send(app, Action.POWER)
    assert app.standby
    assert player.current is None  # screen blanked
    assert 3 in player.overlays  # standby overlay
    # input is ignored while in standby
    send(app, Action.CHANNEL_UP)
    assert app.lineup.current.number == 2
    # power again wakes it up and resumes playback
    send(app, Action.POWER)
    assert not app.standby
    assert player.current is not None


def test_quit_stops_running(tmp_path):
    app, player, _ = build_app(tmp_path)
    app.start()
    app._running = True
    send(app, Action.QUIT)
    assert app._running is False


def test_glitch_transition_then_episode(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "glitch.mp4").write_bytes(b"\x00")
    app, player, clock = build_app(tmp_path, assets_dir=assets, transition="glitch")
    app.start()
    send(app, Action.CHANNEL_UP)
    # A glitch->episode transition was issued (glitch clip + preloaded episode).
    assert player.transitions, "expected a transition on channel change"
    clip, target, _start = player.transitions[-1]
    assert clip == assets / "glitch.mp4"
    assert player.current == target  # the episode is what plays


def test_transition_none_cuts_straight(tmp_path):
    # bridge_seconds=0 -> switch immediately, no transition clip, no preload
    app, player, _ = build_app(tmp_path, transition="none", bridge_seconds=0)
    app.start()
    first = player.current
    send(app, Action.CHANNEL_UP)
    assert not player.transitions
    assert player.preloaded is None
    assert player.current is not None and player.current != first


def test_channel_change_bridges_current_until_next_ready(tmp_path):
    # With bridge_seconds>0 and no transition, the current show keeps playing
    # while the next channel preloads, then cuts over after the window.
    app, player, clock = build_app(tmp_path, bridge_seconds=0.8)
    app.start()
    first = player.current
    send(app, Action.CHANNEL_UP)
    assert player.current == first          # old show still playing...
    assert player.preloaded is not None     # ...next channel preloading
    clock.advance(1.0)
    app.step()                              # bridge window elapsed -> switch
    assert player.preloaded is None
    assert player.current is not None and player.current != first


def test_advance_within_channel_has_no_transition(tmp_path):
    # An episode ending should roll straight into the next one (no glitch burst).
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "glitch.mp4").write_bytes(b"\x00")
    app, player, _ = build_app(tmp_path, assets_dir=assets, transition="glitch")
    app.start()
    before = len(player.transitions)
    player.finish_current(END_EOF)
    app._drain_playback_events()
    assert len(player.transitions) == before  # no new transition
    assert player.current is not None


def test_start_offset_applied(tmp_path):
    app, player, _ = build_app(tmp_path, start_offset=5)
    app.start()
    # The episode should begin 5 seconds in, not at the very beginning.
    assert player.played[-1][1] == 5.0


def test_start_offset_range_applied(tmp_path):
    app, player, _ = build_app(tmp_path, start_offset=[6, 10])
    app.start()
    assert 6.0 <= player.played[-1][1] <= 10.0


def test_empty_channel_shows_no_signal(tmp_path):
    (tmp_path / "dragon").mkdir()
    make_show(tmp_path, "arthur", 2)
    config = config_from_dict(
        {
            "channels": [
                {"number": 2, "name": "Dragon Tales", "path": str(tmp_path / "dragon")},
                {"number": 3, "name": "Arthur", "path": str(tmp_path / "arthur")},
            ]
        }
    )
    app = TVApp(config, MockPlayer(), InputManager([]), clock=FakeClock())
    app.start()  # starts on ch 2 which is empty
    assert "NO SIGNAL" in app.player.overlays.get(4, "")


def test_channel_banner_deferred_until_switch(tmp_path):
    app, player, clock = build_app(tmp_path, bridge_seconds=0.8)
    app.start()
    player.overlays.pop(1, None)          # clear the power-on banner
    send(app, Action.CHANNEL_UP)
    assert 1 not in player.overlays       # banner NOT shown during the bridge
    clock.advance(1.0)
    app.step()                            # cut-over happens here
    assert "CH 03" in player.overlays.get(1, "")  # banner appears at the switch


def test_frozen_episode_is_logged_then_skipped(tmp_path):
    """A stuck timestamp seeks ahead once, and a second freeze skips the file."""
    state = tmp_path / "state" / "playback.json"
    app, player, clock = build_app(
        tmp_path,
        bridge_seconds=0,
        stall_timeout=5,
        stall_grace=0,
        stall_seek=10,
        stall_flag_after=2,
        state_file=str(state),
    )
    app.start()
    first = player.current
    player.time_pos = 125.0  # 2:05, and it never moves
    clock.advance(5)
    app.step()
    assert player.seeks == [135.0]
    assert player.current == first  # still this episode, past the frozen spot
    clock.advance(5)
    app.step()
    assert player.current is not None and player.current != first
    assert "SKIPPING FILE" in player.overlays.get(4, "")
    text = (state.parent / "problem-files.log").read_text(encoding="utf-8")
    assert str(first) in text
    assert "at 2:05 (125.0s)" in text
    assert "stuck at this timestamp" in text
    assert "seeking ahead 10s" in text
    assert "channel 2 Dragon Tales" in text
    assert "flagged (2 freezes)" in text
    assert ProblemLog(state.parent, flag_after=2).is_flagged(first)


def test_playback_that_keeps_moving_is_left_alone(tmp_path):
    state = tmp_path / "state" / "playback.json"
    app, player, clock = build_app(
        tmp_path,
        bridge_seconds=0,
        stall_timeout=5,
        stall_grace=0,
        state_file=str(state),
    )
    app.start()
    first = player.current
    for _ in range(6):
        clock.advance(3)
        player.time_pos += 3
        app.step()
    assert player.seeks == []
    assert player.current == first
    assert not (state.parent / "problem-files.log").exists()


def test_hung_player_skips_the_episode(tmp_path):
    state = tmp_path / "state" / "playback.json"
    app, player, clock = build_app(
        tmp_path,
        bridge_seconds=0,
        stall_timeout=5,
        stall_grace=0,
        state_file=str(state),
    )
    app.start()
    first = player.current
    player.fail_sample = True  # property reads fail: the player is not answering
    clock.advance(5)
    app.step()
    assert player.seeks == []
    assert player.current is not None and player.current != first
    text = (state.parent / "problem-files.log").read_text(encoding="utf-8")
    assert str(first) in text
    assert "player stopped responding" in text
    assert "skipping to the next episode" in text


def test_failed_seek_skips_to_the_next_episode(tmp_path):
    state = tmp_path / "state" / "playback.json"
    app, player, clock = build_app(
        tmp_path,
        bridge_seconds=0,
        stall_timeout=5,
        stall_grace=0,
        state_file=str(state),
    )
    app.start()
    first = player.current
    player.time_pos = 40.0
    player.fail_seek = True
    clock.advance(5)
    app.step()
    assert player.seeks == []
    assert player.current is not None and player.current != first
    text = (state.parent / "problem-files.log").read_text(encoding="utf-8")
    assert "seek failed; skipping to the next episode" in text


def test_standby_does_not_look_like_a_freeze(tmp_path):
    state = tmp_path / "state" / "playback.json"
    app, player, clock = build_app(
        tmp_path,
        bridge_seconds=0,
        stall_timeout=5,
        stall_grace=0,
        state_file=str(state),
    )
    app.start()
    send(app, Action.POWER)
    clock.advance(30)
    app.step()
    assert player.seeks == []
    assert not (state.parent / "problem-files.log").exists()


def test_channel_change_restarts_the_stall_timer(tmp_path):
    state = tmp_path / "state" / "playback.json"
    app, player, clock = build_app(
        tmp_path,
        bridge_seconds=0,
        stall_timeout=5,
        stall_grace=0,
        state_file=str(state),
    )
    app.start()
    clock.advance(4)  # almost, but not quite, a stall
    send(app, Action.CHANNEL_UP)  # a new episode starts the timer over
    clock.advance(4)
    app.step()
    assert player.seeks == []
    assert not (state.parent / "problem-files.log").exists()


def test_flagged_episode_is_skipped_the_next_time_it_is_chosen(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    bad = tmp_path / "dragon" / "dragon_ep01.mp4"
    problems = ProblemLog(state_dir, flag_after=2)
    problems.note_stall(bad, 1.0, "seeking ahead 10s", "channel 2 Dragon Tales")
    problems.note_stall(bad, 11.0, "skipping to the next episode", "channel 2 Dragon Tales")
    app, player, _ = build_app(
        tmp_path,
        order="in_order",
        start_offset=0,
        bridge_seconds=0,
        state_file=str(state_dir / "playback.json"),
        stall_flag_after=2,
    )
    app.start()
    assert player.current is not None
    assert player.current.name == "dragon_ep02.mp4"
    text = (state_dir / "problem-files.log").read_text(encoding="utf-8")
    assert "flagged from earlier freezes; skipping" in text
    assert str(bad) in text


def test_stall_watch_off_keeps_a_frozen_frame(tmp_path):
    app, player, clock = build_app(
        tmp_path,
        bridge_seconds=0,
        stall_watch=False,
        stall_timeout=5,
        stall_grace=0,
    )
    app.start()
    first = player.current
    clock.advance(30)
    app.step()
    assert player.seeks == []
    assert player.current == first


def test_resume_mode_restarts_where_left(tmp_path):
    # bridge_seconds=0 keeps this test focused on resume (immediate switches)
    app, player, _ = build_app(tmp_path, tune_in="resume", bridge_seconds=0)
    app.start()
    playing = player.current
    player.time_pos = 42.0
    send(app, Action.CHANNEL_UP)  # leave ch 2, remembering position 42
    send(app, Action.CHANNEL_DOWN)  # back to ch 2 -> resume at 42
    assert player.current == playing
    assert player.played[-1] == (playing, 42.0)
