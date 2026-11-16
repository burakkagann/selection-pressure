"""
A short memory of the evolving population, for the evolution timeline.

Every ``interval`` frames the app records each gene's population average
and the size of every family (lineage).  The newest ``capacity`` samples are
kept: by default one sample a second for ten minutes at 60 fps.
"""

from __future__ import annotations

from collections import deque

import numpy as np

from . import config

SAMPLE_INTERVAL = 60  # frames between samples
CAPACITY = 600  # samples kept (10 minutes at one a second)


class EvolutionHistory:
    def __init__(self, interval: int = SAMPLE_INTERVAL, capacity: int = CAPACITY):
        self.interval = interval
        self.capacity = capacity
        self.clear()

    def clear(self) -> None:
        self._frames: deque[int] = deque(maxlen=self.capacity)
        self._genes: deque[np.ndarray] = deque(maxlen=self.capacity)
        self._families: deque[tuple[np.ndarray, np.ndarray]] = deque(maxlen=self.capacity)

    def __len__(self) -> int:
        return len(self._frames)

    def maybe_sample(self, sim, frame: int) -> None:
        """Record a sample when ``frame`` falls on the sampling interval."""
        if frame % self.interval == 0:
            self.sample(sim, frame)

    def sample(self, sim, frame: int) -> None:
        means = np.empty(len(config.GENOME_FIELDS))
        for i, (name, default, _lo, _hi) in enumerate(config.GENOME_FIELDS):
            values = sim.per_boid_params.get(name) if sim.per_boid_params else None
            means[i] = float(values.mean()) if values is not None and len(values) else default
        ids, counts = np.unique(sim.lineage_ids[: sim.num], return_counts=True)
        self._frames.append(frame)
        self._genes.append(means)
        self._families.append((ids, counts))

    # ---- queries ---------------------------------------------------------

    def span_frames(self) -> int:
        return self._frames[-1] - self._frames[0] if len(self._frames) > 1 else 0

    def gene_series(self) -> np.ndarray:
        """Gene averages over time, shape (samples, genes)."""
        if not self._genes:
            return np.empty((0, len(config.GENOME_FIELDS)))
        return np.stack(self._genes)

    def family_shares(self, family_ids) -> np.ndarray:
        """Share of the population held by each of ``family_ids`` over time.

        Returns shape (samples, len(family_ids) + 1); the last column is every
        other family together.  Rows sum to 1.
        """
        family_ids = np.asarray(family_ids)
        out = np.zeros((len(self._families), len(family_ids) + 1))
        for row, (ids, counts) in enumerate(self._families):
            total = counts.sum()
            if total == 0:
                continue
            idx = np.searchsorted(ids, family_ids)
            idx = np.clip(idx, 0, max(len(ids) - 1, 0))
            present = len(ids) > 0
            found = (ids[idx] == family_ids) if present else np.zeros(len(family_ids), bool)
            shares = np.where(found, counts[idx] if present else 0, 0) / total
            out[row, :-1] = shares
            out[row, -1] = max(0.0, 1.0 - shares.sum())
        return out
