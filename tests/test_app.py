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
        opts = app.Options(
            windowed=True,
            window_size=(480, 270),
            stars=80,
            black_holes=2,
            screenshot_dir=tmp_path,
            **overrides,
        )
        instance = app.App(opts)
        created.append(instance)
        return instance

    yield factory
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
    a.save_screenshot()
    assert (tmp_path / "sp_screenshot_001.png").read_bytes() == b"keep me"
    assert (tmp_path / "sp_screenshot_002.png").stat().st_size > 0


def test_cli_runs_a_fixed_number_of_frames():
    assert cli.main(["--windowed", "400x300", "--frames", "15", "--stars", "40"]) == 0


def test_cli_reports_a_missing_display(capsys):
    assert cli.main(["--display", "42", "--frames", "1"]) == 2
    assert "does not exist" in capsys.readouterr().err
