"""Command-line entry point: ``nostalgiabox`` / ``python -m nostalgiabox``."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from pathlib import Path
from typing import List, Optional

from . import __version__
from .config import ConfigError, load_config
from .doctor import no_shows_advice, report_config_error, run_check, wait_for_shows

log = logging.getLogger("nostalgiabox")

_INSTALL_HINT = "bash ~/NostalgiaBox/scripts/install.sh"


def installed_repo_dir() -> Optional[Path]:
    """Directory of an editable install (the git checkout), if we can see it.

    ``pip install -e`` keeps this file inside the checkout, so the config next
    to ``pyproject.toml`` is the one the installer created. A copy installed
    into site-packages will not have that layout; ``/etc/nostalgiabox`` is the
    fallback the installer also links.
    """
    root = Path(__file__).resolve().parent.parent
    if (root / "pyproject.toml").is_file() and (root / "scripts" / "install.sh").is_file():
        return root
    return None


def config_candidates(
    cwd: Path,
    home: Path,
    repo_dir: Optional[Path],
) -> List[Path]:
    """Config files to try, first hit wins.

    A ``config.yaml`` in the current directory wins so a local file is used on
    purpose. After that we look next to the installed checkout, then in the
    usual per-user and system locations. That is what makes ``nostalgiabox
    --check`` work no matter which folder the shell is in.
    """
    paths = [cwd / "config.yaml"]
    if repo_dir is not None:
        paths.append(repo_dir / "config.yaml")
    paths.append(home / ".config" / "nostalgiabox" / "config.yaml")
    paths.append(Path("/etc/nostalgiabox/config.yaml"))
    unique: List[Path] = []
    seen = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _find_config(
    explicit: Optional[str],
    *,
    cwd: Optional[Path] = None,
    home: Optional[Path] = None,
    repo_dir: Optional[Path] = None,
) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    cwd = Path.cwd() if cwd is None else cwd
    home = Path.home() if home is None else home
    if repo_dir is None:
        repo_dir = installed_repo_dir()
    candidates = config_candidates(cwd, home, repo_dir)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    looked = "\n".join(f"  - {path}" for path in candidates)
    raise ConfigError(
        "No config file found. Looked for config.yaml in:\n"
        f"{looked}\n"
        "The installer creates ~/NostalgiaBox/config.yaml. From any folder, run:\n"
        f"  {_INSTALL_HINT}"
    )


def _list_audio_devices() -> int:
    """Print mpv's available audio output devices, one 'name  -  description' per line."""
    try:
        import mpv  # type: ignore
    except ImportError:
        print("python-mpv/libmpv not installed; on the Pi try: mpv --audio-device=help")
        return 1
    try:
        player = mpv.MPV(vo="null", idle=True)
        devices = player.audio_device_list or []
        print("Available audio devices (use the 'name' in config.yaml -> audio_device):\n")
        for dev in devices:
            name = dev.get("name", "?")
            desc = dev.get("description", "")
            print(f"  {name}\n      {desc}")
        print("\nFor a TV, pick the HDMI one, e.g. audio_device: \"alsa/hdmi:CARD=vc4hdmi0,DEV=0\"")
        player.terminate()
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"could not list audio devices via libmpv ({exc}).")
        print("Try on the Pi instead: mpv --audio-device=help")
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="nostalgiabox",
        description="A retro TV media player for a Raspberry Pi nostalgia box.",
    )
    parser.add_argument("-c", "--config", help="path to the YAML config file")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run without real hardware (mock player + keyboard/stdin control)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate the config, list channels/episodes, and exit",
    )
    parser.add_argument(
        "--generate-assets",
        action="store_true",
        help="generate the static/colour-bars filler clips and exit",
    )
    parser.add_argument(
        "--list-audio",
        action="store_true",
        help="list available audio output devices (for the 'audio_device' setting) and exit",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="logging verbosity (default: INFO)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    # The check report is the whole output. An INFO line about loading the
    # config would sit on top of it and look like a second error.
    log_level = args.log_level
    if args.check and log_level == "INFO":
        log_level = "ERROR"
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.generate_assets:
        from .static_gen import DEFAULT_ASSETS_DIR, main as gen_main

        return gen_main(["--assets-dir", str(DEFAULT_ASSETS_DIR)])

    if args.list_audio:
        return _list_audio_devices()

    try:
        config_path = _find_config(args.config)
        log.info("loading config: %s", config_path)
        config = load_config(config_path)
    except ConfigError as exc:
        if args.check:
            return report_config_error(exc)
        log.error("%s", exc)
        return 2

    if args.check:
        return _cmd_check(config, config_path)

    if not config.channels:
        if args.dry_run:
            print(no_shows_advice(config))
            return 1
        print("NostalgiaBox is on, and it is waiting for shows.")
        try:
            signal.signal(signal.SIGTERM, _stop_waiting)
            config = wait_for_shows(
                lambda: load_config(config_path),
                time.sleep,
                _announce_waiting,
            )
        except (KeyboardInterrupt, SystemExit):
            print("Stopped.")
            return 0
        print(f"Found {len(config.channels)} channel(s). Starting the TV.")

    from .app import run_from_config

    try:
        run_from_config(config, dry_run=args.dry_run)
    except RuntimeError as exc:
        log.error("%s", exc)
        return 1
    return 0


def _cmd_check(config, config_path: Path) -> int:
    """Validate key overrides, then print the full setup report."""
    from .input.keymap import parse_key_overrides

    try:
        parse_key_overrides(config.input_options.get("key_overrides"))
    except ValueError as exc:
        print("NostalgiaBox check")
        print("==================")
        print()
        print("Remote keys")
        print(f"  FIX  {exc}")
        print()
        print("Open config.yaml and fix key_overrides, then run: nostalgiabox --check")
        return 2
    return run_check(config, config_path)


def _announce_waiting(config) -> None:
    print(no_shows_advice(config))
    print("Waiting for shows. This starts on its own once a show folder appears.")
    print("From another SSH window, run: nostalgiabox --check")
    print()


def _stop_waiting(signum, _frame) -> None:
    raise SystemExit(0)


if __name__ == "__main__":
    sys.exit(main())
