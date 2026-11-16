import numpy as np
import pytest

from conftest import H, W, run
from selection_pressure import config
from selection_pressure.app import make_predators, make_sim
from selection_pressure.config import PredatorParams
from selection_pressure.simulation import (
    FLEE_SPEED_BOOST,
    _mutate_predator_params,
    curl_noise,
    pairwise_offsets,
    wrap_delta,
)


def assert_arrays_consistent(sim):
    for name in sim.PER_BOID_ARRAYS:
        assert len(getattr(sim, name)) == sim.num, name
    for name, arr in sim.per_boid_params.items():
        assert len(arr) == sim.num, name


def test_same_seed_is_deterministic():
    a, b = make_sim(W, H, 150, seed=3), make_sim(W, H, 150, seed=3)
    pa, pb = make_predators(W, H, 2), make_predators(W, H, 2)
    run(a, pa, 120)
    run(b, pb, 120)
    np.testing.assert_array_equal(a.positions, b.positions)
    assert a.total_consumed == b.total_consumed


def test_different_seeds_differ():
    a, b = make_sim(W, H, 150, seed=3), make_sim(W, H, 150, seed=4)
    run(a, [], 10)
    run(b, [], 10)
    assert not np.allclose(a.positions, b.positions)


def test_positions_stay_on_the_torus(sim, predators):
    for _ in range(10):
        run(sim, predators, 30)
        assert (sim.positions >= 0).all()
        assert (sim.positions[:, 0] < W).all() and (sim.positions[:, 1] < H).all()


def test_speed_limits(sim, predators):
    run(sim, predators, 200)
    max_speed = sim._p("max_speed")
    assert (sim.speeds <= max_speed * FLEE_SPEED_BOOST + 1e-9).all()
    assert np.isfinite(sim.velocities).all()


def test_add_and_remove_keep_arrays_in_sync(sim):
    sim.add_boids(30, frame_num=5)
    assert sim.num == 150
    assert_arrays_consistent(sim)
    sim.remove_boids(40)
    assert sim.num == 110
    assert_arrays_consistent(sim)


def test_add_zero_boids_is_a_no_op(sim):
    sim.add_boids(0)
    assert sim.num == 120


def test_remove_boids_takes_the_youngest_and_keeps_ten(sim):
    sim.add_boids(5, frame_num=99)
    sim.remove_boids(5)
    assert (sim.birth_frame < 99).all()
    sim.remove_boids(10_000)
    assert sim.num == 10
    assert_arrays_consistent(sim)


def test_evolution_keeps_genomes_in_bounds(monkeypatch):
    monkeypatch.setattr(config, "CULL_INTERVAL_FRAMES", 50)
    monkeypatch.setattr(config, "PERIODIC_SPAWN_INTERVAL", 40)
    sim = make_sim(W, H, 200, seed=11)
    preds = make_predators(W, H, 3)
    run(sim, preds, 400)
    assert sim.total_consumed > 0, "scenario should exercise predation"
    assert_arrays_consistent(sim)
    for name, _default, lo, hi in config.GENOME_FIELDS:
        values = sim.per_boid_params[name]
        assert values.min() >= lo and values.max() <= hi, name


def test_predator_starvation_explodes_and_respawns(monkeypatch):
    monkeypatch.setattr(config, "PREDATOR_STARVATION_FRAMES", 30)
    sim = make_sim(W, H, 40, seed=1)
    pred = make_predators(W, H, 1)[0]
    pred.kill_count = 5
    for frame in range(30):
        pred.step(sim.positions)
        pred.frames_since_last_kill = frame + 1  # make sure it never eats
    assert pred.starved
    before = sim.num
    explosions = sim.check_predator_starvation([pred], 30)
    assert len(explosions) == 1
    assert sim.num == before + config.PREDATOR_EXPLOSION_BOIDS
    assert pred.generation == 1 and not pred.starved
    assert pred.kill_count == 0
    assert_arrays_consistent(sim)


def test_mutated_predator_params_stay_in_bounds():
    rng = np.random.default_rng(0)
    params = PredatorParams()
    for _ in range(200):
        params = _mutate_predator_params(params, rng)
    for name, default, lo, hi in config.PREDATOR_GENOME_FIELDS:
        value = getattr(params, name)
        assert lo <= value <= hi, name
        assert isinstance(value, int) == isinstance(default, int), name


def test_tournament_selection_prefers_fitter_boids(sim):
    fitness = np.linspace(0.0, 1.0, sim.num)
    picks = [sim._select_parent(fitness) for _ in range(500)]
    assert np.mean(picks) > sim.num * 0.6  # uniform picking would average 0.5


def test_select_parent_with_nobody_alive(sim):
    assert sim._select_parent(np.full(sim.num, -np.inf)) is None


def test_resize_scales_positions(sim, predators):
    rel = sim.positions / (W, H)
    sim.resize(W * 2, H)
    np.testing.assert_allclose(sim.positions / (W * 2, H), rel)
    for p in predators:
        p.resize(W * 2, H)
        assert p.width == W * 2
    run(sim, predators, 5)
    assert (sim.positions[:, 0] < W * 2).all()


def test_wrap_delta_is_shortest_path():
    d = np.array([-350.0, -10.0, 0.0, 10.0, 350.0])
    np.testing.assert_allclose(wrap_delta(d, 400.0), [50.0, -10.0, 0.0, 10.0, -50.0])


def test_pairwise_offsets_are_antisymmetric():
    pos = np.random.default_rng(0).uniform(0, 100, (20, 2))
    dx, dy, dist = pairwise_offsets(pos, 100, 100)
    np.testing.assert_allclose(dx, -dx.T, atol=1e-5)
    np.testing.assert_allclose(np.diag(dist), 0)
    assert dist.max() <= np.hypot(50, 50) + 1e-3


def test_curl_noise_is_divergence_free():
    xs, ys = np.meshgrid(np.linspace(100, 500, 30), np.linspace(100, 300, 30))
    x, y, h = xs.ravel(), ys.ravel(), 0.5
    v = lambda px, py: curl_noise(px, py, 10.0, 0.003, 0.05)  # noqa: E731
    div = (v(x + h, y)[:, 0] - v(x - h, y)[:, 0]) / (2 * h) + (
        v(x, y + h)[:, 1] - v(x, y - h)[:, 1]
    ) / (2 * h)
    assert np.abs(div).max() < 1e-4


@pytest.mark.parametrize("count", [0, 1, 3])
def test_make_predators_count(count):
    assert len(make_predators(W, H, count)) == count
