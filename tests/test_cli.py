"""Command lookup and installer help, independent of the current folder."""

import subprocess
from pathlib import Path

import pytest

from nostalgiabox.__main__ import _find_config, main
from nostalgiabox.config import ConfigError
from nostalgiabox.doctor import ServiceStatus
from tests.helpers import make_show

REPO = Path(__file__).resolve().parents[1]


def test_find_config_uses_the_repo_when_cwd_has_none(tmp_path):
    repo = tmp_path / "NostalgiaBox"
    repo.mkdir()
    config = repo / "config.yaml"
    config.write_text("media_root: /tmp/shows\n")
    other = tmp_path / "other"
    other.mkdir()
    found = _find_config(None, cwd=other, home=tmp_path / "home", repo_dir=repo)
    assert found == config


def test_find_config_prefers_a_config_in_the_current_directory(tmp_path):
    repo = tmp_path / "NostalgiaBox"
    repo.mkdir()
    (repo / "config.yaml").write_text("media_root: /tmp/repo\n")
    here = tmp_path / "here"
    here.mkdir()
    local = here / "config.yaml"
    local.write_text("media_root: /tmp/local\n")
    found = _find_config(None, cwd=here, home=tmp_path / "home", repo_dir=repo)
    assert found == local


def test_find_config_points_at_the_installer_when_nothing_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "nostalgiabox.__main__.config_candidates",
        lambda cwd, home, repo: [tmp_path / "nope.yaml"],
    )
    with pytest.raises(ConfigError, match="install.sh"):
        _find_config(None)


def test_check_works_from_another_directory(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "NostalgiaBox"
    shows = tmp_path / "shows"
    make_show(shows, "Dragon Tales", 2)
    repo.mkdir()
    (repo / "config.yaml").write_text(
        f"media_root: {shows}\nusb_media_root: {tmp_path / 'no-usb'}\n"
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setattr("nostalgiabox.__main__.installed_repo_dir", lambda: repo)
    monkeypatch.setattr("nostalgiabox.doctor.probe_python_mpv", lambda: (True, "ok"))
    monkeypatch.setattr("nostalgiabox.doctor.probe_service", lambda: ServiceStatus(True, "active", "enabled"))
    monkeypatch.setattr("nostalgiabox.doctor.shutil.which", lambda name: f"/usr/bin/{name}")

    code = main(["--check"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Dragon Tales" in out
    assert "2 episodes" in out
    assert "Ready." in out


def test_check_missing_config_is_a_fix_not_a_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("nostalgiabox.__main__.installed_repo_dir", lambda: None)
    monkeypatch.setattr(
        "nostalgiabox.__main__.config_candidates",
        lambda cwd, home, repo: [tmp_path / "missing.yaml"],
    )
    code = main(["--check"])
    out = capsys.readouterr().out
    assert code == 2
    assert "FIX" in out
    assert "install.sh" in out


def test_bad_key_override_fails_check(tmp_path, capsys):
    shows = tmp_path / "shows"
    make_show(shows, "Arthur", 1)
    config = tmp_path / "config.yaml"
    config.write_text(
        f"media_root: {shows}\n"
        "input:\n"
        "  key_overrides:\n"
        "    KEY_F5: not_an_action\n"
    )
    code = main(["--check", "--config", str(config)])
    out = capsys.readouterr().out
    assert code == 2
    assert "not_an_action" in out


def test_run_from_config_rejects_an_empty_library(tmp_path):
    from nostalgiabox.app import run_from_config
    from nostalgiabox.config import config_from_dict

    cfg = config_from_dict({"media_root": str(tmp_path)})
    with pytest.raises(RuntimeError, match="No show folders"):
        run_from_config(cfg, dry_run=True)


def test_dry_run_without_shows_exits(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    config = tmp_path / "config.yaml"
    config.write_text(f"media_root: {empty}\n")
    code = main(["--dry-run", "--config", str(config)])
    out = capsys.readouterr().out
    assert code == 1
    assert str(empty) in out


def test_install_help_from_another_directory():
    result = subprocess.run(
        ["bash", str(REPO / "scripts" / "install.sh"), "--help"],
        cwd="/tmp",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "any directory" in result.stdout
    assert "--no-service" in result.stdout
    assert str(REPO) in result.stdout


def test_install_unknown_argument_fails_before_doing_work():
    result = subprocess.run(
        ["bash", str(REPO / "scripts" / "install.sh"), "--frob"],
        cwd="/tmp",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "unknown argument" in result.stderr


def test_mount_usb_help_does_not_need_root():
    result = subprocess.run(
        ["bash", str(REPO / "scripts" / "mount-usb.sh"), "--help"],
        cwd="/tmp",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "/media/nostalgiabox-usb" in result.stdout
