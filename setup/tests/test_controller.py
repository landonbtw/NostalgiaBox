#!/usr/bin/env python3
"""Runs the real TV controller (restarted like systemd would) against a fake NostalgiaBox
and checks it picks the right screen: ready -> channels -> off air -> channels -> ready.

Run:  python3 tests/test_controller.py      (takes about a minute: it really draws the screens)
"""
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="nbctl-")
ENV = dict(os.environ, NB_STATE_DIR=TMP + "/state", NB_ETC_DIR=TMP + "/etc", NB_MEDIA_DIR=TMP + "/media",
           NB_MOUNT_DIR=TMP + "/mnt", NB_RUN_DIR=TMP + "/run", NB_TICK="0.2", NB_WATCH="0.5",
           NB_HELPER=f"{sys.executable} {ROOT}/tests/fake_helper.py", NB_FAKE_LOG=TMP + "/h.log",
           NB_FAKE_MARK=TMP + "/marks.txt")
for d in ("etc", "run", "state", "media/channel-1"):
    os.makedirs(f"{TMP}/{d}", exist_ok=True)
json.dump({"argv": [sys.executable, ROOT + "/tests/fake_nostalgiabox.py"], "cwd": None, "env": {}},
          open(TMP + "/etc/base-command.json", "w"))
sys.path.insert(0, ROOT + "/app")
os.environ.update({k: v for k, v in ENV.items() if k.startswith("NB_")})
import nbcommon as nb  # noqa: E402

ok = True
procs = {"p": None, "starts": 0}


def ensure_running():
    p = procs["p"]
    if p is None or p.poll() is not None:  # what systemd's Restart=always does
        procs["p"] = subprocess.Popen([sys.executable, ROOT + "/app/controller.py"], env=ENV,
                                      stdout=open(TMP + "/ctl.log", "a"), stderr=subprocess.STDOUT)
        procs["starts"] += 1


def marks():
    try:
        return [os.path.basename(x) for x in open(ENV["NB_FAKE_MARK"]).read().split()]
    except OSError:
        return []


def wait_for_mark(name, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        ensure_running()
        if marks() and marks()[-1] == name:
            return True
        time.sleep(0.3)
    return False


def step(label, name, timeout=90):
    global ok
    good = wait_for_mark(name, timeout)
    ok &= good
    print(("  ok   " if good else "  FAIL ") + label + ("" if good else f"   (marks so far: {marks()})"))


def save(**changes):
    s = nb.load_settings()
    s["configured"] = True
    for k, v in changes.items():
        a, b = k.split("__")
        s[a][b] = v
    nb.save_settings(s)
    return s


try:
    step("fresh box shows the ready screen", "ready.yaml")
    ready = open(TMP + "/state/screens/ready/ready.sig").read()
    print("  ok   ready screen drawn and encoded" if os.path.exists(TMP + "/state/screens/ready/ready.mp4") else "  FAIL no ready.mp4")

    with open(TMP + "/media/channel-1/ep.mp4", "wb") as f:
        f.write(b"x")
    save()
    step("a video + saved settings switches to channels", "config.yaml")
    import yaml
    cfg = yaml.safe_load(open(TMP + "/state/config.yaml"))
    good = [c["number"] for c in cfg["channels"]] == [2]
    ok &= good
    print(("  ok   " if good else "  FAIL ") + "channels config written from the saved settings")

    # stop the controller first so it can't overwrite the usage file we set up (it saves its own count on exit)
    procs["p"].terminate()
    procs["p"].wait(10)
    nb.save_usage(899.0, 0)
    save(screentime__enabled=True, screentime__hours=0.25)
    step("screen time used up shows off the air", "offair.yaml")
    used = nb.load_usage(0)
    good = used >= 899
    ok &= good
    print(("  ok   " if good else "  FAIL ") + f"usage saved to disk ({used:.0f}s)")

    save(screentime__enabled=False)
    step("turning the limit off brings channels back", "config.yaml")

    os.remove(TMP + "/media/channel-1/ep.mp4")
    step("no videos left goes back to the ready screen", "ready.yaml", timeout=60)

    end = time.time() + 15
    while time.time() < end and not nb.read_json(nb.STATUS_FILE):
        ensure_running()
        time.sleep(0.3)
    st = nb.read_json(nb.STATUS_FILE, {})
    good = st.get("mode") in ("ready", "tv", "offair")
    ok &= good
    print(("  ok   " if good else "  FAIL ") + f"status file written for the web page ({st.get('mode')})")
finally:
    p = procs["p"]
    if p:
        p.terminate()
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            p.kill()
    log = open(TMP + "/ctl.log").read() if os.path.exists(TMP + "/ctl.log") else ""
    if "Traceback" in log:
        ok = False
        print("CONTROLLER TRACEBACK:\n" + log[-1500:])

print("\nPASS" if ok else "\nFAIL")
sys.exit(0 if ok else 1)
