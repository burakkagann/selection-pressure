"""Headless end-to-end checks of the app loop (SDL dummy video driver)."""

import numpy as np
import pygame
import pytest

from selection_pressure import app, cli


@pytest.fixture
def make_app(tmp_path):
    created = []

    def factory(**overrides):
        pygame.init()
        settings = {"window_size": (480, 270), "stars": 80, "black_holes": 2}
        opts = app.Options(**{**settings, **overrides}, screenshot_dir=tmp_path)
        instance = app.App(opts)
        created.append(instance)
        return instance

    yield factory
    for instance in created:
        instance.close()
    pygame.quit()


def advance(a, frames):
    for _ in range(frames):
        a.step()
        a.draw()


def test_frames_render_something(make_app):
    a = make_app()
    advance(a, 30)
    pixels = pygame.surfarray.array3d(a.screen)
    assert pixels.max() > 0, "screen should not be black after 30 frames"
    assert a.frame == 30


def test_every_key_binding(make_app):
    a = make_app()
    keys = [
        pygame.K_RIGHTBRACKET,
        pygame.K_RIGHTBRACKET,
        pygame.K_EQUALS,
        pygame.K_MINUS,
        pygame.K_LEFTBRACKET,
        pygame.K_h,
        pygame.K_s,
        pygame.K_SPACE,
    ]
    for key in keys:
        a.handle_key(key)
        advance(a, 2)
    assert len(a.predators) == 2  # +2 capped at 3, then -1
    assert a.sim.num == 80
    assert a.paused
    frame = a.frame
    advance(a, 5)
    assert a.frame == frame, "paused app must not advance"
    a.handle_key(pygame.K_SPACE)
    a.handle_key(pygame.K_q)
    assert not a.running


def test_black_hole_limits(make_app):
    a = make_app()
    for _ in range(10):
        a.add_black_hole()
    assert len(a.predators) == app.MAX_BLACK_HOLES
    for _ in range(10):
        a.remove_black_hole()
    assert len(a.predators) == app.MIN_BLACK_HOLES


def test_reset_restores_the_initial_world(make_app):
    a = make_app()
    first = a.sim.positions.copy()
    advance(a, 20)
    a.add_black_hole()
    a.handle_key(pygame.K_r)
    assert a.frame == 0 and len(a.predators) == 2
    np.testing.assert_array_equal(a.sim.positions, first)


def test_fullscreen_toggle_resizes_the_world(make_app):
    a = make_app()
    a.handle_key(pygame.K_f)
    advance(a, 3)
    assert a.fullscreen
    assert (a.sim.width, a.sim.height) == a.size
    assert all(p.width == a.size[0] for p in a.predators)
    a.handle_key(pygame.K_f)
    advance(a, 3)
    assert not a.fullscreen and (a.sim.width, a.sim.height) == a.size


def test_screenshots_never_overwrite(make_app, tmp_path):
    (tmp_path / "sp_screenshot_001.png").write_bytes(b"keep me")
    a = make_app()
    advance(a, 3)
    a.handle_key(pygame.K_s)
    advance(a, 1)
    assert (tmp_path / "sp_screenshot_001.png").read_bytes() == b"keep me"
    assert (tmp_path / "sp_screenshot_002.png").stat().st_size > 0


def test_screenshot_leaves_out_the_panels(make_app, tmp_path):
    a = make_app()
    advance(a, 3)
    a.handle_key(pygame.K_h)  # controls card in the middle of the screen
    a.handle_key(pygame.K_s)
    advance(a, 1)  # the screenshot is taken during this frame
    shot = pygame.surfarray.array3d(pygame.image.load(str(tmp_path / "sp_screenshot_001.png")))
    screen = pygame.surfarray.array3d(a.screen)
    corner = (slice(0, 40), slice(0, 40))  # no panel reaches the top-left corner
    middle = (slice(200, 280), slice(120, 150))  # under the controls card
    np.testing.assert_array_equal(shot[corner], screen[corner])
    assert not np.array_equal(shot[middle], screen[middle])


def test_panel_key_cycles_strip_timeline_off(make_app):
    a = make_app()
    assert a.panel == "strip"
    seen = []
    for _ in range(3):
        advance(a, 2)
        seen.append(a.panel)
        a.handle_key(pygame.K_i)
    assert seen == ["strip", "full", "off"] and a.panel == "strip"


def test_help_card_and_tuning_panel_do_not_overlap(make_app):
    a = make_app()
    a.handle_key(pygame.K_h)
    assert a.show_help
    a.handle_key(pygame.K_g)
    assert a.tuning.visible and not a.show_help
    advance(a, 2)


def test_history_is_sampled_and_cleared_on_reset(make_app):
    a = make_app()
    a.history.interval = 5
    a.history.clear()
    advance(a, 21)
    assert len(a.history) == 5  # frames 0, 5, 10, 15, 20
    a.handle_key(pygame.K_r)
    assert len(a.history) == 0


@pytest.mark.parametrize("size", [(320, 240), (1080, 1350), (1920, 1080)])
def test_every_view_draws_at_any_size(make_app, size):
    a = make_app(window_size=size)
    a.opts.kiosk = True  # visitor hint and clock (set late: kiosk minimises the console)
    for panel in app.PANELS:
        a.panel = panel
        a.show_help = True
        a.tuning.visible = True
        advance(a, 7)  # past the panel cache


def test_cli_runs_a_fixed_number_of_frames():
    assert cli.main(["--window", "400x300", "--frames", "15", "--stars", "40"]) == 0


def test_cli_reports_a_missing_display(capsys):
    assert cli.main(["--display", "42", "--frames", "1"]) == 2
    assert "does not exist" in capsys.readouterr().err
