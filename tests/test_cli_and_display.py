from pathlib import Path

import pytest

from selection_pressure import cli, config
from selection_pressure.display import choose_display

MONITORS = [(0, 0, 1920, 1080), (1920, 0, 3840, 2160), (-1080, 0, 1080, 1920)]


def test_primary_is_the_monitor_at_origin():
    assert choose_display([(1920, 0, 800, 600), (0, 0, 1920, 1080)], "primary") == 1


def test_auto_prefers_the_largest_landscape_secondary():
    assert choose_display(MONITORS, "auto") == 1


def test_auto_with_one_monitor():
    assert choose_display(MONITORS[:1], "auto") == 0


def test_explicit_index_is_validated():
    assert choose_display(MONITORS, "2") == 2
    with pytest.raises(ValueError, match="does not exist"):
        choose_display(MONITORS, "3")


def test_default_options(monkeypatch):
    monkeypatch.delenv("SP_DISPLAY", raising=False)
    opts = cli.parse_args([])
    assert opts.display == "primary"
    assert not opts.windowed and opts.window_size is None
    assert opts.seed == config.SEED and opts.stars == config.NUM_BOIDS
    assert opts.frames is None and opts.show_hud


def test_sp_display_env_is_still_honoured(monkeypatch):
    monkeypatch.setenv("SP_DISPLAY", "auto")
    assert cli.parse_args([]).display == "auto"


def test_full_option_set():
    opts = cli.parse_args(
        [
            "--display",
            "1",
            "--windowed",
            "800x600",
            "--seed",
            "9",
            "--stars",
            "300",
            "--black-holes",
            "2",
            "--fps",
            "30",
            "--frames",
            "5",
            "--no-hud",
            "--kiosk",
            "--profile",
            "--screenshot-dir",
            "out",
        ]
    )
    assert opts.display == "1"
    assert opts.windowed and opts.window_size == (800, 600)
    assert (opts.seed, opts.stars, opts.black_holes, opts.fps, opts.frames) == (9, 300, 2, 30, 5)
    assert not opts.show_hud and opts.kiosk and opts.profile
    assert opts.screenshot_dir == Path("out")


def test_windowed_without_size():
    opts = cli.parse_args(["--windowed"])
    assert opts.windowed and opts.window_size is None


@pytest.mark.parametrize(
    "args",
    [
        "--stars 5",
        "--stars 99999",
        "--black-holes 9",
        "--windowed 10x10",
        "--windowed big",
        "--display left",
        "--fps 0",
    ],
)
def test_invalid_arguments_exit_with_usage_error(args, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.parse_args(args.split())
    assert exc.value.code == 2
