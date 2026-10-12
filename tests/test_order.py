"""Natural episode order, in-order playback, and the saved place."""

import random
from pathlib import Path

from nostalgiabox.actions import Action
from nostalgiabox.channel import (
    BroadcastSchedule,
    Channel,
    natural_sort_key,
    preview_episodes,
    scan_episodes,
)
from nostalgiabox.config import ConfigError, config_from_dict
from nostalgiabox.playback_state import ChannelBookmark, PlaybackState
from tests.helpers import make_show
from tests.test_app import build_app, send

import pytest


def _files(folder: Path, names: list[str]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x00")


def test_natural_sort_puts_2_before_10_and_seasons_in_order(tmp_path):
    folder = tmp_path / "show"
    _files(
        folder,
        [
            "Ep 10.mp4",
            "Ep 2.mp4",
            "103.mp4",
            "101.mp4",
            "102.mp4",
            "S01E10.mp4",
            "S01E02.mp4",
            "1x10.mp4",
            "1x02.mp4",
            "Season 10/ep.mp4",
            "Season 2/S02E01.mp4",
            "Season 1/S01E10.mp4",
            "Season 1/S01E02.mp4",
        ],
    )
    got = [p.relative_to(folder).as_posix() for p in scan_episodes(folder, [".mp4"])]
    assert got.index("Ep 2.mp4") < got.index("Ep 10.mp4")
    assert got.index("101.mp4") < got.index("102.mp4") < got.index("103.mp4")
    assert got.index("S01E02.mp4") < got.index("S01E10.mp4")
    assert got.index("1x02.mp4") < got.index("1x10.mp4")
    assert got.index("Season 1/S01E02.mp4") < got.index("Season 1/S01E10.mp4")
    assert got.index("Season 2/S02E01.mp4") < got.index("Season 10/ep.mp4")
    # The same key the scanner uses: numbers compare as numbers.
    assert natural_sort_key("ep 2") < natural_sort_key("ep 10")
    assert natural_sort_key("season 2") < natural_sort_key("season 10")


def _ordered_channel(tmp_path, names, **kw):
    from nostalgiabox.config import ChannelConfig

    folder = tmp_path / "show"
    _files(folder, names)
    cfg = ChannelConfig(
        number=kw.pop("number", 3),
        name="Show",
        path=folder,
        order="in_order",
    )
    episodes = scan_episodes(folder, [".mp4"])
    return Channel(
        cfg,
        episodes,
        rng=random.Random(0),
        start_offset_min=6.0,
        start_offset_max=10.0,
        **kw,
    )


def test_in_order_plays_101_102_103_and_loops(tmp_path):
    ch = _ordered_channel(tmp_path, ["103.mp4", "101.mp4", "102.mp4"])
    first = ch.tune_in()
    # A series starts at the beginning. The 6–10 second skip is for shuffle.
    assert first.path.name == "101.mp4"
    assert first.start == 0.0
    assert ch.advance().path.name == "102.mp4"
    assert ch.advance().path.name == "103.mp4"
    assert ch.advance().path.name == "101.mp4"
    assert ch.advance().start == 0.0


def test_in_order_remembers_a_channel_flip(tmp_path):
    ch = _ordered_channel(tmp_path, ["101.mp4", "102.mp4"])
    first = ch.tune_in()
    ch.remember(first.path, 42.5)
    again = ch.tune_in()
    assert again.path == first.path
    assert again.start == 42.5


def test_in_order_place_survives_a_new_channel_object(tmp_path):
    ch = _ordered_channel(tmp_path, ["101.mp4", "102.mp4", "103.mp4"])
    first = ch.tune_in()
    ch.remember(first.path, 18.0)
    state = PlaybackState(tmp_path / "playback.json")
    state.set(ch.config.path, ch.bookmark())
    state.save()

    loaded = PlaybackState.load(tmp_path / "playback.json")
    restored = Channel(
        ch.config,
        ch.episodes,
        tune_in="random",
        bookmark=loaded.get(ch.config.path),
    )
    req = restored.tune_in()
    assert req.path.name == "101.mp4"
    assert req.start == 18.0
    # --check lists the series from the saved episode, then wraps.
    preview = preview_episodes(
        ch.config.path,
        ch.episodes,
        order="in_order",
        bookmark=loaded.get(ch.config.path),
        limit=3,
    )
    assert [p.name for p in preview] == ["101.mp4", "102.mp4", "103.mp4"]


def test_corrupt_state_file_starts_fresh(tmp_path):
    path = tmp_path / "playback.json"
    path.write_text("{not json", encoding="utf-8")
    state = PlaybackState.load(path)
    assert state.get(tmp_path / "show") is None


def test_broadcast_in_order_follows_the_files(tmp_path, monkeypatch):
    import nostalgiabox.channel as channel_mod

    monkeypatch.setattr(channel_mod, "probe_duration", lambda _p: 10.0)
    ch = _ordered_channel(
        tmp_path, ["103.mp4", "101.mp4", "102.mp4"], tune_in="broadcast"
    )
    assert ch.tune_in(now=0.0).path.name == "101.mp4"
    assert ch.tune_in(now=0.0).start == 0.0
    assert ch.tune_in(now=15.0).path.name == "102.mp4"
    assert ch.tune_in(now=15.0).start == 5.0
    assert ch.tune_in(now=25.0).path.name == "103.mp4"
    assert ch.broadcast_epoch == 0.0

    # A reboot keeps the same station clock.
    again = Channel(
        ch.config,
        ch.episodes,
        tune_in="broadcast",
        bookmark=ChannelBookmark(epoch=0.0),
    )
    # probe_duration is still patched.
    assert again.tune_in(now=15.0).path.name == "102.mp4"


def test_broadcast_schedule_in_order_does_not_shuffle():
    episodes = [Path("101.mp4"), Path("102.mp4"), Path("103.mp4")]
    sched = BroadcastSchedule(
        episodes,
        [10.0, 10.0, 10.0],
        epoch=0.0,
        rng=random.Random(0),
        in_order=True,
    )
    assert sched.at(0.0).path.name == "101.mp4"
    assert sched.at(10.0).path.name == "102.mp4"
    assert sched.at(20.0).path.name == "103.mp4"
    assert sched.at(30.0).path.name == "101.mp4"


def test_shuffle_false_and_marker_and_explicit_order(tmp_path):
    shows = tmp_path / "shows"
    dragon = make_show(shows, "dragon", 1)
    (dragon / ".inorder").write_text("", encoding="utf-8")
    make_show(shows, "arthur", 1)
    cfg = config_from_dict({
        "media_root": str(shows),
        "usb_media_root": str(tmp_path / "no-usb"),
    })
    by_name = {c.name: c.order for c in cfg.channels}
    assert by_name["Dragon"] == "in_order"  # marker, no config edit
    assert by_name["Arthur"] == "shuffle"
    assert cfg.order == "shuffle"

    listed = config_from_dict({
        "shuffle": False,
        "channels": [
            {"path": str(dragon)},
            {"path": str(shows / "arthur"), "order": "shuffle"},
        ],
    })
    assert listed.order == "in_order"
    assert listed.channels[0].order == "in_order"  # inherited shuffle: false
    assert listed.channels[1].order == "shuffle"  # explicit order wins

    aliased = config_from_dict({
        "channels": [{"path": str(shows / "arthur"), "shuffle": False}],
    })
    assert aliased.channels[0].order == "in_order"

    both = config_from_dict({
        "order": "in_order",
        "shuffle": True,  # order wins
        "channels": [{"path": str(dragon), "order": "shuffle"}],
    })
    assert both.order == "in_order"
    # Explicit per-channel shuffle beats the .inorder marker.
    assert both.channels[0].order == "shuffle"

    with pytest.raises(ConfigError, match="order"):
        config_from_dict({
            "order": "alphabetical",
            "channels": [{"path": str(dragon)}],
        })


def test_app_saves_the_place_across_a_restart(tmp_path):
    state = tmp_path / "playback.json"
    app, player, _ = build_app(
        tmp_path, order="in_order", state_file=str(state), start_offset=0
    )
    app.start()
    first = player.current
    assert first is not None and first.name.endswith("ep01.mp4")
    player.time_pos = 22.0
    send(app, Action.CHANNEL_UP)
    app.shutdown()

    app2, player2, _ = build_app(
        tmp_path, order="in_order", state_file=str(state), start_offset=0
    )
    app2.start()
    assert player2.current == first
    assert player2.played[-1] == (first, 22.0)
