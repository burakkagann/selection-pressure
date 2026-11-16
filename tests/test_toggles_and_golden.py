"""Feature-flag coverage and a numerical regression check.

``config.py`` exposes on/off switches for every subsystem.  Each one is
turned off in isolation and the full simulate + render pipeline is run, so a
code path that only works with every feature enabled fails here.

The golden test compares early frames of a seeded run against
``tests/data/golden.npz``.  The system is chaotic, so only the first frames
are compared (with a tolerance that absorbs float differences across
platforms).  Regenerate on purpose after an intended behaviour change:

    python tests/update_golden.py
"""

from pathlib import Path

import numpy as np
import pygame
import pytest

from conftest import H, W, run
from selection_pressure import config
from selection_pressure.app import App, Options, make_predators, make_sim

TOGGLES = [
    "BLACK_HOLE_ENABLED",
    "PREDATOR_EVOLUTION_ENABLED",
    "ACCRETION_ENABLED",
    "ACCRETION_HUNGER_ENABLED",
    "EVOLUTION_ENABLED",
    "EVOLUTION_COLOR_MODE",
    "NEBULA_FIELDS_ENABLED",
    "STAR_ENERGY_ENABLED",
    "CHEMOTAXIS_ENABLED",
    "QUORUM_ENABLED",
    "PERIODIC_SPAWN_ENABLED",
    "ATTRACTOR_ENABLED",
    "GALAXY_BG_ENABLED",
    "TWINKLE_ENABLED",
    "BLOOM_ENABLED",
    "LENS_ENABLED",
    "SPEED_AFFECTS_SIZE",
    "BLACK_HOLE_FEAR_COLOR_SHIFT",
    "ACCRETION_GLOW_ENABLED",
    "PHOTON_SPHERE_ENABLED",
    "QUORUM_VISUAL_PULSE",
]

GOLDEN = Path(__file__).parent / "data" / "golden.npz"
GOLDEN_FRAMES = (1, 10, 30)


def test_every_toggle_is_a_real_config_flag():
    for name in TOGGLES:
        assert isinstance(getattr(config, name), bool), name


@pytest.mark.parametrize("flag", TOGGLES)
def test_pipeline_runs_with_flag_off(flag, monkeypatch, tmp_path):
    monkeypatch.setattr(config, flag, False)
    monkeypatch.setattr(config, "PERIODIC_SPAWN_INTERVAL", 20)
    monkeypatch.setattr(config, "CULL_INTERVAL_FRAMES", 25)
    monkeypatch.setattr(config, "PREDATOR_STARVATION_FRAMES", 40)
    pygame.init()
    try:
        app = App(
            Options(
                window_size=(320, 240),
                stars=60,
                black_holes=2,
                screenshot_dir=tmp_path,
            )
        )
        for _ in range(60):
            app.step()
            app.draw()
        assert np.isfinite(app.sim.positions).all()
    finally:
        pygame.quit()


def golden_run():
    sim = make_sim(W, H, num_stars=200, seed=2024)
    preds = make_predators(W, H, 2)
    snapshots = {}
    for frame in range(max(GOLDEN_FRAMES)):
        run(sim, preds, 1, start=frame)
        if frame + 1 in GOLDEN_FRAMES:
            snapshots[f"pos{frame + 1}"] = sim.positions.copy()
    return snapshots


def test_matches_golden_early_frames():
    expected = np.load(GOLDEN)
    actual = golden_run()
    for key in expected.files:
        np.testing.assert_allclose(actual[key], expected[key], atol=1e-3, err_msg=key)
