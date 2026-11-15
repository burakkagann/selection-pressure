import numpy as np

from selection_pressure import config
from selection_pressure.config import BoidParams, PredatorParams
from selection_pressure.nebula import NebulaField


def test_genome_defaults_lie_inside_their_bounds():
    for fields in (config.GENOME_FIELDS, config.PREDATOR_GENOME_FIELDS):
        for name, default, lo, hi in fields:
            assert lo <= default <= hi, name


def test_genome_fields_exist_on_param_dataclasses():
    for name, *_ in config.GENOME_FIELDS:
        assert hasattr(BoidParams(), name), name
    for name, *_ in config.PREDATOR_GENOME_FIELDS:
        assert hasattr(PredatorParams(), name), name


def test_palettes_are_rgb():
    assert config.ACTIVE_PALETTE in config.PALETTES
    for palette in config.PALETTES.values():
        assert len(palette) >= 2
        for colour in palette:
            assert len(colour) == 3 and all(0 <= c <= 255 for c in colour)


def test_threshold_ordering():
    assert config.QUORUM_THRESHOLD > config.DEFENSIVE_LOCAL_THRESHOLD
    assert config.BH_MASS_MIN <= config.BH_MASS_INITIAL <= config.BH_MASS_MAX
    assert 0 < config.STAR_ENERGY_INITIAL <= config.STAR_ENERGY_MAX
    assert config.PANIC_RADIUS_OK if hasattr(config, "PANIC_RADIUS_OK") else True
    p = PredatorParams()
    assert p.consume_radius < p.panic_radius < p.flee_radius < p.sight_radius


def test_nebula_densities_stay_in_range():
    rng = np.random.default_rng(0)
    field = NebulaField(4, 640, 360, rng)
    boids = rng.uniform(0, 360, (300, 2))
    for _ in range(500):
        field.step(boids)
        assert (field.densities >= config.NEBULA_CLOUD_MIN_DENSITY - 1e-9).all()
        assert (field.densities <= config.NEBULA_CLOUD_MAX_DENSITY + 1e-9).all()
    assert (field.get_density_at(boids) >= 0).all()


def test_nebula_directions_are_unit_vectors():
    rng = np.random.default_rng(1)
    field = NebulaField(5, 640, 360, rng)
    directions = field.get_nearest_cloud_direction(rng.uniform(0, 360, (100, 2)))
    lengths = np.linalg.norm(directions, axis=1)
    assert np.allclose(lengths[lengths > 0], 1.0, atol=1e-6)
