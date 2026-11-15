# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.0] - Unreleased

First packaged release.

### Added
- `selection-pressure` command with options for display, window size, seed,
  population, frame limit, profiling, kiosk mode and screenshot folder.
- `--record` renders MP4 or GIF clips offline through ffmpeg.
- Headless test suite, CI on Linux, Windows and macOS, pre-commit hooks,
  Dependabot and a `uv.lock`.

### Changed
- Installable package (`pip install .`) with a `src/` layout.
- The primary monitor is the default; `--display auto` picks a projector.
- The evolution panel shrinks to fit small windows.
- Fortress and defensive cohesion are vectorised (about 25% faster in dense scenes).

### Fixed
- The evolution panel froze after a reset.
- The simulation kept its old size after toggling fullscreen or resizing.
- The flee speed boost only considered the first black hole.
- Disabling evolution in `config.py` crashed the simulation.
- An invalid `SP_DISPLAY` value crashed with a traceback.
