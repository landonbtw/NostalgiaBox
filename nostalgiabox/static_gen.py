"""Generate the nostalgic filler clips (analog static, SMPTE colour bars).

These short clips are what make channel changes feel like a real 2000s TV:

* ``static.mp4`` - a second of silent grey "snow", shown briefly whenever the
  channel changes.
* ``colorbars.mp4`` - SMPTE colour bars with a 1 kHz tone, shown at start-up and
  as a friendly "no signal" / empty-channel screen.

They are produced once (by ``scripts/install.sh`` or ``python -m
nostalgiabox.static_gen``) with ffmpeg and cached in the assets directory, so
the Pi never has to synthesise them at runtime.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
from pathlib import Path
from typing import List

log = logging.getLogger(__name__)

# Package-bundled assets live next to this file.
DEFAULT_ASSETS_DIR = Path(__file__).resolve().parent / "assets"

STATIC_FILENAME = "static.mp4"
COLORBARS_FILENAME = "colorbars.mp4"


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _run(cmd: List[str]) -> None:
    log.info("running: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def generate_static(
    out_path: Path,
    *,
    duration: float = 1.0,
    width: int = 1280,
    height: int = 720,
    fps: int = 25,
) -> Path:
    """Render a loopable, silent analog-snow clip to ``out_path``.

    Only ~0.5s is shown per channel change, but we render a full second so the
    brief loop never shows a visible seam. The clip has no audio track, so
    channel changes are silent (no static hiss).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"nullsrc=s={width}x{height}:r={fps}:d={duration}",
        "-vf", "geq=lum='random(1)*255':cb=128:cr=128,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        # Silent: the snow is picture-only, no audio hiss.
        "-an",
        str(out_path),
    ]
    _run(cmd)
    return out_path


def generate_color_bars(
    out_path: Path,
    *,
    duration: float = 6.0,
    width: int = 1280,
    height: int = 720,
    fps: int = 25,
) -> Path:
    """Render SMPTE colour bars with a 1 kHz tone to ``out_path``."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"smptehdbars=s={width}x{height}:r={fps}:d={duration}",
        "-f", "lavfi",
        "-i", f"sine=frequency=1000:duration={duration}:sample_rate=48000",
        "-af", "volume=0.1",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k",
        "-shortest",
        str(out_path),
    ]
    _run(cmd)
    return out_path


def generate_all(assets_dir: Path, *, force: bool = False) -> List[Path]:
    """Generate any missing assets in ``assets_dir``; return what exists."""
    if not ffmpeg_available():
        raise RuntimeError(
            "ffmpeg is required to generate assets. Install it with "
            "`sudo apt install ffmpeg`."
        )
    assets_dir.mkdir(parents=True, exist_ok=True)
    results: List[Path] = []

    static_path = assets_dir / STATIC_FILENAME
    if force or not static_path.exists():
        results.append(generate_static(static_path))
    else:
        results.append(static_path)

    bars_path = assets_dir / COLORBARS_FILENAME
    if force or not bars_path.exists():
        results.append(generate_color_bars(bars_path))
    else:
        results.append(bars_path)

    return results


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate NostalgiaBox filler assets.")
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=DEFAULT_ASSETS_DIR,
        help=f"where to write the assets (default: {DEFAULT_ASSETS_DIR})",
    )
    parser.add_argument("--force", action="store_true", help="regenerate even if present")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        produced = generate_all(args.assets_dir, force=args.force)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        log.error("asset generation failed: %s", exc)
        return 1
    for path in produced:
        log.info("asset ready: %s", path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
