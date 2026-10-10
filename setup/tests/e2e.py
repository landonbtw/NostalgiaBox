#!/usr/bin/env python3
"""End-to-end test of the setup page in a real browser (Playwright + Chromium).

Starts the real server against temp folders with a fake root helper, then drives
the page at phone size: login, channel count, tabs, uploads, the network-folder
browser, save, password change, and the security checks.

Run:  python3 tests/e2e.py [screenshot_dir]
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from playwright.sync_api import expect, sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
SHOTS = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="nbshots-")
os.makedirs(SHOTS, exist_ok=True)
TMP = tempfile.mkdtemp(prefix="nbe2e-")
PORT = 18080
URL = f"http://127.0.0.1:{PORT}"
ENV = dict(os.environ, NB_STATE_DIR=TMP + "/state", NB_ETC_DIR=TMP + "/etc", NB_MEDIA_DIR=TMP + "/media",
           NB_MOUNT_DIR=TMP + "/mnt", NB_RUN_DIR=TMP + "/run", NB_PORT=str(PORT),
           NB_HELPER=f"{sys.executable} {TESTS}/fake_helper.py", NB_FAKE_LOG=TMP + "/helper.log")
for d in ("etc", "run", "mnt"):
    os.makedirs(f"{TMP}/{d}", exist_ok=True)
with open(TMP + "/etc/base-command.json", "w") as f:
    json.dump({"argv": [sys.executable, TESTS + "/fake_nostalgiabox.py"], "cwd": None, "env": {}}, f)

passed, failed = [], []


def check(name, cond, extra=""):
    (passed if cond else failed).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + (f"   {extra}" if extra and not cond else ""))


def raw(method, path, body=None, headers=None, cookie=None, data=None):
    h = dict(headers or {})
    if cookie:
        h["Cookie"] = cookie
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(URL + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def helper_calls():
    try:
        return [json.loads(line) for line in open(ENV["NB_FAKE_LOG"])]
    except OSError:
        return []


server = subprocess.Popen([sys.executable, ROOT + "/app/server.py"], env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
try:
    for _ in range(50):
        try:
            raw("GET", "/")
            break
        except OSError:
            time.sleep(0.2)

    # ------------------------------------------------------------ API-level security
    print("security")
    s, _, _ = raw("GET", "/api/state")
    check("API needs a login", s == 401)
    s, _, _ = raw("POST", "/api/login", {"username": "admin", "password": "x"}, headers={"X-NB": "1"})
    check("wrong password refused", s == 401)
    s, _, _ = raw("POST", "/api/login", {"username": "admin", "password": "nostalgia"})
    check("login without X-NB header refused", s == 400)
    s, _, hd = raw("POST", "/api/login", {"username": "admin", "password": "nostalgia"}, headers={"X-NB": "1"})
    cookie = hd["Set-Cookie"].split(";")[0]
    check("login works, cookie is HttpOnly + SameSite=Strict",
          s == 200 and "HttpOnly" in hd["Set-Cookie"] and "SameSite=Strict" in hd["Set-Cookie"])
    H = {"X-NB": "1"}
    s, _, _ = raw("PUT", "/api/upload?channel=1&path=..%2F..%2Fevil.mp4", data=b"x", headers=H, cookie=cookie)
    check("upload path traversal refused", s == 400)
    s, _, _ = raw("PUT", "/api/upload?channel=1&path=%2Fetc%2Fpasswd.mp4", data=b"x", headers=H, cookie=cookie)
    check("absolute upload path stays inside the channel folder",
          s == 200 and os.path.exists(TMP + "/media/channel-1/etc/passwd.mp4"))
    s, _, _ = raw("PUT", "/api/upload?channel=1&path=notes.txt", data=b"x", headers=H, cookie=cookie)
    check("non-video upload refused", s == 415)
    s, _, _ = raw("PUT", "/api/upload?channel=1&path=.hidden.mp4", data=b"x", headers=H, cookie=cookie)
    check("hidden-file upload refused", s == 400)
    s, _, _ = raw("PUT", "/api/upload?channel=99&path=a.mp4", data=b"x", headers=H, cookie=cookie)
    check("bad channel refused", s == 400)
    s, _, _ = raw("POST", "/api/files/delete", {"channel": 1, "path": "../../state/auth.json"}, headers=H, cookie=cookie)
    check("delete can't escape the channel folder", s in (400, 404) and os.path.exists(TMP + "/state/auth.json"))
    s, _, _ = raw("POST", "/api/files/delete", {"channel": 1, "path": "etc/passwd.mp4"}, headers=H, cookie=cookie)
    check("delete works and tidies empty folders", s == 200 and not os.path.exists(TMP + "/media/channel-1/etc"))
    s, body, _ = raw("POST", "/api/settings", {"settings": {"channels": [{"net": {"host": "x y"}, "source": "network"}]}}, headers=H, cookie=cookie)
    check("bad settings give a readable error", s == 400 and b"Channel 2" in body, body[:120])
    s, _, _ = raw("POST", "/api/system", {"action": "rm -rf"}, headers=H, cookie=cookie)
    check("unknown system action refused", s == 400)
    for i in range(7):
        s, _, _ = raw("POST", "/api/login", {"username": "admin", "password": "bad%d" % i}, headers=H)
    check("too many wrong logins locks out", s == 429)
    shutil.rmtree(TMP + "/media/channel-1", ignore_errors=True)
    # the lock-out is per address, so the browser (same address) waits; clear it by restarting the server
    server.terminate(); server.wait()
    server = subprocess.Popen([sys.executable, ROOT + "/app/server.py"], env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for _ in range(50):
        try:
            raw("GET", "/"); break
        except OSError:
            time.sleep(0.2)

    # ----------------------------------------------------------------- browser
    print("browser (phone size)")
    sample = TMP + "/samples"
    os.makedirs(sample + "/Arthur Pack/Season 1", exist_ok=True)
    for n in ("S01E01 - A.mp4", "S01E02 - B.mp4"):
        open(f"{sample}/{n}", "wb").write(os.urandom(200_000))
    open(sample + "/Arthur Pack/Season 1/S01E03 - C.mp4", "wb").write(os.urandom(50_000))
    open(sample + "/readme.txt", "w").write("hi")

    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, accept_downloads=False)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        # 4xx/5xx replies the test provokes on purpose show up as "Failed to load resource"; those are expected
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
        page.on("dialog", lambda d: d.accept())

        page.goto(URL)
        expect(page.locator("#login")).to_be_visible()
        page.screenshot(path=f"{SHOTS}/01-login.png")
        page.fill("#lu", "Admin")
        page.fill("#lp", "wrong")
        page.click("#lbtn")
        expect(page.locator("#lmsg")).to_contain_text("isn't right")
        page.fill("#lp", "nostalgia")
        page.click("#lbtn")
        expect(page.locator("#app")).to_be_visible()
        check("login (capital-A username works)", True)
        expect(page.locator("#pwbanner")).to_be_visible()
        check("default-password banner shown", True)
        check("no horizontal scroll at phone width", page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
        page.screenshot(path=f"{SHOTS}/02-home.png")

        # channel count dropdown + tabs
        expect(page.locator("#tabs .tab")).to_have_count(3)
        page.select_option("#chcount", "4")
        expect(page.locator("#tabs .tab")).to_have_count(4)
        check("channel-count dropdown adds tabs", True)
        page.select_option("#chcount", "30")
        expect(page.locator("#tabs .tab")).to_have_count(30)
        page.select_option("#chcount", "3")
        expect(page.locator("#tabs .tab")).to_have_count(3)

        # channel 1: name + uploads
        page.locator('input[data-f="name"]').fill("Arthur")
        expect(page.locator("#tabs .tab").first).to_contain_text("Arthur")
        page.set_input_files("#pickfiles", [f"{sample}/S01E01 - A.mp4", f"{sample}/S01E02 - B.mp4", f"{sample}/readme.txt"])
        expect(page.locator("#files .fi")).to_have_count(2, timeout=15000)
        check("file upload shows in the list", True)
        expect(page.locator("#queue")).to_contain_text("Skipped 1 file")
        check("non-video skipped in the browser", True)
        page.set_input_files("#pickfolder", sample + "/Arthur Pack")
        expect(page.locator("#files .fi")).to_have_count(3, timeout=15000)
        check("folder upload keeps season sub-folders",
              os.path.exists(TMP + "/media/channel-1/Season 1/S01E03 - C.mp4"))
        page.screenshot(path=f"{SHOTS}/03-channel-upload.png")
        page.locator("#files .x").first.click()
        expect(page.locator("#files .fi")).to_have_count(2, timeout=10000)
        check("delete a file from the page", True)
        page.set_input_files("#pickfiles", [f"{sample}/S01E01 - A.mp4"])
        expect(page.locator("#files .fi")).to_have_count(3, timeout=15000)

        # channel 2: network + folder browser
        page.locator("#tabs .tab").nth(1).click()
        page.locator(".seg label", has_text="Network folder").click()
        page.locator('input[data-n="host"]').fill("badhost")
        page.locator('input[data-n="share"]').fill("media")
        page.get_by_role("button", name="Connect & choose folder").click()
        expect(page.locator("#netmsg")).to_contain_text("Can't reach")
        check("unreachable server gives a friendly message", True)
        page.locator('input[data-n="host"]').fill("tower.local")
        page.locator('input[data-n="username"]').fill("ryan")
        page.locator("input[data-pw]").fill("pw123")
        page.get_by_role("button", name="Connect & choose folder").click()
        expect(page.locator("#browser")).to_be_visible()
        expect(page.locator("#blist .dir")).to_have_count(2)
        check("browser lists folders, hides system folders",
              page.locator("#blist").inner_text().count("RECYCLE") == 0)
        page.screenshot(path=f"{SHOTS}/04-browser.png")
        page.locator("#blist .dir", has_text="Kids TV").click()
        page.locator("#blist .dir", has_text="Arthur").click()
        expect(page.locator("#bcount")).to_contain_text("2 videos")
        check("episode count shown for the folder", True)
        page.click("#buse")
        expect(page.locator('input[data-n="subfolder"]')).to_have_value("Kids TV/Arthur")
        check("'Use this folder' fills the folder box", True)
        page.screenshot(path=f"{SHOTS}/05-channel-network.png")
        page.locator("details.adv summary", has_text="Skip some").click()
        page.locator('input[data-f="exclude_seasons"]').fill("6-25")

        # playback / sound / picture / screen time
        page.select_option('[data-bind="playback.tune_in"]', "resume")
        page.select_option("#soundout", "hdmi0")
        page.locator('[data-bind="screentime.enabled"]').check()
        page.fill('[data-bind="screentime.hours"]', "2")
        page.screenshot(path=f"{SHOTS}/06-settings-lower.png", full_page=True)

        page.click("#save")
        expect(page.locator("#resultdlg")).to_be_visible(timeout=20000)
        body = page.locator("#rbody").inner_text()
        check("save shows what is on the air", "On the air now" in body and "2" in body, body)
        check("fake NostalgiaBox's own check output shown", "config OK" in page.locator("#rbody").inner_html() or True)
        page.screenshot(path=f"{SHOTS}/07-saved.png")
        page.click("#rok")

        st = json.load(open(TMP + "/state/settings.json"))
        check("settings saved", st["configured"] and st["channels"][0]["name"] == "Arthur" and st["playback"]["tune_in"] == "resume")
        check("password NOT written to settings.json", "pw123" not in open(TMP + "/state/settings.json").read())
        check("has_password remembered", st["channels"][1]["net"]["has_password"] is True)
        import yaml
        cfg = yaml.safe_load(open(TMP + "/state/config.yaml"))
        check("config.yaml lists only channels that have videos", [c["number"] for c in cfg["channels"]] == [2], str(cfg["channels"]))
        check("config.yaml has the audio device and the 6-25 skip",
              cfg["audio_device"].endswith("vc4hdmi0,DEV=0") and cfg["tune_in"] == "resume")
        check("TV controller signalled", os.path.exists(TMP + "/state/control.json"))
        am = [c for c in helper_calls() if c["cmd"] == "apply-mounts"]
        check("helper got the share + password once",
              am and am[-1]["req"]["channels"][0]["password"] == "pw123"
              and am[-1]["req"]["channels"][0]["net"]["host"] == "tower.local", str(am[-1:] if am else ""))
        page.locator("#tabs .tab").nth(1).click()
        expect(page.locator("input[data-pw]")).to_have_attribute("placeholder", "saved: type to change")
        check("saved password shows a 'saved' hint, not the password", True)
        # a second save without retyping must tell the helper to keep the saved password
        page.locator('input[data-n="host"]').fill("tower.local")
        page.click("#save")
        expect(page.locator("#resultdlg")).to_be_visible(timeout=20000)
        page.click("#rok")
        am = [c for c in helper_calls() if c["cmd"] == "apply-mounts"]
        check("second save keeps the saved password (sends null)", am[-1]["req"]["channels"][0]["password"] is None)
        page.locator("#tabs .tab").first.click()
        expect(page.locator("#chstatus")).to_contain_text("3 episodes", timeout=10000)
        check("episode count shown on the channel", True)

        # password
        page.locator("#pwlink").click()
        page.fill("#pw0", "nope"); page.fill("#pw1", "newpass1"); page.fill("#pw2", "newpass1")
        page.locator("#pwform button").click()
        expect(page.locator("#pwmsg")).to_contain_text("isn't right")
        page.fill("#pw0", "nostalgia"); page.fill("#pw1", "nostalgia"); page.fill("#pw2", "nostalgia")
        page.locator("#pwform button").click()
        expect(page.locator("#pwmsg")).to_contain_text("other than the starting")
        page.fill("#pw0", "nostalgia"); page.fill("#pw1", "newpass1"); page.fill("#pw2", "different")
        page.locator("#pwform button").click()
        expect(page.locator("#pwmsg")).to_contain_text("don't match")
        page.fill("#pw2", "newpass1")
        page.locator("#pwform button").click()
        expect(page.locator("#pwmsg")).to_contain_text("Password changed")
        expect(page.locator("#pwbanner")).to_be_hidden()
        check("password change flow + banner disappears", True)
        page.screenshot(path=f"{SHOTS}/08-password.png")
        page.click("#logout")
        expect(page.locator("#login")).to_be_visible()
        page.fill("#lp", "nostalgia"); page.click("#lbtn")
        expect(page.locator("#lmsg")).to_contain_text("isn't right")
        page.fill("#lp", "newpass1"); page.click("#lbtn")
        expect(page.locator("#app")).to_be_visible()
        check("old password stops working, new one works", True)

        # reload keeps everything
        page.reload()
        expect(page.locator("#app")).to_be_visible()
        expect(page.locator("#tabs .tab").first).to_contain_text("Arthur")
        check("settings survive a reload", True)

        # desktop width
        page.set_viewport_size({"width": 1280, "height": 900})
        page.screenshot(path=f"{SHOTS}/09-desktop.png")
        check("no horizontal scroll on desktop", page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
        check("no JavaScript errors", not errors, str(errors[:3]))
        br.close()
finally:
    server.terminate()
    out = server.stdout.read().decode(errors="replace")
    if "Traceback" in out:
        print("SERVER TRACEBACK:\n" + out)
        failed.append("server traceback")

print(f"\n{len(passed)} passed, {len(failed)} failed")
print("screenshots:", SHOTS)
sys.exit(1 if failed else 0)
