"""Frozen-picture watchdog: detection, the problem-file log, and recovery."""

import json
from pathlib import Path

from nostalgiabox.stall import (
    PlaybackSample,
    ProblemLog,
    StallWatchdog,
    format_problem_line,
    format_timestamp,
    picture_token,
)


def test_timestamp_formats_minutes_and_hours():
    assert format_timestamp(0) == "0:00"
    assert format_timestamp(125) == "2:05"
    assert format_timestamp(3661) == "1:01:01"


def test_picture_token_reads_a_timecode_and_ignores_other_shapes():
    assert picture_token({"smpte-timecode": "01:02:03:04"}) == "01:02:03:04"
    assert picture_token({"gop_timecode": " 00:00:01:00 "}) == "00:00:01:00"
    assert picture_token({"picture-type": "P"}) is None
    assert picture_token("nope") is None


def test_problem_line_includes_path_and_timestamp():
    line = format_problem_line(
        Path("/media/nostalgiabox/Dragon Tales/S01E04.mp4"),
        754.2,
        "playback position stopped advancing (stuck at this timestamp); seeking ahead 10s",
        "channel 3 Dragon Tales",
    )
    assert "problem file: /media/nostalgiabox/Dragon Tales/S01E04.mp4" in line
    assert "at 12:34 (754.2s)" in line
    assert "channel 3 Dragon Tales" in line
    assert line.startswith("20")  # UTC timestamp


def _watch(**kw) -> StallWatchdog:
    return StallWatchdog(timeout=5, grace=0, **kw)


def test_frozen_position_seeks_once_then_skips(tmp_path):
    path = tmp_path / "ep.mp4"
    watch = _watch()
    watch.arm(path, now=0)
    # One reading establishes the clock. It is not progress.
    assert watch.observe(PlaybackSample(position=125.0), now=0) is None
    stall = watch.observe(PlaybackSample(position=125.0), now=5)
    assert stall is not None
    assert stall.action == "seek"
    assert stall.kind == "timestamp"
    assert stall.position == 125.0
    assert "stuck at this timestamp" in stall.detail
    watch.note_seek(now=5)
    # The seek landed and the picture froze there too.
    assert watch.observe(PlaybackSample(position=135.0), now=5) is None
    again = watch.observe(PlaybackSample(position=135.0), now=10)
    assert again is not None
    assert again.action == "skip"
    assert again.position == 135.0


def test_moving_clock_is_not_a_stall(tmp_path):
    path = tmp_path / "ep.mp4"
    watch = _watch()
    watch.arm(path, now=0)
    position = 10.0
    for t in range(0, 30, 3):
        assert watch.observe(PlaybackSample(position=position), now=float(t)) is None
        position += 3.0


def test_audio_clock_keeps_a_still_video_clock_alive(tmp_path):
    """Sound still moving means the file is not the 'no audio, frozen' case."""
    path = tmp_path / "ep.mp4"
    watch = _watch()
    watch.arm(path, now=0)
    watch.observe(PlaybackSample(position=10.0, audio_position=10.0), now=0)
    assert (
        watch.observe(PlaybackSample(position=10.0, audio_position=14.0), now=6) is None
    )


def test_grace_holds_off_a_freeze_while_the_file_opens(tmp_path):
    path = tmp_path / "ep.mp4"
    watch = StallWatchdog(timeout=5, grace=10)
    watch.arm(path, now=0)
    watch.observe(PlaybackSample(position=1.0), now=0)
    assert watch.observe(PlaybackSample(position=1.0), now=6) is None
    stall = watch.observe(PlaybackSample(position=1.0), now=10)
    assert stall is not None and stall.action == "seek"


def test_ended_file_is_left_to_the_normal_roll(tmp_path):
    path = tmp_path / "ep.mp4"
    watch = _watch()
    watch.arm(path, now=0)
    watch.observe(PlaybackSample(position=1.0), now=0)
    assert watch.observe(PlaybackSample(position=1.0, ended=True), now=30) is None


def test_hung_player_skips_without_a_seek(tmp_path):
    path = tmp_path / "ep.mp4"
    watch = _watch()
    watch.arm(path, now=0)
    stall = watch.observe(PlaybackSample(failed=True), now=5)
    assert stall is not None
    assert stall.action == "skip"
    assert stall.kind == "player"
    assert stall.position is None


