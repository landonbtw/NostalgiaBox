#!/usr/bin/env python3
"""Draws the two full-screen messages the TV can show instead of channels:

  * the "NostalgiaBox is ready" screen (address + username to log in with)
  * the "off the air" static screen (daily screen time used up)

Each becomes a small video clip that NostalgiaBox plays as a one-channel
"station", so it reaches the TV through exactly the same video/HDMI path as
your shows (green banner and CRT curve included).
"""
from __future__ import annotations

import glob
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

W, H = 960, 720  # 4:3, like a tube TV

FONT_CANDIDATES = [
    "/usr/share/fonts/**/VT323*.ttf",
    os.path.expanduser("~/.fonts/**/VT323*.ttf"),
    os.path.expanduser("~/.local/share/fonts/**/VT323*.ttf"),
    os.path.expanduser("~/NostalgiaBox/**/VT323*.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def find_font_path() -> str | None:
    for pattern in FONT_CANDIDATES:
        hits = sorted(glob.glob(pattern, recursive=True))
        if hits:
            return hits[0]
    return None


def font(size: int):
    path = find_font_path()
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size)  # Pillow 10.1+
    except TypeError:
        return ImageFont.load_default()


def _hex(color: str, factor: float = 1.0):
    c = color.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    return (int(r * factor), int(g * factor), int(b * factor))


def _centered(d, y, text, fnt, fill):
    box = d.textbbox((0, 0), text, font=fnt)
    d.text(((W - (box[2] - box[0])) / 2 - box[0], y), text, font=fnt, fill=fill)
    return box[3] - box[1]


def render_ready_png(path: str, info: dict, color: str = "#4DFF5A") -> None:
    """info: ip, hostname, port, username, password (None once changed), configured, no_shows."""
    img = Image.new("RGB", (W, H), (4, 14, 6))
    d = ImageDraw.Draw(img)
    for y in range(0, H, 4):  # faint scanlines
        d.line([(0, y), (W, y)], fill=(6, 20, 9))
    bright, dim = _hex(color), _hex(color, 0.6)

    big, mid, small = font(86), font(46), font(36)
    y = 48
    _centered(d, y, "NOSTALGIABOX", big, bright)
    y += 100
    if info.get("no_shows"):
        headline = "NO SHOWS FOUND YET"
    elif info.get("configured"):
        headline = "BOX IS READY"
    else:
        headline = "BOX IS READY!"
    _centered(d, y, headline, mid, bright)
    y += 78

    ip, port = info.get("ip"), info.get("port", 8080)
    if ip:
        _centered(d, y, "On your phone or computer, open a", small, dim)
        y += 46
        _centered(d, y, "web browser and go to:", small, dim)
        y += 76
        _centered(d, y, f"http://{ip}:{port}", mid, bright)
        y += 62
        _centered(d, y, f"or http://{info.get('hostname', 'nostalgiabox')}.local:{port}", small, dim)
        y += 78
        _centered(d, y, f"Username:  {info.get('username', 'admin')}", mid, bright)
        y += 56
        if info.get("password"):
            _centered(d, y, f"Password:  {info['password']}", mid, bright)
            y += 66
            _centered(d, y, "Log in, then CHANGE THE PASSWORD.", small, dim)
        else:
            _centered(d, y, "Password:  the one you chose", small, dim)
    else:
        _centered(d, y + 40, "Connecting to the network...", mid, bright)
        _centered(d, y + 120, "Check the Wi-Fi name and password", small, dim)
        _centered(d, y + 166, "or plug in a network cable.", small, dim)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)


def render_offair_text_png(path: str, color: str = "#4DFF5A") -> None:
    """Transparent text card that gets laid over the static."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    box_w, box_h = 700, 190
    x0, y0 = (W - box_w) // 2, (H - box_h) // 2
    d.rectangle([x0, y0, x0 + box_w, y0 + box_h], fill=(0, 0, 0, 215))
    bright = _hex(color)
    _centered(d, y0 + 22, "OFF THE AIR", font(78), bright)
    _centered(d, y0 + 118, "See you tomorrow!", font(44), (235, 235, 235))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)


def _ffmpeg(args: list[str], timeout: int = 600) -> None:
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"] + args,
                   check=True, timeout=timeout, capture_output=True)


def make_still_clip(png: str, mp4: str, seconds: int = 600, fps: int = 2) -> None:
    tmp = mp4 + ".new.mp4"
    _ffmpeg(["-loop", "1", "-framerate", str(fps), "-i", png,
             "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
             "-t", str(seconds), "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
             "-pix_fmt", "yuv420p", "-r", str(fps), "-c:a", "aac", "-shortest", tmp])
    os.replace(tmp, mp4)


def make_offair_clip(mp4: str, color: str = "#4DFF5A", seconds: int = 20) -> None:
    png = os.path.join(os.path.dirname(mp4), "offair-text.png")
    render_offair_text_png(png, color)
    tmp = mp4 + ".new.mp4"
    # Snow is made small (240x180) and scaled up: it looks like chunky analog static and,
    # unlike full-size noise, stays a small, light file the Pi can decode easily.
    _ffmpeg(["-f", "lavfi", "-i", f"color=c=0x707070:s={W // 4}x{H // 4}:r=15",
             "-i", png,
             "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
             "-filter_complex",
             f"[0:v]format=gray,noise=alls=80:allf=t+u,scale={W}:{H}:flags=neighbor[n];"
             "[n][1:v]overlay=0:0,format=yuv420p[v]",
             "-map", "[v]", "-map", "2:a", "-t", str(seconds), "-c:v", "libx264", "-preset", "veryfast",
             "-b:v", "1500k", "-maxrate", "2000k", "-bufsize", "4000k",
             "-c:a", "aac", "-shortest", tmp])
    os.replace(tmp, mp4)
