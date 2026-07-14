import pytest

from nostalgiabox.config import (
    ConfigError,
    config_from_dict,
    load_config,
)
from tests.helpers import make_show


def test_explicit_channels(tmp_path):
    make_show(tmp_path, "dragon-tales", 3)
    make_show(tmp_path, "arthur", 2)
    data = {
        "channels": [
            {"number": 2, "name": "Dragon Tales", "path": str(tmp_path / "dragon-tales")},
            {"number": 3, "name": "Arthur", "path": str(tmp_path / "arthur")},
        ]
    }
    cfg = config_from_dict(data)
    assert cfg.channel_numbers() == [2, 3]
    assert cfg.channels[0].name == "Dragon Tales"
    assert cfg.tune_in == "random"  # default


def test_channel_number_and_name_defaults(tmp_path):
    make_show(tmp_path, "magic_school_bus", 1)
    data = {"channels": [{"path": str(tmp_path / "magic_school_bus")}]}
    cfg = config_from_dict(data)
    # number defaults to index+2, name derived + prettified from folder
    assert cfg.channels[0].number == 2
    assert cfg.channels[0].name == "Magic School Bus"


def test_media_root_autodiscovery(tmp_path):
    make_show(tmp_path, "arthur", 1)
    make_show(tmp_path, "rugrats", 1)
    make_show(tmp_path, "dragon tales", 1)
    (tmp_path / ".hidden").mkdir()
    cfg = config_from_dict({"media_root": str(tmp_path)})
    # alphabetical order, numbered from 2, hidden folder ignored
    assert [(c.number, c.name) for c in cfg.channels] == [
        (2, "Arthur"),
        (3, "Dragon Tales"),
        (4, "Rugrats"),
    ]


def test_autodiscovery_custom_first_number(tmp_path):
    make_show(tmp_path, "arthur", 1)
    cfg = config_from_dict({"media_root": str(tmp_path), "first_channel_number": 7})
    assert cfg.channels[0].number == 7


def test_duplicate_channel_numbers_rejected(tmp_path):
    make_show(tmp_path, "a", 1)
    make_show(tmp_path, "b", 1)
    data = {
        "channels": [
            {"number": 5, "name": "A", "path": str(tmp_path / "a")},
            {"number": 5, "name": "B", "path": str(tmp_path / "b")},
        ]
    }
    with pytest.raises(ConfigError, match="duplicate channel number"):
        config_from_dict(data)


def test_missing_channels_and_media_root():
    with pytest.raises(ConfigError, match="either 'channels' or 'media_root'"):
        config_from_dict({})


def test_bad_tune_in_mode(tmp_path):
    make_show(tmp_path, "a", 1)
    data = {"tune_in": "nonsense", "channels": [{"path": str(tmp_path / "a")}]}
    with pytest.raises(ConfigError, match="tune_in"):
        config_from_dict(data)


def test_volume_and_durations_clamped(tmp_path):
    make_show(tmp_path, "a", 1)
    data = {
        "initial_volume": 500,
        "volume_step": 0,
        "static_duration": -3,
        "channels": [{"path": str(tmp_path / "a")}],
    }
    cfg = config_from_dict(data)
    assert cfg.initial_volume == 100
    assert cfg.volume_step == 1
    assert cfg.static_duration == 0.0


def test_video_extensions_normalised(tmp_path):
    make_show(tmp_path, "a", 1)
    data = {
        "video_extensions": ["mp4", ".MKV"],
        "channels": [{"path": str(tmp_path / "a")}],
    }
    cfg = config_from_dict(data)
    assert cfg.video_extensions == (".mp4", ".mkv")


def test_load_config_from_file(tmp_path):
    make_show(tmp_path, "arthur", 1)
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "channels:\n"
        f"  - path: {tmp_path / 'arthur'}\n"
        "    name: Arthur\n"
        "    number: 3\n"
        "tune_in: resume\n"
    )
    cfg = load_config(cfg_file)
    assert cfg.tune_in == "resume"
    assert cfg.channels[0].number == 3


def test_load_config_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_relative_paths_resolved_against_config_dir(tmp_path):
    make_show(tmp_path, "arthur", 1)
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("channels:\n  - path: arthur\n    name: Arthur\n")
    cfg = load_config(cfg_file)
    assert cfg.channels[0].path == tmp_path / "arthur"
