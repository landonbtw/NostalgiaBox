#!/usr/bin/env python3
"""NostalgiaBox setup page: one web page to set up the whole box.

Runs as the NostalgiaBox user (never root). Anything that needs root (mounting
network shares, reboot, time zone) goes through nostalgiabox-helper.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import traceback
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nbcommon as nb  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
VERSION = "1.0"
SESSION_TTL = 12 * 3600
MAX_JSON = 1_000_000
MAX_UPLOAD = 40 * 1024 ** 3
SPACE_MARGIN = 300 * 1024 ** 2
SAVE_LOCK = threading.Lock()


class ApiError(Exception):
    def __init__(self, message: str, code: int = 400):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- sessions
_sessions: dict[str, float] = {}
_fails: dict[str, list[float]] = {}
_lock = threading.Lock()


def new_session() -> str:
    tok = secrets.token_urlsafe(32)
    with _lock:
        now = time.time()
        for k in [k for k, exp in _sessions.items() if exp < now]:
            del _sessions[k]
        _sessions[tok] = now + SESSION_TTL
    return tok


def session_ok(tok: str | None) -> bool:
    if not tok:
        return False
    with _lock:
        exp = _sessions.get(tok)
        return bool(exp and exp > time.time())


def drop_other_sessions(keep: str | None) -> None:
    with _lock:
        for k in [k for k in _sessions if k != keep]:
            del _sessions[k]


def login_locked(ip: str) -> bool:
    with _lock:
        recent = [t for t in _fails.get(ip, []) if t > time.time() - 300]
        _fails[ip] = recent
        return len(recent) >= 6


def note_fail(ip: str) -> None:
    with _lock:
        _fails.setdefault(ip, []).append(time.time())


# ------------------------------------------------------------------ helpers
def safe_parts(rel: str) -> list[str]:
    parts = [p for p in re.split(r"[\\/]+", rel or "") if p not in ("", ".")]
    if not parts:
        raise ApiError("No file name given.")
    for p in parts:
        if p == ".." or p.startswith(".") or len(p) > 150 or any(ord(c) < 32 for c in p):
            raise ApiError("That file name has characters we can't use.")
    return parts


def slot_from(q: dict) -> int:
    try:
        i = int(q.get("channel", [""])[0]) - 1
    except ValueError:
        raise ApiError("Bad channel.")
    if not 0 <= i < nb.MAX_CHANNELS:
        raise ApiError("Bad channel.")
    return i


def under(base: str, path: str) -> bool:
    b, p = os.path.realpath(base), os.path.realpath(path)
    return p == b or p.startswith(b + os.sep)


def status_info(s: dict) -> dict:
    st = nb.read_json(nb.STATUS_FILE, {}) or {}
    fresh = time.time() - st.get("updated", 0) < 40
    media = nb.MEDIA_DIR if os.path.isdir(nb.MEDIA_DIR) else "/"
    try:
        du = shutil.disk_usage(media)
        free, total = du.free, du.total
    except OSError:
        free = total = 0
    return {
        "tv_mode": st.get("mode") if fresh else None,
        "used_seconds": st.get("used_seconds") if fresh else None,
        "budget_seconds": st.get("budget_seconds") if fresh else None,
        "ip": nb.local_ip(), "hostname": nb.short_hostname(), "port": nb.PORT,
        "free_bytes": free, "total_bytes": total,
        "default_password": nb.auth_is_default(), "username": nb.auth_username(),
        "can_check": nb.load_base() is not None, "version": VERSION,
    }


def run_check():
    inv = nb.base_invocation(["--check"], nb.REAL_CONFIG)
    if inv is None:
        return None
    argv, cwd, env = inv
    try:
        r = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=45)
        return {"ok": r.returncode == 0, "output": (r.stdout + r.stderr).strip()[-4000:]}
    except Exception as e:
        return {"ok": False, "output": f"Couldn't run the check: {e}"}


# ------------------------------------------------------------------- API
def h_state(h):
    s = nb.load_settings()
    h.send_json({"settings": s, "status": status_info(s), "max_channels": nb.MAX_CHANNELS})


def h_counts(h):
    s = nb.load_settings()
    out = []
    for i, number, ch in nb.active_channels(s):
        e = {"index": i, "number": number, "count": 0, "state": "ok", "message": "", "more": False}
        if not nb.channel_ready(ch):
            e.update(state="incomplete", message="Not filled in yet.")
        elif ch["source"] == "network" and not os.path.ismount(nb.mount_point(i)):
            e.update(state="offline", message="Not connected right now. The box keeps retrying.")
        else:
            e["count"], e["more"] = nb.count_videos(nb.channel_path(i, ch), limit=20000, max_seconds=5)
            if e["count"] == 0:
                e.update(state="empty", message="No videos found here yet.")
        out.append(e)
    h.send_json({"counts": out})


def h_save(h):
    body = h.read_json()
    with SAVE_LOCK:
        old = nb.load_settings()
        try:
            s = nb.sanitize_settings(body.get("settings"), old)
        except ValueError as e:
            raise ApiError(str(e), 400)
        s["configured"] = True
        passwords = body.get("passwords") if isinstance(body.get("passwords"), dict) else {}
        warnings: list[str] = []

        items, net_slots = [], set()
        for i, number, ch in nb.active_channels(s):
            if ch["source"] == "network" and nb.channel_ready(ch):
                pw = passwords.get(str(i))
                items.append({"id": i + 1, "password": pw if isinstance(pw, str) else None,
                              "net": {k: ch["net"][k] for k in ("type", "host", "share", "username")}})
                net_slots.add(i)
        had_net = any(c["source"] == "network" and nb.channel_ready(c) for _i, _n, c in nb.active_channels(old))
        if items or had_net:
            res = nb.call_helper("apply-mounts", {"channels": items}, timeout=240)
            if not res.get("ok"):
                warnings.append(res.get("error") or "Couldn't set up the network folders.")
            else:
                for r in res.get("results", []):
                    if not r.get("mounted"):
                        num = s["first_channel"] + r["id"] - 1
                        warnings.append(f"Channel {num}: {r.get('error') or 'could not connect'}")
        for it in items:
            ch = s["channels"][it["id"] - 1]
            if it["password"] is not None:
                ch["net"]["has_password"] = bool(it["password"])
            if not ch["net"]["username"]:
                ch["net"]["has_password"] = False
        for i in range(nb.MAX_CHANNELS):
            if i not in net_slots:
                s["channels"][i]["net"]["has_password"] = False

        for i, _n, ch in nb.active_channels(s):
            if ch["source"] == "local":
                try:
                    os.makedirs(nb.local_dir(i), exist_ok=True)
                except OSError as e:
                    warnings.append(f"Couldn't create the folder for channel {i + s['first_channel']}: {e}")

        nb.save_settings(s)
        cfg = nb.build_config(s)
        nb.write_yaml(nb.REAL_CONFIG, cfg, "# Written automatically by the NostalgiaBox setup page.\n")
        check = run_check() if cfg["channels"] else None
        nb.signal_controller()
    h.send_json({"ok": True, "settings": s, "warnings": warnings, "check": check,
                 "on_air": [c["number"] for c in cfg["channels"]]})


def h_password(h):
    b = h.read_json()
    if not nb.verify_login(nb.auth_username(), str(b.get("current", ""))):
        raise ApiError("Your current password isn't right.", 403)
    new = str(b.get("new", ""))
    if len(new) < 6:
        raise ApiError("Use at least 6 characters.")
    if new == nb.DEFAULT_PASSWORD:
        raise ApiError("Please pick something other than the starting password.")
    nb.set_password(new)
    drop_other_sessions(h.token())
    h.send_json({"ok": True})


def h_files(h):
    i = slot_from(h.query())
    base = nb.local_dir(i)
    files, total, truncated = [], 0, False
    for root, dirs, names in os.walk(base):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for n in sorted(names):
            if n.startswith(".") or not nb.is_video(n):
                continue
            p = os.path.join(root, n)
            try:
                size = os.path.getsize(p)
            except OSError:
                continue
            total += size
            if len(files) < 2000:
                files.append({"path": os.path.relpath(p, base).replace(os.sep, "/"), "size": size})
            else:
                truncated = True
    h.send_json({"files": files, "total": total, "truncated": truncated})


def h_upload(h):
    q = h.query()
    i = slot_from(q)
    parts = safe_parts(q.get("path", [""])[0])
    if not nb.is_video(parts[-1]):
        raise ApiError("Only video files can be added (mp4, mkv, avi, m4v, mov...).", 415)
    base = nb.local_dir(i)
    dest = os.path.join(base, *parts)
    if not under(base, dest):
        raise ApiError("Bad path.")
    try:
        length = int(h.headers.get("Content-Length", "-1"))
    except ValueError:
        length = -1
    if length < 0:
        raise ApiError("No file size sent.", 411)
    if length > MAX_UPLOAD:
        raise ApiError("That file is too big.", 413)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if length + SPACE_MARGIN > shutil.disk_usage(os.path.dirname(dest)).free:
        raise ApiError("Not enough free space on the box for this file.", 507)
    tmp = dest + ".part"
    remaining = length
    try:
        with open(tmp, "wb") as f:
            while remaining > 0:
                chunk = h.rfile.read(min(1 << 20, remaining))
                if not chunk:
                    break
                f.write(chunk)
                remaining -= len(chunk)
        if remaining:
            raise ApiError("The upload was interrupted.", 400)
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    h.send_json({"ok": True, "path": "/".join(parts), "size": length})


def h_delete_file(h):
    b = h.read_json()
    try:
        i = int(b.get("channel")) - 1
    except (TypeError, ValueError):
        raise ApiError("Bad channel.")
    if not 0 <= i < nb.MAX_CHANNELS:
        raise ApiError("Bad channel.")
    parts = safe_parts(str(b.get("path", "")))
    base = nb.local_dir(i)
    target = os.path.join(base, *parts)
    if not under(base, target) or not os.path.isfile(target):
        raise ApiError("File not found.", 404)
    base_real = os.path.realpath(base)
    d = os.path.dirname(os.path.realpath(target))
    os.unlink(target)
    while d != base_real and d.startswith(base_real + os.sep):
        try:
            os.rmdir(d)
        except OSError:
            break
        d = os.path.dirname(d)
    h.send_json({"ok": True})


BROWSE_DIR = os.path.join(nb.MOUNT_DIR, ".browse")
_net = {"connected": False}


def h_net_connect(h):
    b = h.read_json()
    try:
        ch = nb.sanitize_channel({"source": "network", "net": b.get("net")})
    except ValueError as e:
        raise ApiError(str(e))
    n = ch["net"]
    if not (n["host"] and n["share"]):
        raise ApiError("Fill in the server and the share first.")
    req = {"net": {k: n[k] for k in ("type", "host", "share", "username")},
           "password": b.get("password") if isinstance(b.get("password"), str) else None}
    saved = b.get("saved_channel")
    if req["password"] is None and isinstance(saved, int):
        req["saved_channel"] = saved
    res = nb.call_helper("browse-mount", req, timeout=70)
    _net["connected"] = bool(res.get("ok"))
    if not res.get("ok"):
        raise ApiError(res.get("error") or "Couldn't connect.", 502)
    h.send_json({"ok": True})


def h_net_ls(h):
    if not _net["connected"]:
        raise ApiError("Connect to the server first.", 409)
    try:
        sub = nb.clean_subfolder(h.query().get("path", [""])[0])
    except ValueError as e:
        raise ApiError(str(e))
    full = os.path.join(BROWSE_DIR, sub) if sub else BROWSE_DIR
    if not under(BROWSE_DIR, full):
        raise ApiError("Bad path.")
    dirs, here = [], 0
    try:
        with os.scandir(full) as it:
            for e in it:
                try:
                    if e.is_dir(follow_symlinks=True):
                        if not e.name.startswith(".") and e.name.lower() not in nb.SKIP_DIRS:
                            dirs.append(e.name)
                    elif nb.is_video(e.name) and not e.name.startswith("."):
                        here += 1
                except OSError:
                    continue
    except OSError as e:
        raise ApiError(f"Couldn't open that folder ({e.strerror or e}).", 502)
    total, more = nb.count_videos(full, limit=5000, max_seconds=3)
    h.send_json({"path": sub, "dirs": sorted(dirs, key=str.lower), "videos_here": here,
                 "episodes": total, "episodes_more": more})


def h_net_disconnect(h):
    _net["connected"] = False
    nb.call_helper("browse-umount", {}, timeout=40)
    h.send_json({"ok": True})


def h_timezones(h):
    try:
        zones = subprocess.run(["timedatectl", "list-timezones"], capture_output=True, text=True, timeout=10).stdout.split()
        cur = subprocess.run(["timedatectl", "show", "-p", "Timezone", "--value"], capture_output=True,
                             text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        zones, cur = [], ""
    h.send_json({"zones": zones, "current": cur})


def h_system(h):
    b = h.read_json()
    action = b.get("action")
    if action == "reboot":
        res = nb.call_helper("power", {"action": "reboot"})
    elif action == "shutdown":
        res = nb.call_helper("power", {"action": "poweroff"})
    elif action == "restart-tv":
        nb.signal_controller()
        res = {"ok": True}
    elif action == "timezone":
        res = nb.call_helper("set-timezone", {"tz": str(b.get("value", ""))})
        if res.get("ok"):
            nb.signal_controller()
    else:
        raise ApiError("Unknown action.")
    if not res.get("ok"):
        raise ApiError(res.get("error") or "That didn't work.", 502)
    h.send_json({"ok": True})


def h_logout(h):
    tok = h.token()
    with _lock:
        _sessions.pop(tok, None)
    h.send_json({"ok": True}, clear_cookie=True)


ROUTES = {
    ("GET", "/api/state"): h_state,
    ("GET", "/api/counts"): h_counts,
    ("POST", "/api/settings"): h_save,
    ("POST", "/api/password"): h_password,
    ("GET", "/api/files"): h_files,
    ("PUT", "/api/upload"): h_upload,
    ("POST", "/api/files/delete"): h_delete_file,
    ("POST", "/api/net/connect"): h_net_connect,
    ("GET", "/api/net/ls"): h_net_ls,
    ("POST", "/api/net/disconnect"): h_net_disconnect,
    ("GET", "/api/timezones"): h_timezones,
    ("POST", "/api/system"): h_system,
    ("POST", "/api/logout"): h_logout,
}


# ------------------------------------------------------------- HTTP plumbing
class Handler(BaseHTTPRequestHandler):
    server_version = "NostalgiaBoxSetup"
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt, *args):  # keep the journal quiet
        pass

    def query(self) -> dict:
        return parse_qs(urlparse(self.path).query)

    def token(self) -> str | None:
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        c = SimpleCookie()
        try:
            c.load(raw)
        except Exception:
            return None
        m = c.get("nb_session")
        return m.value if m else None

    def send_json(self, obj, code=200, set_cookie=None, clear_cookie=False):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if set_cookie:
            self.send_header("Set-Cookie", f"nb_session={set_cookie}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_TTL}")
        if clear_cookie:
            self.send_header("Set-Cookie", "nb_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")
        self.end_headers()
        self.wfile.write(data)

    def read_json(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = 0
        if n > MAX_JSON:
            raise ApiError("Request too large.", 413)
        try:
            d = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            raise ApiError("Bad request.")
        if not isinstance(d, dict):
            raise ApiError("Bad request.")
        return d

    def serve_index(self):
        with open(os.path.join(HERE, "index.html"), "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_PUT(self):
        self.route("PUT")

    def route(self, method: str):
        path = urlparse(self.path).path
        try:
            if method == "GET" and path in ("/", "/index.html"):
                return self.serve_index()
            if method == "GET" and path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if not path.startswith("/api/"):
                return self.send_json({"error": "Not found"}, 404)
            if method != "GET" and self.headers.get("X-NB") != "1":
                return self.send_json({"error": "Bad request"}, 400)
            if method == "POST" and path == "/api/login":
                return self.login()
            if not session_ok(self.token()):
                return self.send_json({"error": "login"}, 401)
            fn = ROUTES.get((method, path))
            if not fn:
                return self.send_json({"error": "Not found"}, 404)
            fn(self)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except ApiError as e:
            try:
                self.send_json({"error": str(e)}, e.code)
            except OSError:
                pass
        except Exception:
            traceback.print_exc()
            try:
                self.send_json({"error": "Something went wrong on the box."}, 500)
            except OSError:
                pass

    def login(self):
        ip = self.client_address[0]
        if login_locked(ip):
            raise ApiError("Too many tries. Wait a few minutes and try again.", 429)
        b = self.read_json()
        if not nb.verify_login(str(b.get("username", "")), str(b.get("password", ""))):
            note_fail(ip)
            time.sleep(0.8)
            raise ApiError("That username or password isn't right.", 401)
        self.send_json({"ok": True}, set_cookie=new_session())


def main():
    nb.load_auth()  # creates the starting login on first run
    for d in (nb.STATE_DIR, nb.MEDIA_DIR):
        try:
            os.makedirs(d, exist_ok=True)
        except OSError as e:
            print(f"warning: can't create {d}: {e}", file=sys.stderr)
    srv = ThreadingHTTPServer(("0.0.0.0", nb.PORT), Handler)
    srv.daemon_threads = True
    print(f"NostalgiaBox setup page on port {nb.PORT}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
