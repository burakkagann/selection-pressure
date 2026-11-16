import os

# Headless pygame for every test: no window, no audio device.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402
import pytest  # noqa: E402

from selection_pressure.app import make_predators, make_sim  # noqa: E402

W, H = 640, 360


@pytest.fixture
def sim():
    return make_sim(W, H, num_stars=120, seed=7)


@pytest.fixture
def predators():
    return make_predators(W, H, count=2)


@pytest.fixture
def pygame_display():
    pygame.init()
    yield pygame.display.set_mode((W, H))
    pygame.quit()


def run(sim, predators, frames, start=0):
    """Advance the simulation like the app loop does (without rendering)."""
    for frame in range(start, start + frames):
        for p in predators:
            p.step(sim.positions, [q for q in predators if q is not p])
        sim.step(frame, predators or None)
        sim.check_predator_starvation(predators, frame)
