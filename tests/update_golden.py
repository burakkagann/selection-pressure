"""Regenerate tests/data/golden.npz after an intended behaviour change."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from test_toggles_and_golden import GOLDEN, golden_run  # noqa: E402

GOLDEN.parent.mkdir(exist_ok=True)
np.savez_compressed(GOLDEN, **golden_run())
print(f"wrote {GOLDEN}")
