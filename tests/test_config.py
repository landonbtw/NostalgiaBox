from pathlib import Path

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
        "transition_duration": -3,
        "channels": [{"path": str(tmp_path / "a")}],
    }
    cfg = config_from_dict(data)
    assert cfg.initial_volume == 100
    assert cfg.volume_step == 1
    assert cfg.transition_duration == 0.0


def test_video_extensions_normalised(tmp_path):
    make_show(tmp_path, "a", 1)
    data = {
        "video_extensions": ["mp4", ".MKV"],
        "channels": [{"path": str(tmp_path / "a")}],
    }
    cfg = config_from_dict(data)
    assert cfg.video_extensions == (".mp4", ".mkv")


def test_ui_and_crt_defaults(tmp_path):
    make_show(tmp_path, "a", 1)
    cfg = config_from_dict({"channels": [{"path": str(tmp_path / "a")}]})
    assert cfg.ui.font == "VT323"
    assert cfg.ui.color == "#4DFF5A"
    assert cfg.crt.enabled is True
    assert cfg.force_4_3 is False   # shows keep their native aspect by default
    assert cfg.start_offset_min == 6.0
    assert cfg.start_offset_max == 10.0
    assert cfg.transition_effect == "none"
    assert cfg.transition_duration == 0.4
    assert cfg.bridge_seconds == 0.8


def test_start_offset_forms(tmp_path):
    make_show(tmp_path, "a", 1)
    base = {"channels": [{"path": str(tmp_path / "a")}]}
    # single number -> min == max
    c1 = config_from_dict({**base, "start_offset": 8})
    assert (c1.start_offset_min, c1.start_offset_max) == (8.0, 8.0)
    # [min, max] list
    c2 = config_from_dict({**base, "start_offset": [6, 10]})
    assert (c2.start_offset_min, c2.start_offset_max) == (6.0, 10.0)
    # explicit keys, and min/max get ordered
    c3 = config_from_dict({**base, "start_offset_min": 10, "start_offset_max": 6})
    assert (c3.start_offset_min, c3.start_offset_max) == (10.0, 10.0)


def test_ui_and_crt_overrides(tmp_path):
    make_show(tmp_path, "a", 1)
    cfg = config_from_dict(
        {
            "channels": [{"path": str(tmp_path / "a")}],
            "ui": {"font": "Press Start 2P", "color": "00FF00", "glow": False},
            "crt": {"enabled": False, "curvature": 0.2, "scanlines": False},
        }
    )
    assert cfg.ui.font == "Press Start 2P"
    assert cfg.ui.color == "#00FF00"  # normalised with leading '#'
    assert cfg.ui.glow is False
    assert cfg.crt.enabled is False
    assert cfg.crt.curvature == 0.2
    assert cfg.crt.scanlines is False


def test_crt_values_clamped(tmp_path):
    make_show(tmp_path, "a", 1)
    cfg = config_from_dict(
        {
            "channels": [{"path": str(tmp_path / "a")}],
            "crt": {"curvature": 5.0, "vignette": -1},
        }
    )
    assert cfg.crt.curvature == 0.5   # clamped to max
    assert cfg.crt.vignette == 0.0    # clamped to min


def test_bad_transition_rejected(tmp_path):
    make_show(tmp_path, "a", 1)
    with pytest.raises(ConfigError, match="transition"):
        config_from_dict(
            {"channels": [{"path": str(tmp_path / "a")}], "transition": "sparkles"}
        )


def test_bad_color_rejected(tmp_path):
    make_show(tmp_path, "a", 1)
    with pytest.raises(ConfigError, match="ui.color"):
        config_from_dict(
            {"channels": [{"path": str(tmp_path / "a")}], "ui": {"color": "greenish"}}
        )


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


