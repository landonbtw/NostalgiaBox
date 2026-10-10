#!/usr/bin/env python3
"""Unit tests: settings validation, config generation, login, screen-time maths,
the root helper's input checks and fstab handling, and the service-file reader.

Run:  python3 tests/test_units.py
"""
import importlib.machinery
import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="nbtest-")
os.environ.update(NB_STATE_DIR=TMP + "/state", NB_ETC_DIR=TMP + "/etc", NB_MEDIA_DIR=TMP + "/media",
                  NB_MOUNT_DIR=TMP + "/mnt", NB_RUN_DIR=TMP + "/run")
sys.path.insert(0, os.path.join(ROOT, "app"))
import nbcommon as nb  # noqa: E402
import discover_base  # noqa: E402


def load_helper():
    loader = importlib.machinery.SourceFileLoader("nbhelper", os.path.join(ROOT, "sbin", "nostalgiabox-helper"))
    spec = importlib.util.spec_from_loader("nbhelper", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def touch(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


class Settings(unittest.TestCase):
    def test_defaults_roundtrip(self):
        s = nb.sanitize_settings({})
        self.assertEqual(s["channel_count"], 3)
        self.assertEqual(len(s["channels"]), nb.MAX_CHANNELS)
        self.assertEqual(nb.sanitize_settings(s, s), s)

    def test_clamps_and_swaps(self):
        s = nb.sanitize_settings({"channel_count": 999, "first_channel": -4,
                                  "playback": {"start_offset_min": 20, "start_offset_max": 5, "tune_in": "bogus",
                                               "bridge_seconds": 99},
                                  "sound": {"initial_volume": 500, "output": "nope"},
                                  "picture": {"ui_color": "red", "curvature": 9},
                                  "screentime": {"hours": 0, "reset_hour": 99}})
        self.assertEqual(s["channel_count"], nb.MAX_CHANNELS)
        self.assertEqual(s["first_channel"], 1)
        self.assertEqual((s["playback"]["start_offset_min"], s["playback"]["start_offset_max"]), (5, 20))
        self.assertEqual(s["playback"]["tune_in"], "random")
        self.assertEqual(s["playback"]["bridge_seconds"], 5)
        self.assertEqual(s["sound"]["initial_volume"], 100)
        self.assertEqual(s["sound"]["output"], "auto")
        self.assertEqual(s["picture"]["ui_color"], "#4DFF5A")
        self.assertEqual(s["picture"]["curvature"], 0.4)
        self.assertEqual(s["screentime"]["hours"], 0.25)
        self.assertEqual(s["screentime"]["reset_hour"], 23)

    def test_bad_values_named_by_channel(self):
        with self.assertRaises(ValueError) as cm:
            nb.sanitize_settings({"channel_count": 2, "first_channel": 2,
                                  "channels": [{}, {"source": "network", "net": {"host": "bad host!"}}]})
        self.assertIn("Channel 3", str(cm.exception))

    def test_hidden_channel_errors_are_ignored(self):
        s = nb.sanitize_settings({"channel_count": 1, "channels": [{}, {"net": {"host": "bad host!"}}]})
        self.assertEqual(s["channels"][1]["net"]["host"], "")

    def test_net_rules(self):
        c = nb.sanitize_channel({"source": "network", "net": {"type": "nfs", "host": "tower.local",
                                                              "share": "mnt/user/media/", "username": "x",
                                                              "subfolder": "/Kids TV//Arthur/"}})
        self.assertEqual(c["net"]["share"], "/mnt/user/media")
        self.assertEqual(c["net"]["username"], "")  # NFS has no login
        self.assertEqual(c["net"]["subfolder"], "Kids TV/Arthur")
        for bad in ({"subfolder": "../etc"}, {"subfolder": "a/../../b"}, {"host": "a b"}, {"host": "-x"},
                    {"type": "smb", "share": "a/b"}, {"username": "x;rm"}):
            with self.assertRaises(ValueError, msg=str(bad)):
                nb.sanitize_channel({"source": "network", "net": dict({"type": "smb"}, **bad)})
        with self.assertRaises(ValueError):
            nb.sanitize_channel({"exclude_seasons": "six"})
        self.assertEqual(nb.sanitize_channel({"exclude_seasons": "6-25 3"})["exclude_seasons"], "6-25, 3")

    def test_start_channel_must_exist(self):
        s = nb.sanitize_settings({"channel_count": 3, "first_channel": 2, "playback": {"start_channel": 4}})
        self.assertEqual(s["playback"]["start_channel"], 4)
        s = nb.sanitize_settings({"channel_count": 3, "first_channel": 2, "playback": {"start_channel": 9}})
        self.assertEqual(s["playback"]["start_channel"], 0)


class Config(unittest.TestCase):
    def setUp(self):
        import shutil
        shutil.rmtree(nb.MEDIA_DIR, ignore_errors=True)
        shutil.rmtree(nb.MOUNT_DIR, ignore_errors=True)
        self.s = nb.sanitize_settings({"channel_count": 3, "first_channel": 2, "channels": [
            {"name": "Arthur", "exclude_seasons": "6-25", "exclude": "*special*, *promo*"},
            {"name": "Empty"},
            {"name": "", "source": "network", "net": {"type": "smb", "host": "tower", "share": "media",
                                                       "subfolder": "Kids/Dragon Tales"}}]})
        touch(nb.local_dir(0) + "/Season 1/S01E01.mp4")

    def test_only_channels_with_videos_air(self):
        cfg = nb.build_config(self.s)
        self.assertEqual([c["number"] for c in cfg["channels"]], [2])
        self.assertEqual(cfg["channels"][0]["name"], "Arthur")
        self.assertEqual(cfg["channels"][0]["exclude_seasons"], ["6-25"])
        self.assertEqual(cfg["channels"][0]["exclude"], ["*special*", "*promo*"])
        self.assertEqual(cfg["start_channel"], 2)

    def test_network_channel_path_and_default_name(self):
        touch(nb.mount_point(2) + "/Kids/Dragon Tales/a.mkv")
        cfg = nb.build_config(self.s)
        c = [c for c in cfg["channels"] if c["number"] == 4][0]
        self.assertEqual(c["name"], "Channel 4")
        self.assertEqual(c["path"], nb.mount_point(2) + "/Kids/Dragon Tales")

    def test_audio_offsets_and_yaml(self):
        self.s["sound"]["output"] = "hdmi1"
        self.s["playback"]["start_offset_min"] = self.s["playback"]["start_offset_max"] = 5
        cfg = nb.build_config(self.s)
        self.assertEqual(cfg["audio_device"], "alsa/hdmi:CARD=vc4hdmi1,DEV=0")
        self.assertEqual(cfg["start_offset"], 5)
        path = os.path.join(TMP, "cfg.yaml")
        nb.write_yaml(path, cfg, "# hi\n")
        import yaml
        self.assertEqual(yaml.safe_load(open(path))["channels"][0]["number"], 2)

    def test_special_config(self):
        cfg = nb.build_special_config(self.s, "Setup", "/x/ready")
        self.assertEqual(cfg["channels"], [{"number": 2, "name": "Setup", "path": "/x/ready"}])
        self.assertEqual(cfg["start_offset"], 0)

    def test_count_and_has_video_skip_junk(self):
        d = TMP + "/junk"
        touch(d + "/.hidden/a.mp4")
        touch(d + "/$RECYCLE.BIN/b.mp4")
        touch(d + "/notes.txt")
        touch(d + "/.._x.mp4")
        self.assertEqual(nb.count_videos(d)[0], 0)
        self.assertFalse(nb.has_video(d))
        touch(d + "/Season 2/c.MKV")
        self.assertEqual(nb.count_videos(d)[0], 1)
        self.assertTrue(nb.has_video(d))


class Auth(unittest.TestCase):
    def test_login_lifecycle(self):
        self.assertTrue(nb.auth_is_default())
        self.assertTrue(nb.verify_login("admin", "nostalgia"))
        self.assertTrue(nb.verify_login("Admin ", "nostalgia"))  # phones capitalise
        self.assertFalse(nb.verify_login("admin", "wrong"))
        nb.set_password("correct horse")
        self.assertFalse(nb.auth_is_default())
        self.assertFalse(nb.verify_login("admin", "nostalgia"))
        self.assertTrue(nb.verify_login("admin", "correct horse"))
        self.assertEqual(stat.S_IMODE(os.stat(nb.AUTH_FILE).st_mode), 0o600)
        self.assertNotIn("correct horse", open(nb.AUTH_FILE).read())


class ScreenTime(unittest.TestCase):
    def test_budget_day(self):
        self.assertEqual(nb.budget_day(datetime(2026, 10, 10, 2, 0), 6), "2026-10-09")
        self.assertEqual(nb.budget_day(datetime(2026, 10, 10, 6, 0), 6), "2026-10-10")
        self.assertEqual(nb.budget_day(datetime(2026, 10, 10, 0, 5), 0), "2026-10-10")

    def test_usage_resets_on_new_day(self):
        nb.save_usage(1234, 0, datetime(2026, 10, 10, 20, 0))
        self.assertEqual(nb.load_usage(0, datetime(2026, 10, 10, 23, 59)), 1234)
        self.assertEqual(nb.load_usage(0, datetime(2026, 10, 11, 0, 1)), 0)


class Invocation(unittest.TestCase):
    def test_config_args_replaced(self):
        os.makedirs(nb.ETC_DIR, exist_ok=True)
        with open(nb.BASE_FILE, "w") as f:
            json.dump({"argv": ["/venv/bin/nostalgiabox", "--config", "/old.yaml", "--check"],
                       "cwd": "/nonexistent", "env": {"A": "1"}}, f)
        argv, cwd, env = nb.base_invocation(["--check"], "/new.yaml")
        self.assertEqual(argv, ["/venv/bin/nostalgiabox", "--check", "--config", "/new.yaml"])
        self.assertIsNone(cwd)
        self.assertEqual(env["A"], "1")


class Discover(unittest.TestCase):
    UNIT = """[Unit]
Description=NostalgiaBox
After=multi-user.target

[Service]
User=pi
WorkingDirectory=/home/pi/NostalgiaBox
Environment=SDL_AUDIODRIVER=alsa "FOO=bar baz"
ExecStart=-/home/pi/NostalgiaBox/.venv/bin/python -m nostalgiabox --config /home/pi/NostalgiaBox/config.yaml
Restart=on-failure

[Install]
WantedBy=multi-user.target
"""

    def test_parse(self):
        b = discover_base.build(self.UNIT)
        self.assertEqual(b["argv"][:3], ["/home/pi/NostalgiaBox/.venv/bin/python", "-m", "nostalgiabox"])
        self.assertEqual(b["cwd"], "/home/pi/NostalgiaBox")
        self.assertEqual(b["user"], "pi")
        self.assertEqual(b["env"], {"SDL_AUDIODRIVER": "alsa", "FOO": "bar baz"})


class Helper(unittest.TestCase):
    def setUp(self):
        self.h = load_helper()
        h = self.h
        base = tempfile.mkdtemp(prefix="nbhelper-")
        h.ETC, h.CREDS = base + "/etc", base + "/etc/creds"
        h.MOUNT_ROOT, h.BROWSE_MP, h.RUNDIR = base + "/mnt", base + "/mnt/.browse", base + "/run"
        h.FSTAB = base + "/fstab"
        os.makedirs(h.ETC)
        with open(h.ETC + "/helper.json", "w") as f:
            json.dump({"uid": 1000, "gid": 1000}, f)
        with open(h.FSTAB, "w") as f:
            f.write("proc /proc proc defaults 0 0\nUUID=abc / ext4 defaults 0 1\n")
        self.calls, self.mounted = [], set()
        h.run = lambda cmd, timeout=60: (self.calls.append(cmd), (self.rc(cmd), self.err))[1]
        h.is_mounted = lambda p: p in self.mounted
        self.rc, self.err = (lambda cmd: 0), ""

    def test_validation(self):
        h = self.h
        ok = {"type": "smb", "host": "192.168.1.20", "share": "media", "username": "ryan"}
        self.assertEqual(h.clean_net(ok)["share"], "media")
        bad = [dict(ok, host="a b"), dict(ok, host="a;b"), dict(ok, host=""), dict(ok, share="m\nedia"),
               dict(ok, share="a/b"), dict(ok, username="x y"), dict(ok, type="sshfs"),
               {"type": "nfs", "host": "h", "share": "/a/../b"}, {"type": "nfs", "host": "h", "share": "/a\nb"}]
        for b in bad:
            with self.assertRaises(h.Fail, msg=str(b)):
                h.clean_net(b)
        with self.assertRaises(h.Fail):
            h.clean_password("pa\nss")
        with self.assertRaises(h.Fail):
            h.clean_id(0)
        with self.assertRaises(h.Fail):
            h.clean_id("../x")

    def test_apply_mounts_writes_fstab_and_creds(self):
        h = self.h
        req = {"channels": [
            {"id": 1, "net": {"type": "smb", "host": "tower", "share": "Kids TV", "username": "ryan"}, "password": "s3cret"},
            {"id": 2, "net": {"type": "nfs", "host": "10.0.0.5", "share": "/mnt/user/media", "username": ""}, "password": None},
            {"id": 3, "net": {"type": "smb", "host": "tower", "share": "pub", "username": ""}, "password": None}]}
        out = h.cmd_apply_mounts(req)
        self.assertEqual([r["id"] for r in out["results"]], [1, 2, 3])
        fstab = open(h.FSTAB).read()
        self.assertIn("proc /proc proc defaults 0 0", fstab)  # untouched
        self.assertIn(h.BEGIN, fstab)
        self.assertIn("//tower/Kids\\040TV " + h.MOUNT_ROOT + "/ch1 cifs ro,uid=1000,gid=1000", fstab)
        self.assertIn("credentials=" + h.CREDS + "/ch1", fstab)
        self.assertIn("10.0.0.5:/mnt/user/media " + h.MOUNT_ROOT + "/ch2 nfs ro,soft", fstab)
        self.assertIn(",guest,", fstab)
        self.assertIn("nofail", fstab)
        self.assertEqual(stat.S_IMODE(os.stat(h.CREDS + "/ch1").st_mode), 0o600)
        self.assertEqual(open(h.CREDS + "/ch1").read(), "username=ryan\npassword=s3cret\n")
        self.assertFalse(os.path.exists(h.CREDS + "/ch3"))
        self.assertTrue(any(c[:1] == ["mount"] and c[1].endswith("/ch1") for c in self.calls))
        # re-apply with no new password keeps the saved one; removing channels cleans up
        h.cmd_apply_mounts({"channels": [{"id": 1, "net": {"type": "smb", "host": "tower", "share": "Kids TV",
                                                          "username": "ryan"}, "password": None}]})
        self.assertIn("s3cret", open(h.CREDS + "/ch1").read())
        self.assertNotIn("/ch2 ", open(h.FSTAB).read())
        h.cmd_apply_mounts({"channels": []})
        self.assertNotIn(h.BEGIN, open(h.FSTAB).read())
        self.assertFalse(os.path.exists(h.CREDS + "/ch1"))
        self.assertEqual(open(h.FSTAB).read().count("proc /proc"), 1)

    def test_changed_username_drops_old_password(self):
        h = self.h
        net = {"type": "smb", "host": "tower", "share": "m", "username": "a"}
        h.cmd_apply_mounts({"channels": [{"id": 1, "net": net, "password": "pw"}]})
        h.cmd_apply_mounts({"channels": [{"id": 1, "net": dict(net, username="b"), "password": None}]})
        self.assertEqual(open(h.CREDS + "/ch1").read(), "username=b\npassword=\n")

    def test_mount_failure_is_explained(self):
        h = self.h
        self.rc, self.err = (lambda cmd: 32 if cmd[0] == "mount" else 0), "mount error(13): Permission denied"
        out = h.cmd_apply_mounts({"channels": [{"id": 1, "net": {"type": "smb", "host": "t", "share": "m", "username": ""}, "password": None}]})
        self.assertFalse(out["results"][0]["mounted"])
        self.assertIn("username and password", out["results"][0]["error"])

    def test_error_messages(self):
        e = self.h.explain_mount_error
        self.assertIn("not that share", e("mount error(2): No such file or directory"))
        self.assertIn("username and password", e("mount error(13): Permission denied"))
        self.assertIn("Can't reach", e("mount error(113): No route to host"))
        self.assertIn("IP address", e("mount.nfs: Failed to resolve server nas: Name or service not known"))
        self.assertIn("Can't reach", e("timed out"))

    def test_browse_mount_uses_saved_password_and_cleans_up(self):
        h = self.h
        h.cmd_apply_mounts({"channels": [{"id": 4, "net": {"type": "smb", "host": "t", "share": "m", "username": "u"}, "password": "topsecret"}]})
        seen = {}

        def fake_run(cmd, timeout=60):
            if cmd[0] == "mount" and "-t" in cmd:
                cred = [o for o in cmd[cmd.index("-o") + 1].split(",") if o.startswith("credentials=")][0].split("=", 1)[1]
                seen["cred"] = open(cred).read()
            return 0, ""
        h.run = fake_run
        h.cmd_browse_mount({"net": {"type": "smb", "host": "t", "share": "m", "username": "u"}, "password": None, "saved_channel": 4})
        self.assertIn("password=topsecret", seen["cred"])
        self.assertFalse(os.path.exists(h.RUNDIR + "/browse.cred"))

    def test_ensure_mounts_only_remounts_missing(self):
        h = self.h
        h.cmd_apply_mounts({"channels": [{"id": 1, "net": {"type": "nfs", "host": "h", "share": "/a", "username": ""}, "password": None},
                                         {"id": 2, "net": {"type": "nfs", "host": "h", "share": "/b", "username": ""}, "password": None}]})
        self.calls.clear()
        self.mounted.add(h.MOUNT_ROOT + "/ch1")
        out = h.cmd_ensure_mounts({})
        self.assertEqual([c for c in self.calls if c[0] == "mount"], [["mount", h.MOUNT_ROOT + "/ch2"]])
        self.assertEqual(len(out["results"]), 2)

    def test_power_and_timezone_are_whitelisted(self):
        h = self.h
        with self.assertRaises(h.Fail):
            h.cmd_power({"action": "rm -rf /"})
        self.err = "UTC\nAmerica/Chicago"
        with self.assertRaises(h.Fail):
            h.cmd_set_timezone({"tz": "Not/AZone; reboot"})
        h.cmd_set_timezone({"tz": "America/Chicago"})
        self.assertIn(["timedatectl", "set-timezone", "America/Chicago"], self.calls)

    def test_main_never_leaks_tracebacks(self):
        import io
        h = self.h
        h.COMMANDS = dict(h.COMMANDS, boom=lambda req: 1 / 0)
        sys.stdin, sys.stdout = io.StringIO("{}"), io.StringIO()
        try:
            h.main(["x", "boom"])
            out = sys.stdout.getvalue()
        finally:
            sys.stdin, sys.stdout = sys.__stdin__, sys.__stdout__
        self.assertEqual(json.loads(out)["ok"], False)
        self.assertNotIn("Traceback", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
