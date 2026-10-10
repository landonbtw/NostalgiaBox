#!/usr/bin/env python3
"""Shared code for the NostalgiaBox setup app.

Used by both the web page (server.py) and the TV controller (controller.py):
paths, settings load/save/validation, the NostalgiaBox config generator,
login storage, and a few small helpers.
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import re
import secrets
import shlex
import subprocess
import tempfile
import time
from datetime import datetime, timedelta

import yaml

# --------------------------------------------------------------------- paths
STATE_DIR = os.environ.get("NB_STATE_DIR", "/var/lib/nostalgiabox-setup")
ETC_DIR = os.environ.get("NB_ETC_DIR", "/etc/nostalgiabox-setup")
MEDIA_DIR = os.environ.get("NB_MEDIA_DIR", "/media/nostalgiabox")
MOUNT_DIR = os.environ.get("NB_MOUNT_DIR", "/mnt/nostalgiabox")
RUN_DIR = os.environ.get("NB_RUN_DIR", "/dev/shm")
HELPER_CMD = shlex.split(os.environ.get("NB_HELPER", "sudo -n /usr/local/sbin/nostalgiabox-helper"))
PORT = int(os.environ.get("NB_PORT", "8080"))

SETTINGS_FILE = os.path.join(STATE_DIR, "settings.json")
AUTH_FILE = os.path.join(STATE_DIR, "auth.json")
CONTROL_FILE = os.path.join(STATE_DIR, "control.json")
USAGE_FILE = os.path.join(STATE_DIR, "usage.json")
REAL_CONFIG = os.path.join(STATE_DIR, "config.yaml")
SCREENS_DIR = os.path.join(STATE_DIR, "screens")
STATUS_FILE = os.path.join(RUN_DIR, "nostalgiabox-tv-status.json")
BASE_FILE = os.path.join(ETC_DIR, "base-command.json")

MAX_CHANNELS = 30
VIDEO_EXTS = [".mp4", ".mkv", ".avi", ".m4v", ".mov", ".mpg", ".mpeg", ".wmv", ".webm", ".ts"]
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "nostalgia"
SKIP_DIRS = {"$recycle.bin", "system volume information", "@eadir", "lost+found", "__macosx"}

AUDIO_DEVICES = {
    "hdmi0": "alsa/hdmi:CARD=vc4hdmi0,DEV=0",
    "hdmi1": "alsa/hdmi:CARD=vc4hdmi1,DEV=0",
}


# --------------------------------------------------------------- small utils
def atomic_write(path: str, data, mode: int = 0o644) -> None:
    """Write a file so a power cut never leaves it half-written."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data if isinstance(data, bytes) else data.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: str, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _int(v, lo, hi, default):
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _float(v, lo, hi, default):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _bool(v) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _clean_text(v, maxlen) -> str:
    s = re.sub(r"[\x00-\x1f\x7f]", "", str(v or "")).strip()
    return s[:maxlen]


# ---------------------------------------------------------------- settings
def default_channel() -> dict:
    return {
        "name": "",
        "source": "local",  # local | network
        "net": {"type": "smb", "host": "", "share": "", "subfolder": "",
                "username": "", "has_password": False},
        "exclude_seasons": "",
        "exclude": "",
    }


def default_settings() -> dict:
    return {
        "configured": False,
        "channel_count": 3,
        "first_channel": 2,
        "channels": [default_channel() for _ in range(MAX_CHANNELS)],
        "playback": {"tune_in": "random", "start_channel": 0, "start_offset_min": 6,
                     "start_offset_max": 10, "transition": "none", "bridge_seconds": 0.8,
                     "channel_bug_seconds": 4, "force_4_3": False},
        "sound": {"output": "auto", "custom_device": "", "initial_volume": 70, "volume_step": 5},
        "picture": {"crt": True, "curvature": 0.12, "scanlines": True,
                    "ui_color": "#4DFF5A", "glow": True},
        "screentime": {"enabled": False, "hours": 2.0, "reset_hour": 0},
    }


HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
SMB_SHARE_RE = re.compile(r"^[\w][\w .-]{0,79}$")
NFS_EXPORT_RE = re.compile(r"^/[\w .@+/-]{0,199}$")
USER_RE = re.compile(r"^[\w.@\\-]{0,64}$")
SEASON_RE = re.compile(r"^\d{1,3}(-\d{1,3})?$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
DEVICE_RE = re.compile(r"^[\w:=,./@+ -]{0,120}$")


def clean_subfolder(value) -> str:
    """A folder path inside a share: no '..', no leading slash, no odd characters."""
    parts = [p for p in re.split(r"[\\/]+", str(value or "")) if p not in ("", ".")]
    for p in parts:
        if p == ".." or len(p) > 150 or re.search(r"[\x00-\x1f]", p):
            raise ValueError("That folder name has characters we can't use.")
    return "/".join(parts)


def sanitize_channel(raw: dict, old: dict | None = None) -> dict:
    ch = default_channel()
    raw = raw if isinstance(raw, dict) else {}
    ch["name"] = _clean_text(raw.get("name"), 40)
    ch["source"] = "network" if raw.get("source") == "network" else "local"
    net = raw.get("net") if isinstance(raw.get("net"), dict) else {}
    n = ch["net"]
    n["type"] = "nfs" if net.get("type") == "nfs" else "smb"
    host = _clean_text(net.get("host"), 253)
    if host and not HOST_RE.match(host):
        raise ValueError("The server name can only use letters, numbers, dots and dashes.")
    n["host"] = host
    share = _clean_text(net.get("share"), 200)
    if share:
        if n["type"] == "smb":
            share = share.strip("/\\")
            if not SMB_SHARE_RE.match(share):
                raise ValueError("The share name can't contain slashes or unusual characters. "
                                 "Put sub-folders in the Folder box instead.")
        else:
            if not share.startswith("/"):
                share = "/" + share
            share = share.rstrip("/") or "/"
            if not NFS_EXPORT_RE.match(share) or ".." in share.split("/"):
                raise ValueError("The NFS export path has characters we can't use.")
    n["share"] = share
    n["subfolder"] = clean_subfolder(net.get("subfolder"))
    user = _clean_text(net.get("username"), 64)
    if not USER_RE.match(user):
        raise ValueError("The username has characters we can't use.")
    n["username"] = user if n["type"] == "smb" else ""
    n["has_password"] = bool((old or {}).get("net", {}).get("has_password")) if old else False
    # Skip-lists
    seasons = [t for t in re.split(r"[,\s]+", str(raw.get("exclude_seasons") or "").strip()) if t]
    for t in seasons:
        if not SEASON_RE.match(t):
            raise ValueError("'Skip seasons' should look like 6-25 or 3 (separate several with commas).")
    ch["exclude_seasons"] = ", ".join(seasons)
    pats = [p.strip() for p in re.split(r"[\n,]+", str(raw.get("exclude") or "")) if p.strip()]
    ch["exclude"] = ", ".join(_clean_text(p, 60) for p in pats[:20])
    return ch


def sanitize_settings(raw: dict, old: dict | None = None) -> dict:
    """Turn whatever the browser sent into a safe, complete settings dict."""
    base = default_settings()
    raw = raw if isinstance(raw, dict) else {}
    old = old or base
    s = base
    s["configured"] = bool(raw.get("configured", old.get("configured", False)))
    s["channel_count"] = _int(raw.get("channel_count"), 1, MAX_CHANNELS, old.get("channel_count", 3))
    s["first_channel"] = _int(raw.get("first_channel"), 1, 99, old.get("first_channel", 2))

    raw_ch = raw.get("channels") if isinstance(raw.get("channels"), list) else []
    old_ch = old.get("channels") or []
    channels = []
    for i in range(MAX_CHANNELS):
        r = raw_ch[i] if i < len(raw_ch) else (old_ch[i] if i < len(old_ch) else {})
        o = old_ch[i] if i < len(old_ch) else None
        try:
            channels.append(sanitize_channel(r, o))
        except ValueError as e:
            if i < s["channel_count"]:
                raise ValueError(f"Channel {s['first_channel'] + i}: {e}")
            channels.append(default_channel())
    s["channels"] = channels

    p = raw.get("playback") if isinstance(raw.get("playback"), dict) else {}
    op = old.get("playback", {})
    b = s["playback"]
    b["tune_in"] = p.get("tune_in") if p.get("tune_in") in ("random", "resume", "broadcast") else op.get("tune_in", "random")
    lo = _int(p.get("start_offset_min"), 0, 600, op.get("start_offset_min", 6))
    hi = _int(p.get("start_offset_max"), 0, 600, op.get("start_offset_max", 10))
    b["start_offset_min"], b["start_offset_max"] = min(lo, hi), max(lo, hi)
    b["transition"] = p.get("transition") if p.get("transition") in ("none", "glitch", "static") else op.get("transition", "none")
    b["bridge_seconds"] = round(_float(p.get("bridge_seconds"), 0, 5, op.get("bridge_seconds", 0.8)), 2)
    b["channel_bug_seconds"] = round(_float(p.get("channel_bug_seconds"), 0, 30, op.get("channel_bug_seconds", 4)), 1)
    b["force_4_3"] = _bool(p.get("force_4_3", op.get("force_4_3", False)))
    numbers = [s["first_channel"] + i for i in range(s["channel_count"])]
    sc = _int(p.get("start_channel"), 0, 999, 0)
    b["start_channel"] = sc if sc in numbers else 0

    so = raw.get("sound") if isinstance(raw.get("sound"), dict) else {}
    oo = old.get("sound", {})
    d = s["sound"]
    d["output"] = so.get("output") if so.get("output") in ("auto", "hdmi0", "hdmi1", "custom") else oo.get("output", "auto")
    dev = _clean_text(so.get("custom_device", oo.get("custom_device", "")), 120)
    if not DEVICE_RE.match(dev):
        raise ValueError("The custom sound device name has characters we can't use.")
    d["custom_device"] = dev
    d["initial_volume"] = _int(so.get("initial_volume"), 0, 100, oo.get("initial_volume", 70))
    d["volume_step"] = _int(so.get("volume_step"), 1, 25, oo.get("volume_step", 5))

    pi = raw.get("picture") if isinstance(raw.get("picture"), dict) else {}
    opi = old.get("picture", {})
    c = s["picture"]
    c["crt"] = _bool(pi.get("crt", opi.get("crt", True)))
    c["curvature"] = round(_float(pi.get("curvature"), 0, 0.4, opi.get("curvature", 0.12)), 3)
    c["scanlines"] = _bool(pi.get("scanlines", opi.get("scanlines", True)))
    color = str(pi.get("ui_color", opi.get("ui_color", "#4DFF5A")))
    c["ui_color"] = color if COLOR_RE.match(color) else "#4DFF5A"
    c["glow"] = _bool(pi.get("glow", opi.get("glow", True)))

    st = raw.get("screentime") if isinstance(raw.get("screentime"), dict) else {}
    ost = old.get("screentime", {})
    t = s["screentime"]
    t["enabled"] = _bool(st.get("enabled", ost.get("enabled", False)))
    t["hours"] = round(_float(st.get("hours"), 0.25, 24, ost.get("hours", 2.0)), 2)
    t["reset_hour"] = _int(st.get("reset_hour"), 0, 23, ost.get("reset_hour", 0))
    return s


def load_settings() -> dict:
    raw = read_json(SETTINGS_FILE)
    if raw is None:
        return default_settings()
    try:
        return sanitize_settings(raw, raw)
    except ValueError:
        return default_settings()


def save_settings(s: dict) -> None:
    atomic_write(SETTINGS_FILE, json.dumps(s, indent=1))


def signal_controller() -> None:
    """Tell the TV controller to restart NostalgiaBox with the newest settings."""
    atomic_write(CONTROL_FILE, json.dumps({"seq": time.time_ns()}))


# ---------------------------------------------------------- channels / paths
def active_channels(s: dict) -> list[tuple[int, int, dict]]:
    """[(slot index, channel number, channel dict)] for the channels in use."""
    return [(i, s["first_channel"] + i, s["channels"][i]) for i in range(s["channel_count"])]


def channel_display_name(ch: dict, number: int) -> str:
    return ch["name"] or f"Channel {number}"


def local_dir(i: int) -> str:
    return os.path.join(MEDIA_DIR, f"channel-{i + 1}")


def mount_point(i: int) -> str:
    return os.path.join(MOUNT_DIR, f"ch{i + 1}")


def channel_ready(ch: dict) -> bool:
    if ch["source"] == "local":
        return True
    n = ch["net"]
    return bool(n["host"] and n["share"])


def channel_path(i: int, ch: dict) -> str:
    if ch["source"] == "local":
        return local_dir(i)
    sub = ch["net"]["subfolder"]
    return os.path.join(mount_point(i), sub) if sub else mount_point(i)


def is_video(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in VIDEO_EXTS


def count_videos(path: str, limit: int = 20000, max_seconds: float = 6.0) -> tuple[int, bool]:
    """Count video files under path. Returns (count, gave_up_early)."""
    start = time.monotonic()
    count = 0
    stack = [path]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    if time.monotonic() - start > max_seconds or count >= limit:
                        return count, True
                    try:
                        if e.is_dir(follow_symlinks=True):
                            if not e.name.startswith(".") and e.name.lower() not in SKIP_DIRS:
                                stack.append(e.path)
                        elif is_video(e.name) and not e.name.startswith("."):
                            count += 1
                    except OSError:
                        continue
        except OSError:
            continue
    return count, False


def has_video(path: str, max_seconds: float = 4.0) -> bool:
    start = time.monotonic()
    stack = [path]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    if time.monotonic() - start > max_seconds:
                        return False
                    try:
                        if e.is_dir(follow_symlinks=True):
                            if not e.name.startswith(".") and e.name.lower() not in SKIP_DIRS:
                                stack.append(e.path)
                        elif is_video(e.name) and not e.name.startswith("."):
                            return True
                    except OSError:
                        continue
        except OSError:
            continue
    return False


# ---------------------------------------------------------- config for NostalgiaBox
def _audio_device(s: dict) -> str | None:
    out = s["sound"]["output"]
    if out in AUDIO_DEVICES:
        return AUDIO_DEVICES[out]
    if out == "custom" and s["sound"]["custom_device"]:
        return s["sound"]["custom_device"]
    return None


def _common_config(s: dict) -> dict:
    pic, snd = s["picture"], s["sound"]
    cfg = {
        "ui": {"font": "VT323", "color": pic["ui_color"], "glow": pic["glow"]},
        "crt": {"enabled": pic["crt"], "curvature": pic["curvature"], "scanlines": pic["scanlines"]},
        "initial_volume": snd["initial_volume"],
        "volume_step": snd["volume_step"],
        "video_extensions": list(VIDEO_EXTS),
        "scan_recursive": True,
    }
    dev = _audio_device(s)
    if dev:
        cfg["audio_device"] = dev
    return cfg


def build_config(s: dict, include_empty: bool = False) -> dict:
    """The config.yaml NostalgiaBox runs with, built from the settings page."""
    chans = []
    for i, number, ch in active_channels(s):
        if not channel_ready(ch):
            continue
        path = channel_path(i, ch)
        if not include_empty and not has_video(path):
            continue
        entry = {"number": number, "name": channel_display_name(ch, number), "path": path}
        seasons = [t for t in re.split(r"[,\s]+", ch["exclude_seasons"]) if t]
        if seasons:
            entry["exclude_seasons"] = seasons
        pats = [p.strip() for p in ch["exclude"].split(",") if p.strip()]
        if pats:
            entry["exclude"] = pats
        chans.append(entry)
    b = s["playback"]
    cfg = {"channels": chans, "tune_in": b["tune_in"]}
    numbers = [c["number"] for c in chans]
    start = b["start_channel"] if b["start_channel"] in numbers else (numbers[0] if numbers else s["first_channel"])
    cfg["start_channel"] = start
    cfg["force_4_3"] = b["force_4_3"]
    cfg["start_offset"] = (b["start_offset_min"] if b["start_offset_min"] == b["start_offset_max"]
                           else [b["start_offset_min"], b["start_offset_max"]])
    cfg["transition"] = b["transition"]
    cfg["bridge_seconds"] = b["bridge_seconds"]
    cfg["channel_bug_seconds"] = b["channel_bug_seconds"]
    cfg.update(_common_config(s))
    return cfg


def build_special_config(s: dict, name: str, folder: str) -> dict:
    """One-channel config used for the 'box is ready' and 'off air' screens."""
    cfg = {
        "channels": [{"number": s["first_channel"], "name": name, "path": folder}],
        "tune_in": "random",
        "start_channel": s["first_channel"],
        "force_4_3": False,
        "start_offset": 0,
        "transition": "none",
        "bridge_seconds": 0,
        "channel_bug_seconds": 3,
    }
    cfg.update(_common_config(s))
    return cfg


def write_yaml(path: str, cfg: dict, header: str = "") -> None:
    text = header + yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False, allow_unicode=True)
    atomic_write(path, text)


# -------------------------------------------------------- how to launch NostalgiaBox
def load_base() -> dict | None:
    d = read_json(BASE_FILE)
    if isinstance(d, dict) and isinstance(d.get("argv"), list) and d["argv"]:
        return d
    return None


def _strip_args(argv: list[str]) -> list[str]:
    out, skip = [], False
    for a in argv:
        if skip:
            skip = False
            continue
        if a in ("--config", "-c"):
            skip = True
            continue
        if a.startswith("--config=") or a in ("--check", "--dry-run", "--list-audio"):
            continue
        out.append(a)
    return out


def base_invocation(extra: list[str], config_path: str):
    """(argv, cwd, env) to run NostalgiaBox the same way its own service does."""
    base = load_base()
    if base is None:
        return None
    argv = _strip_args(base["argv"]) + list(extra) + ["--config", config_path]
    env = dict(os.environ)
    env.update({k: str(v) for k, v in (base.get("env") or {}).items()})
    cwd = base.get("cwd") or None
    if cwd and not os.path.isdir(cwd):
        cwd = None
    return argv, cwd, env


# ------------------------------------------------------------------ login
ITERATIONS = 200_000


def _hash(password: str, salt: bytes, iterations: int) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations).hex()