def test_empty_media_root_is_a_valid_config(tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    cfg = config_from_dict({"media_root": str(root)})
    assert cfg.channels == []
    assert cfg.media_source == "sd"
    assert cfg.active_media_root == root
    assert cfg.media_error is None


def test_missing_media_root_is_reported_not_raised(tmp_path):
    missing = tmp_path / "missing"
    cfg = config_from_dict({"media_root": str(missing)})
    assert cfg.channels == []
    assert cfg.media_error is not None
    assert "does not exist" in cfg.media_error


def test_empty_channel_list_falls_back_to_discovery(tmp_path):
    make_show(tmp_path, "Arthur", 1)
    cfg = config_from_dict({"channels": [], "media_root": str(tmp_path)})
    assert cfg.media_source == "sd"
    assert [c.name for c in cfg.channels] == ["Arthur"]


def test_folder_names_with_spaces_stay_readable(tmp_path):
    make_show(tmp_path, "Dragon Tales", 2)
    make_show(tmp_path, "dragon-tales-alt", 1)
    cfg = config_from_dict({"media_root": str(tmp_path)})
    names = [c.name for c in cfg.channels]
    assert "Dragon Tales" in names
    assert "Dragon Tales Alt" in names


def test_usb_library_with_videos_is_preferred(tmp_path):
    sd = tmp_path / "sd"
    usb = tmp_path / "usb"
    make_show(sd, "Arthur", 1)
    make_show(usb, "Dragon Tales", 3)
    cfg = config_from_dict({"media_root": str(sd), "usb_media_root": str(usb)})
    assert cfg.media_source == "usb"
    assert cfg.active_media_root == usb
    assert [(c.name, c.path) for c in cfg.channels] == [
        ("Dragon Tales", usb / "Dragon Tales"),
    ]


def test_usb_without_videos_falls_back_to_sd_card(tmp_path):
    sd = tmp_path / "sd"
    usb = tmp_path / "usb"
    make_show(sd, "Arthur", 2)
    junk = usb / "System Volume Information"
    junk.mkdir(parents=True)
    (junk / "IndexerVolumeGuid").write_text("x")
    (usb / "LOST.DIR").mkdir()
    cfg = config_from_dict({
        "media_root": str(sd),
        "usb_media_root": str(usb),
        "prefer_usb": True,
    })
    assert cfg.media_source == "sd"
    assert cfg.channels[0].name == "Arthur"
    assert "System Volume Information" not in [c.name for c in cfg.channels]


def test_prefer_usb_false_keeps_the_sd_card(tmp_path):
    sd = tmp_path / "sd"
    usb = tmp_path / "usb"
    make_show(sd, "Arthur", 1)
    make_show(usb, "Dragon Tales", 1)
    cfg = config_from_dict({
        "media_root": str(sd),
        "usb_media_root": str(usb),
        "prefer_usb": False,
    })
    assert cfg.media_source == "sd"
    assert cfg.channels[0].name == "Arthur"


def test_explicit_channels_override_discovery(tmp_path):
    sd = tmp_path / "sd"
    usb = tmp_path / "usb"
    make_show(sd, "Arthur", 1)
    make_show(usb, "Dragon Tales", 4)
    cfg = config_from_dict({
        "media_root": str(sd),
        "usb_media_root": str(usb),
        "channels": [
            {"number": 9, "name": "Custom", "path": str(sd / "Arthur")},
        ],
    })
    assert cfg.media_source == "channels"
    assert cfg.channel_numbers() == [9]
    assert cfg.channels[0].path == sd / "Arthur"


def test_os_junk_folders_are_not_channels(tmp_path):
    make_show(tmp_path, "Arthur", 1)
    (tmp_path / ".Trashes").mkdir()
    (tmp_path / "$RECYCLE.BIN").mkdir()
    (tmp_path / "System Volume Information").mkdir()
    cfg = config_from_dict({"media_root": str(tmp_path)})
    assert [c.name for c in cfg.channels] == ["Arthur"]


def test_example_config_discovers_show_folders(tmp_path):
    import yaml

    example = Path(__file__).resolve().parents[1] / "config.example.yaml"
    data = yaml.safe_load(example.read_text(encoding="utf-8"))
    assert data["media_root"] == "/media/nostalgiabox"
    assert data["usb_media_root"] == "/media/nostalgiabox-usb"
    assert not data.get("channels")

    sd = tmp_path / "sd"
    make_show(sd, "Dragon Tales", 1)
    data["media_root"] = str(sd)
    data["usb_media_root"] = str(tmp_path / "usb-absent")
    cfg = config_from_dict(data)
    assert cfg.media_source == "sd"
    assert cfg.channels[0].name == "Dragon Tales"
    assert cfg.tune_in == "random"


def test_bad_first_channel_number(tmp_path):
    with pytest.raises(ConfigError, match="first_channel_number"):
        config_from_dict({
            "media_root": str(tmp_path),
            "first_channel_number": "two",
        })
