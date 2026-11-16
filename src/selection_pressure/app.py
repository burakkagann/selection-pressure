"""
SELECTION PRESSURE - application loop.

Owns the window, input handling and the per-frame pipeline:
simulate -> draw into the persistent trail surface -> composite -> overlays.
Simulation logic lives in ``simulation.py``; drawing in ``rendering.py`` and
``hud.py``.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

import pygame

from . import background, blackhole_gl, config, display, hud, rendering, ui
from .history import EvolutionHistory
from .recorder import Recorder
from .simulation import BlackHolePredator, BoidsSimulation
from .tuning import TuningPanel

MAX_BLACK_HOLES = 3
MIN_BLACK_HOLES = 1
MAX_STARS = 2000
MIN_STARS = 10
STAR_STEP = 50
START_HINT_SECS = 6  # the 'I panel  H controls' hint shows this long, then fades
START_HINT_FADE_SECS = 1.5
COLOR_CYCLE_SECS = 30  # palette cycle length used by the boid colouring
RECORD_SIZE = (1920, 1080)  # --record without an explicit --size
BLACK_HOLE_STYLES = (*blackhole_gl.STYLES, "classic")
PANELS = ("strip", "full", "off")  # the order I cycles through


@dataclass
class Options:
    """Runtime options, normally built by ``cli.parse_args``."""

    display: str = "primary"
    fullscreen: bool = False  # borderless fullscreen instead of a window
    window_size: tuple[int, int] | None = None  # window or recording size
    seed: int = config.SEED
    stars: int = config.NUM_BOIDS
    black_holes: int = config.NUM_BLACK_HOLES
    black_hole_style: str = config.BLACK_HOLE_STYLE  # particle or classic
    panel: str = "strip"  # evolution panel at start: strip, full or off
    panel_scale: float = 1.0  # larger panels for clips that get scaled down
    frames: int | None = None
    kiosk: bool = False  # exhibition: no start hint; visitor hint and clock on
    profile: bool = False
    screenshot_dir: Path = Path(".")
    record: Path | None = None  # render offline to this .mp4 / .gif and exit
    record_seconds: float = 15.0
    warmup_seconds: float = 0.0


# ============================================================
# Factories
# ============================================================


def make_sim(width, height, num_stars=None, seed=None):
    """Create a BoidsSimulation using the current config toggles."""
    sim = BoidsSimulation(
        config.NUM_BOIDS if num_stars is None else num_stars,
        width,
        height,
        config.SEED if seed is None else seed,
    )
    sim.params.attractor_enabled = config.ATTRACTOR_ENABLED
    sim.params.noise_influence = config.NOISE_INFLUENCE
    return sim


def _spawn_point(index, width, height):
    corners = [(0.25, 0.25), (0.75, 0.75), (0.75, 0.25), (0.25, 0.75)]
    fx, fy = corners[index % len(corners)]
    return width * fx, height * fy


def make_predator(index, width, height):
    """Create the ``index``-th black hole at its fixed spawn corner."""
    return BlackHolePredator(
        width, height, start_pos=_spawn_point(index, width, height), seed=123 + index
    )


def make_predators(width, height, count=None):
    """Create ``count`` black holes (config default when None)."""
    count = min(config.NUM_BLACK_HOLES if count is None else count, MAX_BLACK_HOLES)
    if not config.BLACK_HOLE_ENABLED or count <= 0:
        return []
    return [make_predator(i, width, height) for i in range(count)]


# ============================================================
# Profiler
# ============================================================


class FrameProfiler:
    """Per-section frame timing, printed every ``interval`` frames."""

    def __init__(self, enabled, interval=120):
        self.enabled = enabled
        self._interval = interval
        self._timings = {}
        self._count = 0
        self._label = ""
        self._t0 = 0.0

    def begin(self, label):
        if self.enabled:
            self._label = label
            self._t0 = time.perf_counter()

    def end(self):
        if self.enabled:
            dt = time.perf_counter() - self._t0
            self._timings[self._label] = self._timings.get(self._label, 0.0) + dt

    def tick(self):
        if not self.enabled:
            return
        self._count += 1
        if self._count < self._interval:
            return
        total = sum(self._timings.values())
        print(
            f"\n  [PROFILE] avg over {self._count} frames "
            f"({total / self._count * 1000:.1f} ms/frame):"
        )
        for label, t in sorted(self._timings.items(), key=lambda x: -x[1]):
            pct = t / total * 100 if total > 0 else 0
            print(f"    {label:<24} {t / self._count * 1000:6.2f} ms  ({pct:4.1f}%)")
        self._timings.clear()
        self._count = 0


# ============================================================
# Application
# ============================================================


class App:
    """The running installation: window, world state and frame loop."""

    def __init__(self, options: Options):
        self.opts = options
        self.seed = options.seed
        self.initial_stars = options.stars
        self.initial_black_holes = options.black_holes
        self.prof = FrameProfiler(options.profile)

        if options.kiosk:
            display.minimize_console()
        self.screen = self._open_window()
        pygame.display.set_caption("Selection Pressure  (H for controls)")
        self.clock = pygame.time.Clock()

        self.ui = ui.UI(self.size[1], options.panel_scale)
        self.hud = hud.Hud(self.ui)
        self.history = EvolutionHistory()
        self.panel = options.panel if options.panel in PANELS else "strip"
        self.lens_maps = rendering.precompute_lens_maps()

        # GPU black holes: created on first use, rebuilt when the size changes.
        self.bh_style = options.black_hole_style
        self.gpu = None
        self.gpu_error = None
        self.tuning = TuningPanel(on_style_click=self.cycle_black_hole_style)

        self._create_surfaces()
        self.reset()

        self.running = True
        self.paused = False
        self.screenshot_count = 0
        self.screenshot_requested = False
        self.show_help = False
        self.started = time.monotonic()
        self.show_start_hint = not options.kiosk and options.record is None

    # ---- window and surfaces ------------------------------------------

    def _open_window(self):
        monitors = display.list_monitors()
        index = display.choose_display(monitors, self.opts.display)
        self.monitor = monitors[index]
        x, y, w, h = self.monitor
        print(f"  Display [{index}] {w}x{h} at ({x},{y}) of {len(monitors)} monitor(s)")

        if self.opts.record is not None:
            # Recording renders off-screen (see run()), so any size works.
            self.fullscreen = False
            return pygame.display.set_mode(self.opts.window_size or RECORD_SIZE)

        if self.opts.fullscreen:
            # Borderless window covering the monitor: unlike exclusive
            # fullscreen it stays visible when another screen has focus.
            self.fullscreen = True
            display.place_window(x, y)
            return pygame.display.set_mode((w, h), pygame.NOFRAME)

        self.fullscreen = False
        size = self.opts.window_size or (int(w * 0.8), int(h * 0.8))
        display.place_window(x + (w - size[0]) // 2, y + (h - size[1]) // 2)
        return pygame.display.set_mode(size, pygame.RESIZABLE)

    @property
    def size(self):
        return self.screen.get_size()

    def _create_surfaces(self):
        w, h = self.size
        self._release_gpu()
        self.ui.resize(h)
        self.hud.invalidate()
        self.trail_surface = pygame.Surface((w, h))
        self.trail_surface.fill((0, 0, 0))
        self.boid_layer = pygame.Surface((w, h))
        self.boid_layer.set_colorkey((0, 0, 0))

        self.galaxy_bg = self.twinkle_data = self.twinkle_overlay = None
        if config.GALAXY_BG_ENABLED:
            self.galaxy_bg, self.twinkle_data = background.generate_galaxy_background(
                w, h, seed=self.seed
            )
            if config.TWINKLE_ENABLED and self.twinkle_data:
                self.twinkle_overlay = pygame.Surface((w, h))
                self.twinkle_overlay.set_colorkey((0, 0, 0))

    def reset(self):
        """Restart the world with the initial star and black hole counts."""
        w, h = self.size
        self.sim = make_sim(w, h, self.initial_stars, self.seed)
        self.predators = make_predators(w, h, self.initial_black_holes)
        self.trail_surface.fill((0, 0, 0))
        self.frame = 0
        self.wall_start = time.monotonic()
        self.wall_paused_total = 0.0
        self.wall_pause_begin = None
        self.predator_explosions = []
        self.starvation_total = 0
        self.history.clear()
        self.hud.invalidate()

    def toggle_fullscreen(self):
        x, y, w, h = self.monitor
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            display.place_window(x, y)
            self.screen = pygame.display.set_mode((w, h), pygame.NOFRAME)
        else:
            self.screen = pygame.display.set_mode((int(w * 0.8), int(h * 0.8)), pygame.RESIZABLE)
        self._on_resize()

    def _on_resize(self):
        w, h = self.size
        self._create_surfaces()
        self.sim.resize(w, h)
        for pred in self.predators:
            pred.resize(w, h)
        print(f"  [DISPLAY] {w}x{h} {'fullscreen' if self.fullscreen else 'windowed'}")

    # ---- GPU black holes -----------------------------------------------

    def _gpu_ready(self):
        """True when the current style is drawn by a working GPU renderer."""
        if self.bh_style not in blackhole_gl.STYLES or self.gpu_error:
            return False
        if self.gpu is None:
            self.gpu = blackhole_gl.ShaderBlackHole(*self.size)
            if not self.gpu.available:
                self.gpu_error = self.gpu.error
                self.gpu = None
                self.bh_style = "classic"
                print(f"  [BLACK HOLES] GPU style unavailable, using 'classic': {self.gpu_error}")
                return False
            print(f"  [BLACK HOLES] style '{self.bh_style}' on {self.gpu.renderer_name}")
        return True

    def _release_gpu(self):
        if self.gpu is not None:
            self.gpu.close()
            self.gpu = None

    def cycle_black_hole_style(self):
        """Switch to the next black hole style (the GPU style is skipped without a GPU)."""
        styles = BLACK_HOLE_STYLES if not self.gpu_error else ("classic",)
        index = styles.index(self.bh_style) if self.bh_style in styles else -1
        self.bh_style = styles[(index + 1) % len(styles)]
        print(f"  [BLACK HOLES] style '{self.bh_style}'")

    def close(self):
        self._release_gpu()

    # ---- input --------------------------------------------------------

    def handle_event(self, event):
        if self.tuning.handle_event(event):
            return
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.VIDEORESIZE and not self.fullscreen:
            self.screen = pygame.display.get_surface()
            self._on_resize()
        elif event.type == pygame.KEYDOWN:
            self.handle_key(event.key)

    def handle_key(self, key):
        self.hud.invalidate()  # panels show the change at once, even when paused
        if key in (pygame.K_ESCAPE, pygame.K_q):
            self.running = False
        elif key == pygame.K_SPACE:
            self.toggle_pause()
        elif key == pygame.K_r:
            self.reset()
            print(f"  [RESET] {self.sim.num} stars, seed={self.seed}")
        elif key == pygame.K_f:
            self.toggle_fullscreen()
        elif key == pygame.K_h:
            self.show_help = not self.show_help
            self.show_start_hint = False
        elif key == pygame.K_i:
            self.cycle_panel()
        elif key == pygame.K_s:
            self.screenshot_requested = True  # saved by draw(), before the panels
        elif key == pygame.K_RIGHTBRACKET:
            self.add_black_hole()
        elif key == pygame.K_LEFTBRACKET:
            self.remove_black_hole()
        elif key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            add = min(STAR_STEP, MAX_STARS - self.sim.num)
            if add > 0:
                self.sim.add_boids(add, self.frame)
            print(f"  [STARS] {self.sim.num}")
        elif key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.sim.remove_boids(min(STAR_STEP, self.sim.num - MIN_STARS))
            print(f"  [STARS] {self.sim.num}")
        elif key == pygame.K_m:
            self.cycle_black_hole_style()
        elif key == pygame.K_g:
            self.tuning.toggle()
            if self.tuning.visible:
                self.show_help = False
        elif key == pygame.K_d and self.tuning.visible:
            self.tuning.dump(self.bh_style)

    def toggle_pause(self):
        self.paused = not self.paused
        if self.paused:
            self.wall_pause_begin = time.monotonic()
        elif self.wall_pause_begin is not None:
            self.wall_paused_total += time.monotonic() - self.wall_pause_begin
            self.wall_pause_begin = None
        print(f"  [{'PAUSED' if self.paused else 'RUNNING'}]")

    def cycle_panel(self):
        """I: strip -> timeline -> off."""
        self.panel = PANELS[(PANELS.index(self.panel) + 1) % len(PANELS)]
        self.show_start_hint = False

    def add_black_hole(self):
        if config.BLACK_HOLE_ENABLED and len(self.predators) < MAX_BLACK_HOLES:
            self.predators.append(make_predator(len(self.predators), *self.size))
        print(f"  [BLACK HOLES] {len(self.predators)}")

    def remove_black_hole(self):
        if len(self.predators) > MIN_BLACK_HOLES:
            self.predators.pop()
        print(f"  [BLACK HOLES] {len(self.predators)}")

    def save_screenshot(self, surface=None):
        """Save ``surface`` (the screen by default) as a numbered PNG.

        The S key saves from inside :meth:`draw`, after the artwork is
        composed and before any panel is drawn on top.
        """
        surface = self.screen if surface is None else surface
        out_dir = self.opts.screenshot_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        while True:
            self.screenshot_count += 1
            path = out_dir / f"sp_screenshot_{self.screenshot_count:03d}.png"
            if not path.exists():
                break
        pygame.image.save(surface, str(path))
        print(f"  [SAVED] {path}")

    # ---- frame --------------------------------------------------------

    def elapsed_seconds(self):
        """Wall-clock time since the last reset, excluding pauses."""
        now = time.monotonic()
        paused_now = now - self.wall_pause_begin if self.wall_pause_begin else 0.0
        return now - self.wall_start - self.wall_paused_total - paused_now

    def step(self):
        """Advance the simulation by one frame (no-op while paused)."""
        if self.paused:
            return
        predators = self.predators if config.BLACK_HOLE_ENABLED else []
        for pred in predators:
            pred.step(self.sim.positions, [p for p in predators if p is not pred])
        self.sim.step(self.frame, predators or None)

        if predators and config.PREDATOR_EVOLUTION_ENABLED:
            explosions = self.sim.check_predator_starvation(predators, self.frame)
            self.predator_explosions.extend(explosions)
            self.starvation_total += len(explosions)
        self.history.maybe_sample(self.sim, self.frame)
        self.frame += 1

    def draw(self):
        """Render one frame onto the screen."""
        screen, trail, prof = self.screen, self.trail_surface, self.prof
        sim, predators, frame = self.sim, self.predators, self.frame
        # The GPU style owns the black hole visual; the 2D predator stages are skipped.
        gpu = self._gpu_ready()

        prof.begin("fade_trails")
        rendering.fade_trails(trail)
        prof.end()

        prof.begin("draw_boids")
        if not self.paused or frame == 0:
            rendering.draw_boids(
                self.boid_layer, trail, sim, frame, config.TARGET_FPS * COLOR_CYCLE_SECS, predators
            )
        prof.end()

        if not gpu:
            prof.begin("draw_black_holes")
            rendering.draw_black_holes(trail, predators, frame)
            prof.end()

        if config.EVOLUTION_ENABLED and sim.birth_flashes:
            rendering.draw_birth_flashes(trail, sim.birth_flashes)
        if gpu:
            self.predator_explosions.clear()
        elif self.predator_explosions:
            rendering.draw_predator_explosions(trail, self.predator_explosions)

        prof.begin("composite_display")
        rendering.composite_display(
            screen, trail, self.galaxy_bg, self.twinkle_overlay, self.twinkle_data, frame
        )
        prof.end()

        if config.NEBULA_FIELDS_ENABLED and sim.nebula is not None:
            rendering.draw_nebula_clouds(screen, sim.nebula, frame)
        if not gpu:
            rendering.stamp_void_on_screen(screen, predators)

        prof.begin("apply_bloom")
        rendering.apply_bloom(screen, trail)
        prof.end()

        if gpu:
            prof.begin("gpu_black_holes")
            self.gpu.render(screen, predators, frame)
        else:
            prof.begin("apply_lensing")
            rendering.apply_lensing(screen, predators, self.lens_maps)
        prof.end()

        if self.screenshot_requested:
            self.screenshot_requested = False
            self.save_screenshot(screen)

        prof.begin("overlays")
        self._draw_overlays()
        prof.end()

    def _draw_overlays(self):
        screen, h = self.screen, self.hud
        bottom = screen.get_height() - self.ui.px(24)
        right = None  # right edge for the start hint
        if config.EVOLUTION_ENABLED and self.panel != "off":
            args = (screen, self.sim, self.predators, self.starvation_total)
            if self.panel == "strip":
                bottom = h.draw_strip(*args, self.frame).top - self.ui.px(12)
            else:
                right = h.draw_timeline(*args, self.history, self.frame).left - self.ui.px(16)

        if self.opts.kiosk:
            h.draw_visitor_hint(screen, bottom)
            h.draw_clock(screen, self.elapsed_seconds(), bottom)
        elif self.show_start_hint:
            age = time.monotonic() - self.started
            alpha = 255 * min(
                1.0, (START_HINT_SECS + START_HINT_FADE_SECS - age) / START_HINT_FADE_SECS
            )
            if alpha <= 0:
                self.show_start_hint = False
            else:
                h.draw_start_hint(screen, int(alpha), bottom, right)

        if self.show_help:
            h.draw_help(screen)
        note = "GPU unavailable: see console" if self.gpu_error else ""
        self.tuning.draw(screen, self.bh_style, self.ui, note)

    def record(self):
        """Render ``record_seconds`` of video offline, after an optional warm-up.

        Frames are produced as fast as possible and encoded at ``fps``, so the
        result is smooth even on a machine that cannot render in real time.
        """
        fps = config.TARGET_FPS
        warmup = int(self.opts.warmup_seconds * fps)
        total = int(self.opts.record_seconds * fps)
        self.show_help = self.show_start_hint = False
        if warmup:
            print(f"  Warming up for {warmup} frames...")
            for i in range(warmup):
                pygame.event.pump()
                self.step()
                if i >= warmup - 3 * fps:  # trails need only the last few seconds
                    self.draw()
        recorder = Recorder(self.opts.record, self.size, fps)
        print(f"  Recording {total} frames to {self.opts.record}")
        try:
            for i in range(total):
                pygame.event.pump()
                self.step()
                self.draw()
                pygame.display.flip()
                recorder.write(self.screen)
                if (i + 1) % fps == 0:
                    print(f"    {(i + 1) // fps}/{total // fps} s")
        finally:
            recorder.close()
        print(f"  Saved {recorder.frames} frames to {self.opts.record}")

    def run(self):
        """Main loop.  Returns when the window closes or ``frames`` is reached."""
        if self.opts.record is not None:
            self.record()
            return
        w, h = self.size
        print(f"\n  SELECTION PRESSURE  {w}x{h}, {self.sim.num} stars, seed {self.seed}")
        print("  H controls  I evolution panel  ESC quit\n")
        frames_left = self.opts.frames
        while self.running:
            for event in pygame.event.get():
                self.handle_event(event)

            self.prof.begin("simulation")
            self.step()
            self.prof.end()
            self.draw()

            pygame.display.flip()
            self.clock.tick(config.TARGET_FPS)
            self.prof.tick()

            if frames_left is not None:
                frames_left -= 1
                if frames_left <= 0:
                    self.running = False


def run(options: Options) -> None:
    """Initialise pygame, run the installation and shut down cleanly."""
    display.enable_dpi_awareness()
    if options.record is not None:
        # No visible window: the clip can be larger than the monitor, e.g. a
        # 1080x1920 portrait video on a landscape screen.
        os.environ["SDL_VIDEODRIVER"] = "dummy"
    pygame.init()
    try:
        app = App(options)
        try:
            app.run()
        finally:
            app.close()
    finally:
        pygame.quit()