def _write_auth(user: str, password: str, is_default: bool) -> dict:
    salt = secrets.token_bytes(16)
    d = {"username": user, "salt": salt.hex(), "iterations": ITERATIONS,
         "hash": _hash(password, salt, ITERATIONS), "default": is_default}
    atomic_write(AUTH_FILE, json.dumps(d), mode=0o600)
    return d


def load_auth() -> dict:
    d = read_json(AUTH_FILE)
    if not d or "hash" not in d:
        d = _write_auth(DEFAULT_USER, DEFAULT_PASSWORD, True)
    return d


def verify_login(user: str, password: str) -> bool:
    d = load_auth()
    ok_user = hmac.compare_digest(str(user).strip().lower().encode(), d["username"].lower().encode())
    calc = _hash(str(password), bytes.fromhex(d["salt"]), int(d["iterations"]))
    return hmac.compare_digest(calc.encode(), d["hash"].encode()) and ok_user


def set_password(new_password: str) -> None:
    d = load_auth()
    _write_auth(d["username"], new_password, False)


def auth_is_default() -> bool:
    d = read_json(AUTH_FILE)
    return True if d is None else bool(d.get("default", False))


def auth_username() -> str:
    d = read_json(AUTH_FILE)
    return (d or {}).get("username", DEFAULT_USER)


