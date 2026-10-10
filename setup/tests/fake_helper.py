#!/usr/bin/env python3
"""Stand-in for nostalgiabox-helper so the setup page can be tested without root.
Logs every request to $NB_FAKE_LOG and fakes a network share for browsing."""
import json, os, sys

cmd = sys.argv[1]
req = json.loads(sys.stdin.read() or "{}")
with open(os.environ["NB_FAKE_LOG"], "a") as f:
    f.write(json.dumps({"cmd": cmd, "req": req}) + "\n")


def touch(p):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(b"x")


out = {"ok": True}
if cmd == "browse-mount":
    if req["net"]["host"] == "badhost":
        out = {"ok": False, "error": "Can't reach that server. Check it is on, on the same network, and the address is right."}
    else:
        b = os.path.join(os.environ["NB_MOUNT_DIR"], ".browse")
        touch(b + "/Kids TV/Arthur/Season 1/a.mp4")
        touch(b + "/Kids TV/Arthur/Season 2/b.mp4")
        touch(b + "/Kids TV/Dragon Tales/c.mkv")
        touch(b + "/Movies/d.mp4")
        touch(b + "/$RECYCLE.BIN/e.mp4")
elif cmd == "apply-mounts":
    out["results"] = [{"id": c["id"], "mounted": True, "error": ""} for c in req.get("channels", [])]
print(json.dumps(out))
