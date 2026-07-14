"""Shared test helpers."""

from __future__ import annotations

from pathlib import Path
from typing import List


def make_show(root: Path, name: str, episodes: int, ext: str = ".mp4") -> Path:
    """Create a show folder with ``episodes`` dummy episode files."""
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(1, episodes + 1):
        (folder / f"{name}_ep{i:02d}{ext}").write_bytes(b"\x00")
    return folder


class FakeClock:
    """A manually-advanced monotonic clock for deterministic timing tests."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def list_names(paths: List[Path]) -> List[str]:
    return [p.name for p in paths]
