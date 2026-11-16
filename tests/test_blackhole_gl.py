"""GPU black holes: the renderer itself, the 2D fallback and the tuning panel."""

import numpy as np
import pygame
import pytest

from selection_pressure import app, blackhole_gl, cli, config, ui
from selection_pressure.tuning import CONTROLS, TuningPanel

W, H = 640, 360


class FakePredator:
    def __init__(self, x, y, mass=1.0, lunging=False):
        self.position = np.array([x, y], dtype=float)
        self.mass = mass
        self.lunging = lunging


@pytest.fixture
def gpu():
    renderer = blackhole_gl.ShaderBlackHole(W, H)
    if not renderer.available:
        pytest.skip(f"no OpenGL 3.3 context: {renderer.error}")
    yield renderer
    renderer.close()


@pytest.fixture
def scene():
    pygame.init()
    rng = np.random.default_rng(0)
    pixels = rng.integers(20, 90, (W, H, 3)).astype(np.uint8)
    yield pygame.surfarray.make_surface(pixels)
    pygame.quit()


def _pixels(surface):
    return pygame.surfarray.array3d(surface).astype(int)


def test_particle_disks_glow_around_a_black_centre(gpu, scene):
    holes = [FakePredator(110, 90), FakePredator(320, 270), FakePredator(530, 90, mass=1.5)]
    before = _pixels(scene)
    assert gpu.render(scene, holes, frame=10)
    after = _pixels(scene)
    for hole in holes:
        x, y = hole.position.astype(int)
        assert after[x, y].sum() == 0, "every hole, including the third, has a dark centre"
        ring = after[x + 30 : x + 45, y - 3 : y + 3]
        assert ring.mean() > before[x + 30 : x + 45, y - 3 : y + 3].mean(), "disk should glow"


def test_render_is_deterministic(scene):
    results = []
    for _ in range(2):
        renderer = blackhole_gl.ShaderBlackHole(W, H)
        if not renderer.available:
            pytest.skip(renderer.error)
        surface = scene.copy()
        renderer.render(surface, [FakePredator(300, 180, mass=1.4, lunging=True)], 30)
        renderer.close()
        results.append(_pixels(surface))
    assert np.array_equal(*results)


def test_no_predators_draws_nothing(gpu, scene):
    before = _pixels(scene)
    assert not gpu.render(scene, [], frame=0)
    assert np.array_equal(before, _pixels(scene))


def test_missing_moderngl_reports_unavailable(monkeypatch):
    monkeypatch.setattr(blackhole_gl, "moderngl", None)
    renderer = blackhole_gl.ShaderBlackHole(W, H)
    assert not renderer.available
    assert "moderngl" in renderer.error


# ---- app integration ------------------------------------------------------


@pytest.fixture
def make_app(tmp_path):
    created = []

    def factory(**overrides):
        pygame.init()
        opts = app.Options(window_size=(W, H), stars=60, black_holes=2, **overrides)
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


@pytest.mark.parametrize("style", app.BLACK_HOLE_STYLES)
def test_app_renders_every_style(make_app, style):
    a = make_app(black_hole_style=style)
    advance(a, 20)
    assert pygame.surfarray.array3d(a.screen).max() > 0
    if style == "classic":
        assert a.gpu is None


def test_app_falls_back_to_classic_without_gpu(make_app, monkeypatch):
    monkeypatch.setattr(blackhole_gl, "moderngl", None)
    a = make_app(black_hole_style="particle")
    advance(a, 5)
    assert a.gpu is None and a.gpu_error
    a.cycle_black_hole_style()
    assert a.bh_style == "classic"
    a.tuning.toggle()
    advance(a, 2)


def test_style_key_cycles_and_survives_resize(gpu, make_app):
    a = make_app(black_hole_style="particle")
    seen = []
    for _ in range(len(app.BLACK_HOLE_STYLES)):
        advance(a, 2)
        seen.append(a.bh_style)
        a.handle_key(pygame.K_m)
    assert sorted(seen) == sorted(app.BLACK_HOLE_STYLES)
    assert a.bh_style == "particle"
    a.toggle_fullscreen()
    a.toggle_fullscreen()
    advance(a, 2)


def test_cli_classic_flag():
    assert cli.parse_args([]).black_hole_style == config.BLACK_HOLE_STYLE
    assert cli.parse_args(["--classic"]).black_hole_style == "classic"


# ---- tuning panel -----------------------------------------------------------


def test_tuning_controls_exist_in_config():
    for controls in CONTROLS.values():
        for attr, _, kind, lo, hi in controls:
            value = getattr(config, attr)
            if kind == "float":
                assert lo <= value <= hi, attr


