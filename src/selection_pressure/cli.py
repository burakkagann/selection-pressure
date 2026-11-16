"""Command-line interface: ``selection-pressure`` / ``python -m selection_pressure``."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__, app, config
from .display import DisplayError
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


# --preset: size, length, warm-up and panel for the usual destinations
# The README GIF is shown about 720 px wide, so its panel is drawn 1.5x larger.
PRESETS = {
    "readme": {
        "size": (1920, 1080),
        "duration": 6.0,
        "warmup": 148.0,  # with the default seed a black hole tears through a flock
        "panel": "strip",
        "panel_scale": 1.5,
    },
    "reddit": {"size": (1080, 1350), "duration": 30.0, "warmup": 25.0, "panel": "off"},
    "reel": {"size": (1080, 1920), "duration": 20.0, "warmup": 25.0, "panel": "off"},
    "wide": {
        "size": (1920, 1080),
        "duration": 30.0,
        "warmup": 120.0,
        "panel": "full",
        "panel_scale": 1.2,
    },
}
RECORD_DEFAULTS = {"duration": 15.0, "warmup": 0.0, "panel": "off", "panel_scale": 1.0}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="selection-pressure",
        description="Boids, black holes and evolution in real time. "
        "Press H in the window for the controls.",
        epilog="Most visual and behavioural tuning lives in config.py.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    view = p.add_argument_group("display")
    mode = view.add_mutually_exclusive_group()
    mode.add_argument(
        "--fullscreen",
        action="store_true",
        help="start borderless fullscreen (F toggles); the default is a window at 80%% of the screen",
    )
    mode.add_argument(
        "--window", type=_window_size, metavar="WxH", help="start in a window of this size"
    )
    view.add_argument(
        "--display",
        type=_display,
        default=os.environ.get("SP_DISPLAY", "primary"),
        help="monitor to use: 'primary' (default), 'auto' (largest "
        "secondary screen, e.g. a projector) or an index",
    )
    view.add_argument(
        "--kiosk",
        action="store_true",
        help="exhibition setup: starts sparse and builds up over hours, fullscreen, "
        "visitor hint and clock, console minimised",
    )

    world = p.add_argument_group("simulation")
    world.add_argument(
        "--stars",
        type=_ranged(app.MIN_STARS, app.MAX_STARS),
        help=f"starting stars (default {config.NUM_BOIDS}; {config.KIOSK_STARS} with --kiosk)",
    )
    world.add_argument(
        "--black-holes",
        type=_ranged(0, app.MAX_BLACK_HOLES),
        help=f"starting black holes (default {config.NUM_BLACK_HOLES}; "
        f"{config.KIOSK_BLACK_HOLES} with --kiosk)",
    )
    world.add_argument(
        "--seed", type=int, default=config.SEED, help="random seed (default %(default)s)"
    )
    world.add_argument(
        "--classic",
        action="store_true",
        help="2D black holes that need no GPU (M switches while running)",
    )

    rec = p.add_argument_group("recording (needs ffmpeg on PATH)")
    rec.add_argument(
        "--record", type=Path, metavar="FILE", help="render offline to FILE (.mp4 or .gif) and exit"
    )
    rec.add_argument(
        "--preset",
        choices=PRESETS,
        help="readme (16:9 GIF loop), reddit (4:5), reel (9:16) or wide (16:9 with the "
        "evolution timeline); other recording options override it",
    )
    rec.add_argument(
        "--size", type=_window_size, metavar="WxH", help="frame size (default 1920x1080)"
    )
    rec.add_argument(
        "--duration",
        type=float,
        metavar="SECONDS",
        help=f"length (default {RECORD_DEFAULTS['duration']:g})",
    )
    rec.add_argument(
        "--warmup",
        type=float,
        metavar="SECONDS",
        help="simulate this long before recording starts (default 0)",
    )
    rec.add_argument(
        "--panel",
        choices=("strip", "full"),
        help="include the evolution panel; recordings are clean by default",
    )

    # For tests and benchmarks; not part of the public interface.
    p.add_argument("--frames", type=_ranged(1, 10**9), help=argparse.SUPPRESS)
    p.add_argument("--profile", action="store_true", help=argparse.SUPPRESS)
    return p


def _pick(value, default):
    return default if value is None else value


def parse_args(argv: list[str] | None = None) -> app.Options:
    parser = build_parser()
    ns = parser.parse_args(argv)
    recording = ns.record is not None
    if not recording:
        for flag in ("preset", "size", "duration", "warmup", "panel"):
            if getattr(ns, flag) is not None:
                parser.error(f"--{flag} applies to --record")
    rec = {**RECORD_DEFAULTS, **PRESETS.get(ns.preset, {})}
    for key in ("size", "duration", "warmup", "panel"):
        if getattr(ns, key) is not None:
            rec[key] = getattr(ns, key)
    return app.Options(
        display=ns.display,
        fullscreen=ns.fullscreen or (ns.kiosk and ns.window is None),
        window_size=rec.get("size") if recording else ns.window,
        seed=ns.seed,
        stars=_pick(ns.stars, config.KIOSK_STARS if ns.kiosk else config.NUM_BOIDS),
        black_holes=_pick(
            ns.black_holes, config.KIOSK_BLACK_HOLES if ns.kiosk else config.NUM_BLACK_HOLES
        ),
        black_hole_style="classic" if ns.classic else config.BLACK_HOLE_STYLE,
        panel=rec["panel"] if recording else "strip",
        panel_scale=rec["panel_scale"] if recording else 1.0,
        frames=ns.frames,
        kiosk=ns.kiosk,
        profile=ns.profile,
        record=ns.record,
        record_seconds=rec["duration"],
        warmup_seconds=rec["warmup"],
    )


def main(argv: list[str] | None = None) -> int:
    options = parse_args(argv)
    try:
        app.run(options)
    except (DisplayError, RecorderError) as exc:  # bad --display, missing ffmpeg...
        print(f"selection-pressure: error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
