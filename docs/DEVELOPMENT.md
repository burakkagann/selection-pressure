# Development notes

For people who fork, modify or extend Selection Pressure.

## Setup

```bash
pip install -e ".[dev]"
pre-commit install          # ruff lint + format and basic hygiene on every commit
pytest                      # headless; uses SDL's dummy video driver
```

With [uv](https://docs.astral.sh/uv/), `uv sync` installs the exact versions from `uv.lock`.

The suite covers the simulation invariants, every feature switch, the CLI, the key bindings, the panels, recording, and a numerical regression check against `tests/data/golden.npz`. After an intentional behaviour change, regenerate it with `python tests/update_golden.py` and commit the new file with the change. Tests that need OpenGL skip themselves on machines without it.

CI runs the tests on Linux, Windows and macOS for Python 3.10-3.13 on every push and pull request, and weekly to catch breakage from new dependency releases.

## Architecture

All runtime code is in [src/selection_pressure/](../src/selection_pressure/):

| Module | Role |
|---|---|
| `cli.py` | Command-line options and recording presets, turned into an `app.Options` |
| `app.py` | `App`: window, input, the per-frame pipeline and the main loop |
| `simulation.py` | Boid physics, predator behaviour, evolution, quorum (pure NumPy, no pygame) |
| `nebula.py` | `NebulaField`: resource patches, density, depletion, regeneration |
| `rendering.py` | Trails, boids, 2D black-hole effects, bloom, screen-space lensing |
| `blackhole_gl.py` | GPU particle black holes through moderngl, adapted from [lechebs/nbody](https://github.com/lechebs/nbody) |
| `hud.py` | Evolution strip and timeline, controls card, kiosk hint and clock |
| `ui.py` | Shared panel look: colours, bundled fonts, scaling with window size |
| `history.py` | Gene averages and family sizes over time, for the timeline |
| `tuning.py` | Live tuning panel for the GPU black holes |
| `background.py` | Procedural galaxy background, generated once at startup |
| `display.py` | Monitor discovery and Windows DPI / console helpers |
| `recorder.py` | Offline MP4 / GIF capture through ffmpeg |
| `config.py` | All tunable parameters |

Each frame the app steps the predators and `BoidsSimulation`, draws into a persistent trail surface that fades a little every frame, composites it over the background, then adds bloom, the black holes and the panels. With the particle style the disks are drawn on the GPU and blended into the finished frame around each hole, and the 2D predator stages are skipped. The simulation has no pygame dependency and can run headless, which is how most of the tests exercise it.

## Configuration

[config.py](../src/selection_pressure/config.py) is sectioned by subsystem (boids, predators, nebula, quorum, evolution, visuals), and almost every constant has a comment with a suggested range. A few worth knowing:

| Constant | Default | Meaning |
|---|---|---|
| `NUM_BOIDS`, `NUM_BLACK_HOLES` | 400, 2 | Starting world (also `--stars`, `--black-holes`) |
| `KIOSK_STARS`, `KIOSK_BLACK_HOLES` | 50, 1 | The sparse exhibition start used by `--kiosk` |
| `POPULATION_TARGET` | 800 | Population cap, reached after about 3 hours |
| `TARGET_FPS` | 60 | The simulation is tuned per frame at 60 fps |
| `EVOLUTION_ENABLED` | `True` | The genetic algorithm |
| `NEBULA_FIELDS_ENABLED` | `True` | The foraging layer |
| `QUORUM_ENABLED` | `True` | Fortress mode |

Every `*_ENABLED` switch can be turned off on its own; the test suite runs the full pipeline with each one disabled. Hidden options for benchmarking: `--frames N` quits after N frames, and `--profile` prints per-stage frame timings.

## Known quirks and limitations

- **Shared starvation window.** When any black hole starves and respawns, every hole's kill count resets. That suited the exhibition, where they were evaluated as a group, but can feel unfair with more holes or in long experiments.
- **No save or load.** Each launch is a fresh simulation, with no checkpoint for the evolved genomes.
- **Sizes and speeds are in pixels.** The disks were tuned on a 1080 px wide canvas and the motion for a 4K projection wall (about 1.45x the original 1080p pace; `config.py` explains how to slow it down). On a 4K screen the holes look smaller, and in a small window they cover more of it; adjust them with `G`.
- **Fullscreen is borderless**, not exclusive. It stays visible when another screen has focus, which helps with a projector, but on a single monitor the mouse can still reach other windows.
- **Monitor positions on macOS and Linux.** Without the Windows API the piece knows each monitor's size but not its position, so `--display` may place a fullscreen window on the wrong screen. A window, the default, always works.
- **Performance scales with star count squared.** The neighbour-distance matrix is O(n²) and becomes the bottleneck above about 1000 stars. `POPULATION_TARGET = 800` keeps a mid-range machine near 60 fps.
