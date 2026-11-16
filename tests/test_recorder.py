import shutil
import subprocess

import pytest

from selection_pressure import cli
from selection_pressure.recorder import Recorder, RecorderError

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def test_rejects_unknown_formats(tmp_path):
    with pytest.raises(RecorderError, match="use .mp4 or .gif"):
        Recorder(tmp_path / "out.avi", (64, 64), 30)


def test_missing_ffmpeg_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(RecorderError, match="ffmpeg was not found"):
        Recorder(tmp_path / "out.mp4", (64, 64), 30)


@needs_ffmpeg
@pytest.mark.parametrize("suffix", [".mp4", ".gif"])
def test_cli_records_a_short_clip(tmp_path, suffix):
    out = tmp_path / f"clip{suffix}"
    args = ["--size", "320x240", "--stars", "40"]
    assert cli.main([*args, "--record", str(out), "--duration", "1"]) == 0
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-show_entries",
            "stream=nb_read_frames",
            "-of",
            "csv=p=0",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert int(probe.stdout.strip()) >= 15