# --------------------------------------------------------------- screen time
def budget_day(now: datetime | None = None, reset_hour: int = 0) -> str:
    now = now or datetime.now()
    if now.hour < reset_hour:
        now = now - timedelta(days=1)
    return now.strftime("%Y-%m-%d")


def load_usage(reset_hour: int, now: datetime | None = None) -> float:
    day = budget_day(now, reset_hour)
    d = read_json(USAGE_FILE, {})
    return float(d.get("seconds", 0)) if d.get("day") == day else 0.0


def save_usage(seconds: float, reset_hour: int, now: datetime | None = None) -> None:
    atomic_write(USAGE_FILE, json.dumps({"day": budget_day(now, reset_hour), "seconds": round(seconds, 1)}))


# ------------------------------------------------------------------ network
def local_ip() -> str | None:
    try:
        out = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=3).stdout.split()
    except Exception:
        return None
    for tok in out:
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", tok) and not tok.startswith("169.254."):
            return tok
    return None


def short_hostname() -> str:
    try:
        return subprocess.run(["hostname"], capture_output=True, text=True, timeout=3).stdout.strip() or "nostalgiabox"
    except Exception:
        return "nostalgiabox"


def call_helper(cmd: str, payload: dict | None = None, timeout: int = 90) -> dict:
    """Run one action through the root helper (the only thing the web page can run as root)."""
    try:
        r = subprocess.run(HELPER_CMD + [cmd], input=json.dumps(payload or {}), capture_output=True,
                           text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "That took too long (the server may be unreachable)."}
    except OSError as e:
        return {"ok": False, "error": f"Could not run the helper: {e}"}
    try:
        return json.loads(r.stdout)
    except ValueError:
        return {"ok": False, "error": (r.stderr or r.stdout or "The helper gave no answer.").strip()[:300]}
