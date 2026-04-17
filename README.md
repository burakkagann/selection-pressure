# Selection Pressure

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org)
[![pygame](https://img.shields.io/badge/pygame-2.5%2B-green.svg)](https://www.pygame.org)
[![NumPy](https://img.shields.io/badge/numpy-1.24%2B-orange.svg)](https://numpy.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Emergent flocking under gravitational threat.

A real-time generative-art simulation written in Python. Stars swarm, black holes hunt, and an evolutionary algorithm running beneath the surface selects for survival. Originally shown as a wall-projection installation in the *Pixels2GenAI* exhibition (2026) under the title **SELECTION PRESSURE**.

---

## Table of Contents

- [Demo](#demo)
- [Overview](#overview)
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Known Quirks & Limitations](#known-quirks--limitations)
- [License](#license)
- [Credits](#credits)

---

## Demo

*Screenshots and a short video of the installation will be added here.*

<!-- ![Selection Pressure screenshot](docs/screenshot.png) -->

---

## Overview

Selection Pressure is built on three rules drawn from Craig Reynolds' 1987 boid flocking model: separate from neighbours, align with their heading, steer toward the group centre. On top of that foundation sit several interacting systems that push the flock around and give the viewer something to watch on a long timescale.

The piece was designed to run for four hours on a single boot. It starts with 50 stars and grows to roughly 800 over the first three hours, then holds at full intensity. A small audience interaction is exposed through the `[` and `]` keys, which add or remove black holes between 1 and 3.

## Features

- **Boid flocking** with evolvable per-star parameters (separation, alignment, cohesion weights, and more).
- **Black-hole predators** with gravitational lensing, photon rings, and accretion glow. Their mass grows when they feed and decays when they starve.
- **Nebula resource fields.** Stars carry an internal energy value that depletes over time and replenishes only inside a nebula patch. Food becomes a reason to move.
- **Quorum sensing.** When local density crosses a threshold, stars shift into a defensive "fortress" mode that halves their energy drain but holds them in place. Hungry stars eventually break formation to forage.
- **Evolutionary algorithm.** Survivors pass their behavioural weights to the next generation through tournament selection and uniform crossover. Lineages are visible in the evolution panel (bottom-left).
- **Age-coloured trails** that shift from warm to cool as they persist, revealing the social forces shaping the flock.

## Requirements

- Python 3.10 or newer
- `pygame >= 2.5`
- `numpy >= 1.24`

Tested on Windows 10. The Windows-specific DPI and console-hiding calls are wrapped in `try/except`, so the code should run on macOS and Linux too, though multi-monitor display selection has only been exercised on Windows (see [Known Quirks](#known-quirks--limitations)).

## Installation

```bash
git clone https://github.com/<your-username>/selection-pressure.git
cd selection-pressure
pip install -r requirements.txt
```

A virtual environment is recommended:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

From the repository root:

```bash
python -m selection_pressure
```

On multi-monitor setups the piece tries to pick the largest non-primary display, which is useful for projector use. To force a specific monitor, set `SP_DISPLAY` before launch:

```bash
# Windows (PowerShell)
$env:SP_DISPLAY=1; python -m selection_pressure

# macOS / Linux
SP_DISPLAY=1 python -m selection_pressure
```

### Controls

| Key         | Action                         |
|-------------|--------------------------------|
| `ESC` / `Q` | Quit                           |
| `SPACE`     | Pause / resume                 |
| `R`         | Reset simulation               |
| `F`         | Toggle fullscreen              |
| `H`         | Toggle help overlay            |
| `S`         | Save screenshot                |
| `+` / `-`   | Add / remove stars (50 at a time) |
| `[` / `]`   | Add / remove black holes (1–3) |

Screenshots are written to the repository root as `sp_screenshot_NNN.png`.

## Configuration

All tunable parameters live in [selection_pressure/config.py](selection_pressure/config.py). The file is sectioned by subsystem (window, boids, predators, nebula, quorum, evolution, visuals) and most constants have a short comment explaining what they do. There are no CLI flags; edit the file, save, and re-run.

A few defaults worth knowing:

| Constant                | Default     | Meaning                                 |
|-------------------------|-------------|-----------------------------------------|
| `WIDTH`, `HEIGHT`       | 1920, 1080  | Target render resolution                |
| `NUM_BOIDS`             | 50          | Starting star count                     |
| `POPULATION_TARGET`     | 800         | Hard cap, reached at ~3 hours           |
| `TARGET_FPS`            | 60          |                                         |
| `EVOLUTION_ENABLED`     | `True`      | Turn the GA on/off                      |
| `NEBULA_FIELDS_ENABLED` | `True`      | Enable the foraging layer               |
| `QUORUM_ENABLED`        | `True`      | Enable fortress mode                    |

## Architecture

All runtime code is in [selection_pressure/](selection_pressure/):

| Module          | Role                                                                   |
|-----------------|------------------------------------------------------------------------|
| `__main__.py`   | Package entry point, invoked by `python -m selection_pressure`         |
| `main.py`       | Main loop, event handling, and rendering pipeline wiring               |
| `config.py`     | All simulation parameters                                              |
| `simulation.py` | Boid physics, predator behaviour, evolution, quorum, nebula updates    |
| `rendering.py`  | Trails, bloom, gravitational lensing, HUD, evolution panel             |
| `nebula.py`     | `NebulaField` — resource patch positions, density, depletion, regen    |
| `background.py` | Procedural galaxy background generation                                |
| `__init__.py`   | Package marker                                                         |

The runtime is single-process, single-thread. Every subsystem mutates state inside `BoidsSimulation.step()`, then `rendering.py` draws it. No disk I/O during the main loop other than screenshots on demand.

## Known Quirks & Limitations

Things worth knowing if you fork, modify, or run this on unfamiliar hardware:

- **No CLI arguments.** All configuration happens by editing `selection_pressure/config.py`. This was deliberate for the exhibition (one fixed recipe) but will feel rigid if you want to sweep parameters. A CLI or config-file loader would be a reasonable first contribution.

- **Shared predator starvation window.** When any predator starves and respawns, *all* predators' kill counts reset. This was fine in the exhibition (predators evaluate as a cohort) but can feel unfair if you add more than three predators or run long ablations.

- **Trails persist across `R` if the galaxy background is off.** `R` clears the trail surface, but if `GALAXY_BG_ENABLED = False` there's no subsequent paint to cover old pixels on the first frame. Leaving the galaxy background on (the default) avoids this.

- **No save/load.** Each launch is a fresh simulation. There's no checkpoint for the evolved genome or predator state. This was intentional for the exhibition, which expected a clean start on every boot.

- **No audio.** The piece is silent by design. If you're running this in a gallery you'll want a separate sound source, or none at all.

- **Screenshots land in the working directory**, not next to the package. If you launch from somewhere unusual, expect your screenshots to show up there.

- **Fullscreen is borderless**, not exclusive. On a single-monitor setup this means your mouse can still reach other windows if you Alt-Tab or move the cursor to the edges.

- **Performance scales with boid count squared.** The neighbour-distance matrix is O(n²) and becomes the bottleneck around 1000+ boids on a mid-range GPU. `POPULATION_TARGET = 800` is tuned to stay under 16.6 ms/frame on the exhibition hardware; push it higher at your own risk.

## License

Released under the [MIT License](LICENSE).

## Credits

**Burak Kagan Yilmazer**, 2026. Part of the *Pixels2GenAI* exhibition.

The flocking model is based on Craig W. Reynolds, *Flocks, Herds, and Schools: A Distributed Behavioral Model* (SIGGRAPH 1987).
