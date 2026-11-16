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
    assert not opts.fullscreen and opts.window_size is None  # a window at 80% of the screen
    assert opts.seed == config.SEED and opts.stars == config.NUM_BOIDS
    assert opts.black_holes == config.NUM_BLACK_HOLES
    assert opts.black_hole_style == config.BLACK_HOLE_STYLE
    assert opts.panel == "strip" and not opts.kiosk
    assert opts.frames is None and opts.record is None


def test_sp_display_env_is_still_honoured(monkeypatch):
    monkeypatch.setenv("SP_DISPLAY", "auto")
    assert cli.parse_args([]).display == "auto"


def test_full_option_set():
    opts = cli.parse_args(
        [
            "--display",
            "1",
            "--window",
            "800x600",
            "--seed",
            "9",
            "--stars",
            "300",
            "--black-holes",
            "2",
            "--classic",
            "--frames",
            "5",
            "--profile",
        ]
    )
    assert opts.display == "1"
    assert not opts.fullscreen and opts.window_size == (800, 600)
    assert (opts.seed, opts.stars, opts.black_holes, opts.frames) == (9, 300, 2, 5)
    assert opts.black_hole_style == "classic" and opts.profile


def test_fullscreen_and_kiosk():
    assert cli.parse_args(["--fullscreen"]).fullscreen
    kiosk = cli.parse_args(["--kiosk"])
    assert kiosk.kiosk and kiosk.fullscreen
    assert (kiosk.stars, kiosk.black_holes) == (config.KIOSK_STARS, config.KIOSK_BLACK_HOLES)
    busy_kiosk = cli.parse_args(["--kiosk", "--stars", "300", "--black-holes", "3"])
    assert (busy_kiosk.stars, busy_kiosk.black_holes) == (300, 3)
    windowed_kiosk = cli.parse_args(["--kiosk", "--window", "800x600"])
    assert not windowed_kiosk.fullscreen and windowed_kiosk.window_size == (800, 600)


def test_recordings_are_clean_by_default():
    opts = cli.parse_args(["--record", "clip.mp4"])
    assert opts.panel == "off"
    assert (opts.record_seconds, opts.warmup_seconds) == (15.0, 0.0)
    assert cli.parse_args(["--record", "clip.mp4", "--panel", "full"]).panel == "full"


@pytest.mark.parametrize("name", list(cli.PRESETS))
def test_presets(name):
    preset = cli.PRESETS[name]
    opts = cli.parse_args(["--record", "clip.mp4", "--preset", name])
    assert opts.window_size == preset["size"]
    assert opts.record_seconds == preset["duration"] and opts.warmup_seconds == preset["warmup"]
    assert opts.panel == preset["panel"]


def test_explicit_options_override_a_preset():
    opts = cli.parse_args(
        [
            "--record",
            "c.mp4",
            "--preset",
            "reel",
            "--duration",
            "9",
            "--size",
            "720x1280",
            "--panel",
            "strip",
        ]
    )
    assert opts.window_size == (720, 1280) and opts.record_seconds == 9.0
    assert opts.panel == "strip" and opts.warmup_seconds == cli.PRESETS["reel"]["warmup"]


def test_development_flags_are_hidden_from_help():
    text = cli.build_parser().format_help()
    assert "--frames" not in text and "--profile" not in text
    assert "--window" in text and "--preset" in text


@pytest.mark.parametrize(
    "args",
    [
        "--stars 5",
        "--stars 99999",
        "--black-holes 9",
        "--window 10x10",
        "--window big",
        "--window",
        "--display left",
        "--fullscreen --window 800x600",
        "--preset readme",  # recording options need --record
        "--panel full",
        "--duration 5",
        "--record c.mp4 --preset nope",
        "--windowed",  # removed in 1.0
        "--fps 30",
        "--no-hud",
        "--black-hole-style classic",
    ],
)
def test_invalid_arguments_exit_with_usage_error(args, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.parse_args(args.split())
    assert exc.value.code == 2
