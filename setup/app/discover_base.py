#!/usr/bin/env python3
"""Find out how NostalgiaBox's own systemd service starts the program.

The setup app runs NostalgiaBox the same way (same program, same folder, same
environment) so the TV, sound and remote keep working exactly as they do
today. This is run once by the installer and writes
/etc/nostalgiabox-setup/base-command.json.

Usage: discover_base.py --unit nostalgiabox.service --out /etc/nostalgiabox-setup/base-command.json
       discover_base.py --unit-file /path/to/unit --out out.json      (for testing)
"""
import argparse
import json
import os
import pwd
import re
import shlex
import shutil
import subprocess
import sys


def parse_unit(text: str) -> dict:
    section, exec_start, cwd, user = "", None, None, None
    env = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        m = re.match(r"^\[(.+)\]$", line)
        if m:
            section = m.group(1)
            continue
        if section != "Service" or "=" not in line:
            continue
        key, val = (x.strip() for x in line.split("=", 1))
        if key == "ExecStart":
            exec_start = val or None
        elif key == "WorkingDirectory":
            cwd = val
        elif key == "User":
            user = val
        elif key == "Environment":
            try:
                for tok in shlex.split(val):
                    if "=" in tok:
                        k, v = tok.split("=", 1)
                        env[k] = v
            except ValueError:
                pass
    return {"exec_start": exec_start, "cwd": cwd, "user": user, "env": env}


def expand(s: str, user: str | None) -> str:
    if "%h" in s:
        try:
            home = pwd.getpwnam(user).pw_dir if user else os.path.expanduser("~")
        except KeyError:
            home = os.path.expanduser("~")
        s = s.replace("%h", home)
    return s.replace("%%", "%")


def build(unit_text: str) -> dict:
    p = parse_unit(unit_text)
    argv = []
    if p["exec_start"]:
        cmd = p["exec_start"].lstrip("@-:+!")
        argv = [expand(a, p["user"]) for a in shlex.split(cmd)]
    if not argv:
        found = shutil.which("nostalgiabox")
        if not found:
            raise SystemExit("Could not work out how to start NostalgiaBox (no ExecStart and no 'nostalgiabox' command).")
        argv = [found]
    cwd = expand(p["cwd"], p["user"]).lstrip("-") if p["cwd"] else None
    return {"argv": argv, "cwd": cwd, "env": p["env"], "user": p["user"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", default="nostalgiabox.service")
    ap.add_argument("--unit-file")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    path = a.unit_file
    if not path:
        try:
            path = subprocess.run(["systemctl", "show", "-p", "FragmentPath", "--value", a.unit],
                                  capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            path = ""
    if not path or not os.path.isfile(path):
        print(f"Couldn't find the {a.unit} service. Run './scripts/install.sh --service' inside the "
              f"NostalgiaBox folder first.", file=sys.stderr)
        return 2
    with open(path) as f:
        info = build(f.read())
    info["source"] = path
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(info, f, indent=1)
    print(f"NostalgiaBox starts with: {' '.join(info['argv'])}  (user: {info['user'] or 'root'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
