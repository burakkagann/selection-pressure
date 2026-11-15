"""Offline video capture through ffmpeg.

Frames are rendered as fast as the machine allows and piped to ffmpeg, so the
output plays at a steady frame rate even when live rendering would drop
frames.  The output format follows the file extension: ``.mp4`` (H.264) or
``.gif`` (palette-optimised, at most 720 px wide, good for READMEs).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pygame

# GIFs are for READMEs and chat: keep them small.
GIF_MAX_WIDTH = 720
GIF_MAX_FPS = 20


class RecorderError(RuntimeError):
    """ffmpeg is missing or failed."""


def _ffmpeg_command(path: Path, size: tuple[int, int], fps: int) -> list[str]:
    w, h = size
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{w}x{h}",
        "-r",
        str(fps),
        "-i",
        "-",
    ]
    if path.suffix.lower() == ".gif":
        gif_fps = min(fps, GIF_MAX_FPS)
        cmd += [
            "-vf",
            f"fps={gif_fps},scale='min({GIF_MAX_WIDTH},iw)':-2:flags=lanczos,split[a][b];"
            "[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer",
        ]
    else:
        cmd += [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "18",
            "-preset",
            "slow",
            "-movflags",
            "+faststart",
        ]
    return cmd + [str(path)]


class Recorder:
    """Pipe pygame surfaces into an ffmpeg process."""

    SUPPORTED = (".mp4", ".gif")

    def __init__(self, path: Path, size: tuple[int, int], fps: int):
        if path.suffix.lower() not in self.SUPPORTED:
            raise RecorderError(f"unsupported output {path.name!r}; use .mp4 or .gif")
        if shutil.which("ffmpeg") is None:
            raise RecorderError("ffmpeg was not found on PATH; install it to use --record")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.size = size
        self.frames = 0
        self._proc = subprocess.Popen(
            _ffmpeg_command(path, size, fps), stdin=subprocess.PIPE, stderr=subprocess.PIPE
        )

    def write(self, surface: pygame.Surface) -> None:
        if surface.get_size() != self.size:
            raise RecorderError("the window size changed while recording")
        try:
            self._proc.stdin.write(pygame.image.tobytes(surface, "RGB"))
        except BrokenPipeError:
            raise RecorderError(self._stderr() or "ffmpeg stopped unexpectedly") from None
        self.frames += 1

    def close(self) -> None:
        if self._proc.stdin and not self._proc.stdin.closed:
            self._proc.stdin.close()
        if self._proc.wait() != 0:
            raise RecorderError(self._stderr() or f"ffmpeg exited with {self._proc.returncode}")

    def _stderr(self) -> str:
        return (
            self._proc.stderr.read().decode(errors="replace").strip() if self._proc.stderr else ""
        )