def test_tuning_panel_toggles_and_drags(gpu, make_app, monkeypatch, capsys):
    a = make_app(black_hole_style="particle")
    for attr, *_ in CONTROLS["particle"]:
        monkeypatch.setattr(config, attr, getattr(config, attr))
    panel = a.tuning
    a.handle_key(pygame.K_g)
    advance(a, 1)
    assert panel.visible

    kind, box, _ = panel._rects["BH_PD_LUNGE_SCALE"]
    before = config.BH_PD_LUNGE_SCALE
    down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=box.center)
    assert panel.handle_event(down)
    assert config.BH_PD_LUNGE_SCALE is (not before)

    _, knob, track = panel._rects["BH_PD_SPIN"]
    a.handle_event(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(track.right - 1, track.centery))
    )
    a.handle_event(
        pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(track.right - 1, track.centery))
    )
    assert abs(config.BH_PD_SPIN - 3.0) < 0.05  # right end of the slider

    style_box = panel._rects["__STYLE__"][1]
    a.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=style_box.center))
    assert a.bh_style == "classic"
    a.handle_key(pygame.K_m)
    assert a.bh_style == "particle"

    a.handle_key(pygame.K_d)
    out = capsys.readouterr().out
    assert 'BLACK_HOLE_STYLE = "particle"' in out and "BH_PD_SPIN = 2.9" in out
    a.handle_key(pygame.K_g)
    assert not panel.visible


def test_tuning_panel_with_classic_style():
    pygame.init()
    surface = pygame.Surface((W, H))
    panel = TuningPanel(lambda: None)
    panel.toggle()
    panel.draw(surface, "classic", ui.UI(H), "note")
    assert pygame.surfarray.array3d(surface).max() > 0
    pygame.quit()


def test_switching_style_mid_drag_does_not_crash(gpu, make_app, monkeypatch):
    a = make_app(black_hole_style="particle")
    monkeypatch.setattr(config, "BH_PD_SPIN", config.BH_PD_SPIN)
    a.handle_key(pygame.K_g)
    advance(a, 1)
    _, _, track = a.tuning._rects["BH_PD_SPIN"]
    a.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=track.center))
    a.handle_key(pygame.K_m)  # classic: the slider disappears while held
    advance(a, 1)
    a.handle_event(
        pygame.event.Event(pygame.MOUSEMOTION, pos=(track.x, track.y), buttons=(1, 0, 0))
    )
    a.handle_key(pygame.K_g)
    a.handle_key(pygame.K_g)
    assert a.tuning._drag_attr is None


def test_fallback_switches_to_classic(make_app, monkeypatch):
    monkeypatch.setattr(blackhole_gl, "moderngl", None)
    a = make_app(black_hole_style="particle")
    advance(a, 1)
    assert a.bh_style == "classic"


def test_black_hole_count_is_capped(monkeypatch):
    monkeypatch.setattr(config, "NUM_BLACK_HOLES", 5)
    assert len(app.make_predators(W, H)) == app.MAX_BLACK_HOLES == blackhole_gl.MAX_HOLES


def test_halo_cache_is_bounded(gpu):
    for reach in range(10, 10 + 3 * blackhole_gl.HALO_CACHE_SIZE):
        gpu._get_halo_surface(reach, 0.0)
    assert len(gpu._halo_cache) == blackhole_gl.HALO_CACHE_SIZE


def test_overlapping_holes_add_each_glow_once(gpu, monkeypatch):
    monkeypatch.setattr(config, "BH_PD_HALO_STRENGTH", 1.0)  # no halo: compare glow only
    blank = pygame.Surface((W, H))
    single = blank.copy()
    gpu.render(single, [FakePredator(320, 180)], frame=0)
    gpu._smooth_scale.clear()
    double = blank.copy()
    # hole B's square (reach 106 px) reaches into hole A's disk (outer 80 px)
    gpu.render(double, [FakePredator(320, 180), FakePredator(470, 180)], frame=0)
    region = (slice(366, 386), slice(165, 195))  # A's particles, inside B's square
    assert _pixels(single)[region].max() > 0, "region must contain A's glow"
    assert np.array_equal(_pixels(single)[region], _pixels(double)[region])


def test_cli_record_size():
    opts = cli.parse_args(["--record", "clip.mp4", "--size", "1080x1920"])
    assert opts.window_size == (1080, 1920)
    assert cli.parse_args(["--record", "clip.mp4"]).window_size is None
    with pytest.raises(SystemExit):
        cli.parse_args(["--size", "1080x1920"])  # only meaningful with --record
