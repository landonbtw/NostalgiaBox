"""Best-effort media duration probing via ffprobe.

Only the optional "broadcast" tune-in mode needs to know how long each episode
runs (so it can pretend the channel has been airing continuously). Probing is
done once at startup and is entirely best-effort: if ffprobe is missing or a
file cannot be read, we fall back to an assumed episode length so the box still
works.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

# A typical kids' TV episode is about 22 minutes; used when we cannot probe.
DEFAULT_EPISODE_SECONDS = 22 * 60.0


def ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


def probe_duration(path: Path, *, timeout: float = 15.0) -> Optional[float]:
    """Return the duration of ``path`` in seconds, or ``None`` on failure."""
    if not ffprobe_available():
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout or "{}")
        duration = data.get("format", {}).get("duration")
        if duration is None:
            return None
        value = float(duration)
        return value if value > 0 else None
    except (subprocess.SubprocessError, ValueError, OSError):
        return None


__all__ = ["probe_duration", "ffprobe_available", "DEFAULT_EPISODE_SECONDS"]