def test_paused_with_a_moving_clock_is_not_a_stall(tmp_path):
    """A stale pause flag must not skip a file whose clock is moving."""
    path = tmp_path / "ep.mp4"
    watch = _watch()
    watch.arm(path, now=0)
    watch.observe(PlaybackSample(position=1.0, paused=True), now=0)
    assert watch.observe(PlaybackSample(position=5.0, paused=True), now=6) is None


def test_paused_and_stuck_is_a_player_stall(tmp_path):
    path = tmp_path / "ep.mp4"
    watch = _watch()
    watch.arm(path, now=0)
    watch.observe(PlaybackSample(position=4.0, paused=True), now=0)
    stall = watch.observe(PlaybackSample(position=4.0, paused=True), now=5)
    assert stall is not None
    assert stall.kind == "player"
    assert stall.action == "seek"
    assert stall.position == 4.0


def test_picture_frozen_while_the_clock_moves(tmp_path):
    path = tmp_path / "ep.mp4"
    watch = _watch()
    watch.arm(path, now=0)
    # Timecode changes, so it is a real frame id and not a constant tag.
    watch.observe(PlaybackSample(position=1.0, picture="00:00:01:00"), now=0)
    assert (
        watch.observe(PlaybackSample(position=2.0, picture="00:00:01:01"), now=1) is None
    )
    # Clock runs on. The frame on screen does not.
    assert (
        watch.observe(PlaybackSample(position=10.0, picture="00:00:01:01"), now=3) is None
    )
    stall = watch.observe(PlaybackSample(position=20.0, picture="00:00:01:01"), now=6)
    assert stall is not None
    assert stall.kind == "picture"
    assert stall.action == "seek"
    assert "picture is frozen" in stall.detail
    assert stall.position == 20.0


def test_constant_timecode_does_not_false_stall(tmp_path):
    """A tag that never changes is not evidence of a frozen frame."""
    path = tmp_path / "ep.mp4"
    watch = _watch()
    watch.arm(path, now=0)
    position = 1.0
    for t in range(0, 20, 2):
        sample = PlaybackSample(position=position, picture="SAME")
        assert watch.observe(sample, now=float(t)) is None
        position += 2.0


def test_disarm_and_rearm_reset_the_attempt(tmp_path):
    path = tmp_path / "ep.mp4"
    other = tmp_path / "other.mp4"
    watch = _watch()
    watch.arm(path, now=0)
    watch.observe(PlaybackSample(position=1.0), now=0)
    watch.disarm()
    assert watch.observe(PlaybackSample(position=1.0), now=50) is None
    watch.arm(other, now=50)
    watch.observe(PlaybackSample(position=3.0), now=50)
    stall = watch.observe(PlaybackSample(position=3.0), now=55)
    assert stall is not None
    assert stall.path == other
    assert stall.action == "seek"  # a new file gets the seek, not an immediate skip


def test_problem_log_flags_on_the_second_freeze_and_reloads(tmp_path):
    path = tmp_path / "Dragon Tales" / "S01E04.mp4"
    first = ProblemLog(tmp_path, flag_after=2)
    assert first.note_stall(path, 754.2, "seeking ahead 10s", "channel 3 Dragon Tales") is False
    assert first.is_flagged(path) is False

    again = ProblemLog(tmp_path, flag_after=2)
    assert again.stalls(path) == 1
    assert again.note_stall(path, 764.0, "skipping to the next episode", "channel 3 Dragon Tales")
    assert again.is_flagged(path)

    text = (tmp_path / "problem-files.log").read_text(encoding="utf-8")
    assert str(path) in text
    assert "at 12:34 (754.2s)" in text
    assert "channel 3 Dragon Tales" in text
    saved = json.loads((tmp_path / "problem-files.json").read_text(encoding="utf-8"))
    assert saved["version"] == 1
    assert list(saved["files"].values())[0]["stalls"] == 2


def test_problem_log_ignores_a_broken_file(tmp_path):
    (tmp_path / "problem-files.json").write_text("{", encoding="utf-8")
    log = ProblemLog(tmp_path, flag_after=2)
    assert log.stalls(tmp_path / "ep.mp4") == 0
    assert log.is_flagged(tmp_path / "ep.mp4") is False
