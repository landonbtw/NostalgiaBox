#!/usr/bin/env python3
"""NostalgiaBox TV controller.

The installer points nostalgiabox.service at this program instead of at
NostalgiaBox itself. It decides what the TV should be showing and runs
NostalgiaBox with the matching config:

  ready   - no shows are available yet (fresh install, or the network share is
            down): a "box is ready" screen with the web address and login
  tv      - normal channels, built from what you saved on the setup page
  offair  - the daily screen-time budget is used up: static until the next day

When the mode changes (or you press Save & apply) it stops NostalgiaBox and
exits; systemd restarts it a second later, which cleanly kills anything
NostalgiaBox left behind and starts the new mode.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nbcommon as nb  # noqa: E402

TICK = float(os.environ.get("NB_TICK", "1.0"))
WATCH_EVERY = float(os.environ.get("NB_WATCH", "10"))
USAGE_SAVE_EVERY = 30.0
STATUS_EVERY = 5.0
MOUNT_RETRY_EVERY = 60.0
CONFIG_HEADER = ("# Written automatically by the NostalgiaBox setup page.\n"
                 "# Change settings on the page, not in this file.\n")


def log(msg: str) -> None:
    print(f"[controller] {msg}", flush=True)


def decide_mode(settings: dict, videos_present: bool, used_seconds: float) -> str:
    if not videos_present:
        return "ready"
    st = settings["screentime"]
    if st["enabled"] and used_seconds >= st["hours"] * 3600:
        return "offair"
    return "tv"


_net_cache = {"at": 0.0, "ip": None, "host": ""}


def _net_info() -> tuple:
    """IP and hostname, looked up at most every 5 seconds."""
    if time.monotonic() - _net_cache["at"] > 5 or not _net_cache["host"]:
        _net_cache.update(at=time.monotonic(), ip=nb.local_ip(), host=nb.short_hostname())
    return _net_cache["ip"], _net_cache["host"]


def ready_info(settings: dict, no_shows: bool) -> dict:
    ip, host = _net_info()
    return {
        "ip": ip,
        "hostname": host,
        "port": nb.PORT,
        "username": nb.auth_username(),
        "password": nb.DEFAULT_PASSWORD if nb.auth_is_default() else None,
        "configured": bool(settings.get("configured")),
        "no_shows": bool(no_shows and settings.get("configured")),
    }


class VideoWatcher(threading.Thread):
    """Checks in the background whether any channel has video files (a dead network
    share can make file access slow, and the controller must never freeze on it)."""

    def __init__(self):
        super().__init__(daemon=True)
        self.present = False
        self.false_streak = 0
        self.checked = threading.Event()

    def run(self):
        while True:
            try:
                s = nb.load_settings()
                found = any(nb.channel_ready(ch) and nb.has_video(nb.channel_path(i, ch))
                            for i, _n, ch in nb.active_channels(s))
            except Exception as e:  # keep watching no matter what
                log(f"video check failed: {e!r}")
                found = self.present
            self.false_streak = 0 if found else self.false_streak + 1
            self.present = found
            self.checked.set()
            time.sleep(WATCH_EVERY)


class Controller:
    def __init__(self):
        self.stop = False
        self.child: subprocess.Popen | None = None
        self.mode = ""
        self.mode_started = time.time()
        self.watcher = VideoWatcher()
        self.last_mount_try = 0.0

    # ----------------------------------------------------------- preparing
    def prepare(self, mode: str, s: dict) -> str:
        """Write whatever the mode needs and return the config file to run."""
        if mode == "tv":
            cfg = nb.build_config(s)
            nb.write_yaml(nb.REAL_CONFIG, cfg, CONFIG_HEADER)
            return nb.REAL_CONFIG
        from screens import make_offair_clip, make_still_clip, render_ready_png

        color = s["picture"]["ui_color"]
        if mode == "ready":
            folder = os.path.join(nb.SCREENS_DIR, "ready")
            info = ready_info(s, no_shows=True)
            sig = json.dumps([info, color], sort_keys=True)
            sigfile, mp4 = os.path.join(folder, "ready.sig"), os.path.join(folder, "ready.mp4")
            if not (os.path.exists(mp4) and nb.read_json(sigfile) == sig):
                log("drawing the 'box is ready' screen")
                render_ready_png(os.path.join(folder, "ready.png"), info, color)
                make_still_clip(os.path.join(folder, "ready.png"), mp4)
                nb.atomic_write(sigfile, json.dumps(sig))
            name = "Setup"
        else:
            folder = os.path.join(nb.SCREENS_DIR, "offair")
            sigfile, mp4 = os.path.join(folder, "offair.sig"), os.path.join(folder, "offair.mp4")
            sig = color
            if not (os.path.exists(mp4) and nb.read_json(sigfile) == sig):
                log("making the off-air static")
                os.makedirs(folder, exist_ok=True)
                make_offair_clip(mp4, color)
                nb.atomic_write(sigfile, json.dumps(sig))
            name = "Off Air"
        path = os.path.join(nb.STATE_DIR, f"{mode}.yaml")
        nb.write_yaml(path, nb.build_special_config(s, name, folder), CONFIG_HEADER)
        return path

    def current_ready_sig(self, s: dict) -> str:
        return json.dumps([ready_info(s, no_shows=True), s["picture"]["ui_color"]], sort_keys=True)

    # ------------------------------------------------------------- child
    def launch(self, cfg_path: str) -> None:
        inv = nb.base_invocation([], cfg_path)
        if inv is None:
            argv, cwd, env = ["nostalgiabox", "--config", cfg_path], None, dict(os.environ)
        else:
            argv, cwd, env = inv
        log(f"starting ({self.mode}): {' '.join(argv)}")
        self.child = subprocess.Popen(argv, cwd=cwd, env=env)

    def stop_child(self) -> None:
        c = self.child
        if not c or c.poll() is not None:
            return
        c.terminate()
        try:
            c.wait(timeout=6)
        except subprocess.TimeoutExpired:
            c.kill()
            c.wait()

    def file_sig(self):
        def m(p):
            try:
                return os.stat(p).st_mtime_ns
            except OSError:
                return 0
        return (m(nb.SETTINGS_FILE), m(nb.CONTROL_FILE))

    # ----------------------------------------------------------- misc jobs
    def maybe_remount(self, s: dict) -> None:
        now = time.monotonic()
        if now - self.last_mount_try < MOUNT_RETRY_EVERY:
            return
        needs = [i for i, _n, ch in nb.active_channels(s)
                 if ch["source"] == "network" and nb.channel_ready(ch)
                 and not os.path.ismount(nb.mount_point(i))]
        if needs:
            self.last_mount_try = now
            threading.Thread(target=lambda: nb.call_helper("ensure-mounts", timeout=150), daemon=True).start()

    def write_status(self, s: dict, used: float) -> None:
        st = s["screentime"]
        try:
            nb.atomic_write(nb.STATUS_FILE, json.dumps({
                "mode": self.mode, "since": self.mode_started, "updated": time.time(),
                "used_seconds": round(used), "budget_seconds": round(st["hours"] * 3600) if st["enabled"] else None,
                "pid": os.getpid()}))
        except OSError:
            pass

    # ---------------------------------------------------------------- run
    def run(self) -> int:
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "stop", True))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "stop", True))
        os.makedirs(nb.STATE_DIR, exist_ok=True)

        s = nb.load_settings()
        self.watcher.start()
        self.watcher.checked.wait(timeout=12)
        reset = s["screentime"]["reset_hour"]
        day = nb.budget_day(None, reset)
        used = nb.load_usage(reset)

        self.mode = decide_mode(s, self.watcher.present, used)
        try:
            cfg = self.prepare(self.mode, s)
        except Exception as e:
            log(f"couldn't prepare '{self.mode}': {e!r}")
            time.sleep(10)
            return 1
        ready_sig = self.current_ready_sig(s) if self.mode == "ready" else None
        sig0 = self.file_sig()
        self.mode_started = time.time()
        self.launch(cfg)
        started = time.monotonic()
        self.write_status(s, used)

        last_tick = last_save = last_status = time.monotonic()
        code = 0
        while not self.stop:
            time.sleep(TICK)
            now = time.monotonic()
            dt, last_tick = min(now - last_tick, 5.0), now

            rc = self.child.poll()
            if rc is not None:
                log(f"NostalgiaBox exited with code {rc}")
                code = rc
                if now - started < 8:  # crashed straight away: don't spin
                    time.sleep(10)
                break

            s = nb.load_settings()
            reset = s["screentime"]["reset_hour"]
            today = nb.budget_day(None, reset)
            if today != day:
                day, used = today, 0.0
                nb.save_usage(used, reset)
            if self.mode == "tv":
                used += dt

            present = self.watcher.present or (self.mode == "tv" and self.watcher.false_streak < 3)
            new_mode = decide_mode(s, present, used)
            if new_mode != self.mode:
                log(f"mode {self.mode} -> {new_mode}")
                break
            if self.file_sig() != sig0:
                log("settings changed, restarting")
                break
            if self.mode == "ready" and self.current_ready_sig(s) != ready_sig:
                log("address or login info changed, redrawing")
                break

            self.maybe_remount(s)
            if now - last_save >= USAGE_SAVE_EVERY:
                nb.save_usage(used, reset)
                last_save = now
            if now - last_status >= STATUS_EVERY:
                self.write_status(s, used)
                last_status = now

        nb.save_usage(used, reset)
        self.stop_child()
        return code


if __name__ == "__main__":
    sys.exit(Controller().run())
