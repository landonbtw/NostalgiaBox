"""The nostalgiabox --check report."""

from pathlib import Path

from nostalgiabox.config import config_from_dict
from nostalgiabox.doctor import ServiceStatus, misplaced_show_dirs, run_check, wait_for_shows
from tests.helpers import make_show


def _ready(**kwargs):
    defaults = dict(
        which=lambda name: f"/usr/bin/{name}",
        python_mpv=lambda: (True, "installed"),
        service=lambda: ServiceStatus(True, "active", "enabled"),
        mount_source=lambda path: None,
        package_dir=Path("/this/package/does/not/exist"),
    )
    defaults.update(kwargs)
    return defaults


def test_check_lists_discovered_episodes(tmp_path, capsys):
    shows = tmp_path / "shows"
    make_show(shows, "Dragon Tales", 2)
    make_show(shows, "Arthur", 1)
    cfg = config_from_dict({
        "media_root": str(shows),
        "usb_media_root": str(tmp_path / "no-usb"),
    })
    code = run_check(cfg, tmp_path / "config.yaml", **_ready())
    out = capsys.readouterr().out
    assert code == 0
    assert "Dragon Tales" in out
    assert "2 episodes" in out
    assert "Arthur" in out
    assert "Ready." in out
    assert str(shows) in out


def test_check_explains_an_empty_library(tmp_path, capsys):
    shows = tmp_path / "shows"
    shows.mkdir()
    cfg = config_from_dict({
        "media_root": str(shows),
        "usb_media_root": str(tmp_path / "usb"),
    })
    code = run_check(cfg, tmp_path / "config.yaml", **_ready())
    out = capsys.readouterr().out
    assert code == 1
    assert "FIX" in out
    assert "No show folders" in out
    assert str(shows) in out
    assert "app.py" in out


def test_check_explains_missing_explicit_paths(tmp_path, capsys):
    cfg = config_from_dict({
        "channels": [
            {
                "number": 2,
                "name": "Dragon Tales",
                "path": "/media/nostalgiabox/dragon-tales",
            }
        ]
    })
    code = run_check(cfg, tmp_path / "config.yaml", **_ready())
    out = capsys.readouterr().out
    assert code == 1
    assert "dragon-tales" in out
    assert "does not exist" in out
    assert "media_root: /media/nostalgiabox" in out


def test_check_names_a_usb_drive(tmp_path, capsys):
    usb = tmp_path / "usb"
    make_show(usb, "Arthur", 4)
    cfg = config_from_dict({
        "media_root": str(tmp_path / "sd"),
        "usb_media_root": str(usb),
    })
    code = run_check(
        cfg,
        tmp_path / "config.yaml",
        **_ready(mount_source=lambda path: "/dev/sda1" if path == usb else None),
    )
    out = capsys.readouterr().out
    assert code == 0
    assert cfg.media_source == "usb"
    assert "USB" in out
    assert "/dev/sda1" in out
    assert "4 episodes" in out


def test_check_flags_shows_left_in_the_program_folder(tmp_path, capsys):
    package = tmp_path / "nostalgiabox"
    make_show(package, "DragonTales", 2)
    (package / "app.py").write_text("# program\n")
    (package / "input").mkdir()
    media = tmp_path / "media"
    media.mkdir()
    cfg = config_from_dict({
        "media_root": str(media),
        "usb_media_root": str(tmp_path / "usb"),
    })
    code = run_check(cfg, tmp_path / "config.yaml", **_ready(package_dir=package))
    out = capsys.readouterr().out
    assert code == 1
    assert "DragonTales" in out
    assert "program" in out.lower()
    assert f"mv {str(package / 'DragonTales')!s}" in out or "DragonTales" in out
    assert str(media) in out
    # The real program directories are not treated as shows.
    assert misplaced_show_dirs(package, [".mp4"]) == [package / "DragonTales"]


def test_check_flags_loose_videos_on_a_usb_drive(tmp_path, capsys):
    usb = tmp_path / "usb"
    usb.mkdir()
    (usb / "S01E01.mp4").write_bytes(b"\x00")
    sd = tmp_path / "sd"
    sd.mkdir()
    cfg = config_from_dict({"media_root": str(sd), "usb_media_root": str(usb)})
    assert cfg.media_source == "sd"
    code = run_check(cfg, tmp_path / "config.yaml", **_ready())
    out = capsys.readouterr().out
    assert code == 1
    assert "S01E01.mp4" in out
    assert "Dragon Tales" in out


def test_check_reports_missing_player_tools(tmp_path, capsys):
    shows = tmp_path / "shows"
    make_show(shows, "Arthur", 1)
    cfg = config_from_dict({"media_root": str(shows)})
    code = run_check(
        cfg,
        tmp_path / "config.yaml",
        **_ready(which=lambda name: None, python_mpv=lambda: (False, "no libmpv")),
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "mpv is not installed" in out
    assert "ffmpeg is not installed" in out
    assert "python-mpv" in out
    assert "install.sh" in out


def test_wait_for_shows_announces_then_returns(tmp_path):
    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    shows = tmp_path / "shows"
    make_show(shows, "Arthur", 1)
    empty = config_from_dict({"media_root": str(empty_root)})
    ready = config_from_dict({"media_root": str(shows)})
    remaining = {"left": 1}

    def load():
        if remaining["left"]:
            remaining["left"] -= 1
            return empty
        return ready

    sleeps = []
    notes = []
    found = wait_for_shows(load, sleeps.append, notes.append, interval=5, remind_every=30)
    assert found is ready
    assert sleeps == [5]
    assert notes == [empty]


def test_wait_for_shows_reminds_every_thirty_seconds(tmp_path):
    shows = tmp_path / "shows"
    make_show(shows, "Arthur", 1)
    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    empty = config_from_dict({"media_root": str(empty_root)})
    ready = config_from_dict({"media_root": str(shows)})
    calls = {"n": 0}

    def load():
        calls["n"] += 1
        if calls["n"] >= 8:
            return ready
        return empty

    sleeps = []
    notes = []
    found = wait_for_shows(load, sleeps.append, notes.append, interval=5, remind_every=30)
    assert found is ready
    assert sleeps == [5, 5, 5, 5, 5, 5, 5]
    assert notes == [empty, empty]


def test_wait_returns_immediately_when_channels_exist(tmp_path):
    shows = tmp_path / "shows"
    make_show(shows, "Arthur", 1)
    ready = config_from_dict({"media_root": str(shows)})
    sleeps = []
    notes = []
    found = wait_for_shows(lambda: ready, sleeps.append, notes.append)
    assert found is ready
    assert sleeps == []
    assert notes == []
