# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.0] - Unreleased

First packaged release.

### Added
- `selection-pressure` command with options for display, window or fullscreen,
  seed, population, black hole style and kiosk mode.
- `--record` renders MP4 or GIF clips offline through ffmpeg, off-screen and at
  any `--size` (for example 1080x1920 for vertical video). `--preset readme|reddit|reel|wide`
  sets the size, length, warm-up and panel for common destinations.
- A redesigned evolution panel: a strip along the bottom, and on `I` a timeline of
  every gene and the largest families over the last ten minutes. Full gene names,
  a legend, and sizes that scale with the window.
- A controls card on `H`, grouped by View, World and Make.
- Bundled Inter and JetBrains Mono fonts (SIL Open Font License), so the panels
  look the same on Windows, macOS and Linux.
- GPU black holes (moderngl): an N-body `particle` accretion disk, with a live
  tuning panel on `G`. The 2D look remains as `classic` (`--classic`
  or the `M` key) and is used automatically when OpenGL 3.3 is not available.
- Headless test suite, CI on Linux, Windows and macOS, pre-commit hooks,
  Dependabot and a `uv.lock`.

### Changed
- Tuned for projection: a brighter galaxy background (more stars, stronger
  nebula colours) and motion about 1.45x faster than the original 1080p pace.
- Installable package (`pip install .`) with a `src/` layout.
- A busier start: 400 stars and 2 black holes, so selection is visible within
  a minute. `--kiosk` keeps the exhibition's sparse start (50 stars, 1 black hole)
  that builds up over about three hours.
- A plain launch opens a window at 80% of the screen; `--fullscreen` or `F` for
  fullscreen. The primary monitor is the default; `--display auto` picks a projector.
- The FPS status line is gone, and the visitor hint and clock only appear with
  `--kiosk`, which now also starts fullscreen.
- `S` saves the finished frame without panels, instead of the trail layer alone.
- Recordings leave the panels out unless `--panel` asks for them.
- Every panel shrinks to fit small windows.
- Fortress and defensive cohesion are vectorised (about 25% faster in dense scenes).

### Fixed
- Keys and help text described `[` as adding a black hole; `]` adds, `[` removes.
- The evolution panel froze after a reset.
- The simulation kept its old size after toggling fullscreen or resizing.
- The flee speed boost only considered the first black hole.
- Disabling evolution in `config.py` crashed the simulation.
- An invalid `SP_DISPLAY` value crashed with a traceback.
