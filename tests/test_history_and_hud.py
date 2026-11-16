"""Evolution history, panel helpers and the bundled fonts."""

from types import SimpleNamespace

import numpy as np
import pygame
import pytest

from selection_pressure import config, hud, ui
from selection_pressure.history import EvolutionHistory


def fake_sim(lineages, separation=None):
    lineages = np.asarray(lineages)
    params = {}
    if separation is not None:
        params["separation_weight"] = np.full(len(lineages), separation)
    return SimpleNamespace(num=len(lineages), lineage_ids=lineages, per_boid_params=params)


def test_history_keeps_the_newest_samples():
    h = EvolutionHistory(interval=10, capacity=3)
    for frame in range(0, 60):
        h.maybe_sample(fake_sim([1, 2], separation=frame), frame)
    assert len(h) == 3
    assert h.span_frames() == 20
    np.testing.assert_array_equal(h.gene_series()[:, 0], [30, 40, 50])


def test_missing_genes_fall_back_to_their_defaults():
    h = EvolutionHistory()
    h.sample(fake_sim([1, 1, 2]), 0)
    defaults = [field[1] for field in config.GENOME_FIELDS]
    np.testing.assert_allclose(h.gene_series()[0], defaults)


def test_family_shares_add_up_to_one():
    h = EvolutionHistory()
    h.sample(fake_sim([1, 1, 2, 3]), 0)
    h.sample(fake_sim([2, 2, 2, 9]), 60)
    shares = h.family_shares([2, 1, 7])  # 7 never existed
    np.testing.assert_allclose(shares[0], [0.25, 0.5, 0.0, 0.25])
    np.testing.assert_allclose(shares[1], [0.75, 0.0, 0.0, 0.25])
    np.testing.assert_allclose(shares.sum(axis=1), 1.0)


def test_empty_history():
    h = EvolutionHistory()
    assert len(h) == 0 and h.span_frames() == 0
    assert h.gene_series().shape == (0, len(config.GENOME_FIELDS))
    assert h.family_shares([1]).shape == (0, 2)


def test_gene_labels_match_the_genome():
    assert len(hud.GENES) == len(config.GENOME_FIELDS)
    grouped = sorted(i for _, members in hud.GENE_GROUPS for i in members)
    assert grouped == list(range(len(config.GENOME_FIELDS)))


@pytest.mark.parametrize(("height", "scale"), [(360, 0.7), (1080, 1.0), (1620, 1.5), (4320, 2.0)])
def test_ui_scale_follows_window_height(height, scale):
    assert ui.scale_for(height) == pytest.approx(scale)


def test_bundled_fonts_load():
    pygame.font.init()
    try:
        u = ui.UI(1080)
        for font in (u.title, u.body, u.mono, u.caps):
            assert font.size("Separation · 59%")[0] > 0
    finally:
        pygame.font.quit()


def test_fit_only_shrinks():
    pygame.init()
    try:
        panel = pygame.Surface((400, 200), pygame.SRCALPHA)
        assert ui.fit(panel, 800, 800) is panel
        assert ui.fit(panel, 200, 800).get_size() == (200, 100)
    finally:
        pygame.quit()
