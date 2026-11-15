"""Command-line interface: ``selection-pressure`` / ``python -m selection_pressure``."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__, app, config
from .recorder import RecorderError


def _window_size(text: str) -> tuple[int, int]:
    try:
        w, h = (int(v) for v in text.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected WIDTHxHEIGHT, got {text!r}") from None
    if w < 320 or h < 240:
        raise argparse.ArgumentTypeError("window must be at least 320x240")
    return w, h


def _display(text: str) -> str:
    if text in ("primary", "auto") or text.isdigit():
        return text
    raise argparse.ArgumentTypeError("use 'primary', 'auto' or a monitor index such as 1")


def _ranged(lo: int, hi: int):
    def parse(text: str) -> int:
        value = int(text)
        if not lo <= value <= hi:
            raise argparse.ArgumentTypeError(f"must be between {lo} and {hi}")
        return value

    return parse


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="selection-pressure",
        description="Boids, black holes and evolution in real time.",
        epilog="Most visual and behavioural tuning lives in config.py.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    view = p.add_argument_group("display")
    view.add_argument(
        "--display",
        type=_display,
        default=os.environ.get("SP_DISPLAY", "primary"),
        help="monitor to use: 'primary' (default), 'auto' (largest "
        "secondary screen, e.g. a projector) or an index",
    )
    view.add_argument(
        "--windowed",
        nargs="?",
        const=True,
        default=False,
        type=_window_size,
        metavar="WxH",
        help="run in a resizable window (default 80%% of the monitor)",
    )
    view.add_argument(
        "--fps",
        type=_ranged(10, 240),
        default=config.TARGET_FPS,
        help="frame-rate cap (default %(default)s)",
    )
    view.add_argument(
        "--no-hud",
        dest="show_hud",
        action="store_false",
        help="hide the status line, clock and visitor hint",
    )
    view.add_argument(
        "--kiosk", action="store_true", help="exhibition mode: minimise the console window on start"
    )

    world = p.add_argument_group("simulation")
    world.add_argument(
        "--seed", type=int, default=config.SEED, help="random seed (default %(default)s)"
    )
    world.add_argument(
        "--stars",
        type=_ranged(app.MIN_STARS, app.MAX_STARS),
        default=config.NUM_BOIDS,
        help="starting stars (default %(default)s)",
    )
    world.add_argument(
        "--black-holes",
        type=_ranged(0, app.MAX_BLACK_HOLES),
        default=config.NUM_BLACK_HOLES,
        help="starting black holes (default %(default)s)",
    )

    rec = p.add_argument_group("recording (needs ffmpeg on PATH)")
    rec.add_argument(
        "--record", type=Path, metavar="FILE", help="render offline to FILE (.mp4 or .gif) and exit"
    )
    rec.add_argument(
        "--duration",
        type=float,
        default=15.0,
        metavar="SECONDS",
        help="length of the recording (default %(default)s)",
    )
    rec.add_argument(
        "--warmup",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="simulate this long before recording starts (default %(default)s)",
    )

    dev = p.add_argument_group("development")
    dev.add_argument(
        "--frames",
        type=_ranged(1, 10**9),
        metavar="N",
        help="quit after N frames (useful for tests and benchmarks)",
    )
    dev.add_argument(
        "--profile", action="store_true", help="print per-stage frame timings every 120 frames"
    )
    dev.add_argument(
        "--screenshot-dir",
        type=Path,
        default=Path("."),
        help="where S saves screenshots (default: current directory)",
    )
    return p


def parse_args(argv: list[str] | None = None) -> app.Options:
    ns = build_parser().parse_args(argv)
    windowed = ns.windowed is not False
    return app.Options(
        display=ns.display,
        windowed=windowed,
        window_size=ns.windowed if isinstance(ns.windowed, tuple) else None,
        seed=ns.seed,
        stars=ns.stars,
        black_holes=ns.black_holes,
        fps=ns.fps,
        frames=ns.frames,
        show_hud=ns.show_hud,
        kiosk=ns.kiosk,
        profile=ns.profile,
        screenshot_dir=ns.screenshot_dir,
        record=ns.record,
        record_seconds=ns.duration,
        warmup_seconds=ns.warmup,
    )


def main(argv: list[str] | None = None) -> int:
    options = parse_args(argv)
    try:
        app.run(options)
    except (ValueError, RecorderError) as exc:  # bad --display, missing ffmpeg...
        print(f"selection-pressure: error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
