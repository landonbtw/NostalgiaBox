#!/usr/bin/env python3
"""Stand-in for the nostalgiabox program: --check lists channels; otherwise it 'plays'."""
import os, sys, time
import yaml

args = sys.argv[1:]
cfg_path = args[args.index("--config") + 1]
cfg = yaml.safe_load(open(cfg_path))
if "--check" in args:
    for c in cfg["channels"]:
        print(f"CH {c['number']:>2}  {c['name']}  ok")
    print("config OK")
    sys.exit(0)
mark = os.environ.get("NB_FAKE_MARK")
if mark:
    with open(mark, "a") as f:
        f.write(cfg_path + "\n")
while True:
    time.sleep(1)
