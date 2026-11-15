"""
SELECTION PRESSURE - application loop.

Owns the window, input handling and the per-frame pipeline:
simulate -> draw into the persistent trail surface -> composite -> overlays.
Simulation logic lives in ``simulation.py``; drawing in ``rendering.py`` and
``hud.py``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import pygame

from . import background, config, display, hud, rendering
from .simulation import BlackHolePredator, BoidsSimulation

MAX_BLACK_HOLES = 3
MIN_BLACK_HOLES = 1
MAX_STARS = 2000
MIN_STARS = 10
STAR_STEP = 50
HELP_DISPLAY_SECS = 5   # help overlay stays fully visible this long
HELP_FADE_SPEED = 3     # alpha lost per frame while fading out
COLOR_CYCLE_SECS = 30   # palette cycle length used by the boid colouring


@dataclass
class Options:
    """Runtime options, normally built by ``cli.parse_args``."""

    display: str = "primary"
    windowed: bool = False
    window_size: tuple[int, int] | None = None
    seed: int = config.SEED
    stars: int = config.NUM_BOIDS
    black_holes: int = config.NUM_BLACK_HOLES
    fps: int = config.TARGET_FPS
    frames: int | None = None
    show_hud: bool = True
    kiosk: bool = False
    profile: bool = False
    screenshot_dir: Path = Path(".")


# ============================================================
# Factories
# ============================================================

def make_sim(width, height, num_stars=None, seed=None):
    """Create a BoidsSimulation using the current config toggles."""
    sim = BoidsSimulation(
        config.NUM_BOIDS if num_stars is None else num_stars,
        width, height, config.SEED if seed is None else seed)
    sim.params.attractor_enabled = config.ATTRACTOR_ENABLED
    sim.params.noise_influence = config.NOISE_INFLUENCE
    return sim


def _spawn_point(index, width, height):
    corners = [(0.25, 0.25), (0.75, 0.75), (0.75, 0.25), (0.25, 0.75)]
    fx, fy = corners[index % len(corners)]
    return width * fx, height * fy


def make_predator(index, width, height):
    """Create the ``index``-th black hole at its fixed spawn corner."""
    return BlackHolePredator(width, height,
                             start_pos=_spawn_point(index, width, height),
                             seed=123 + index)


def make_predators(width, height, count=None):
    """Create ``count`` black holes (config default when None)."""
    count = config.NUM_BLACK_HOLES if count is None else count
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
        print(f"\n  [PROFILE] avg over {self._count} frames "
              f"({total / self._count * 1000:.1f} ms/frame):")
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
        pygame.display.set_caption("SELECTION PRESSURE [SPACE=pause, R=reset, H=help]")
        self.clock = pygame.time.Clock()

        self.font_hud = pygame.font.SysFont("consolas", 20)
        self.font_title = pygame.font.SysFont("consolas", 28, bold=True)
        self.lens_maps = rendering.precompute_lens_maps()

        self._create_surfaces()
        self.reset()

        self.running = True
        self.paused = False
        self.screenshot_count = 0
        self.show_help = True
        self.help_alpha = 255
        self.help_auto_fade = True

    # ---- window and surfaces ------------------------------------------

    def _open_window(self):
        monitors = display.list_monitors()
        index = display.choose_display(monitors, self.opts.display)
        self.monitor = monitors[index]
        x, y, w, h = self.monitor
        print(f"  Display [{index}] {w}x{h} at ({x},{y}) "
              f"of {len(monitors)} monitor(s)")

        if self.opts.windowed:
            self.fullscreen = False
            size = self.opts.window_size or (int(w * 0.8), int(h * 0.8))
            display.place_window(x + (w - size[0]) // 2, y + (h - size[1]) // 2)
            return pygame.display.set_mode(size, pygame.RESIZABLE)

        # Borderless window covering the monitor: unlike exclusive
        # fullscreen it stays visible when another screen has focus.
        self.fullscreen = True
        display.place_window(x, y)
        return pygame.display.set_mode((w, h), pygame.NOFRAME)

    @property
    def size(self):
        return self.screen.get_size()

    def _create_surfaces(self):
        w, h = self.size
        self.trail_surface = pygame.Surface((w, h))
        self.trail_surface.fill((0, 0, 0))
        self.boid_layer = pygame.Surface((w, h))
        self.boid_layer.set_colorkey((0, 0, 0))

        self.galaxy_bg = self.twinkle_data = self.twinkle_overlay = None
        if config.GALAXY_BG_ENABLED:
            self.galaxy_bg, self.twinkle_data = background.generate_galaxy_background(
                w, h, seed=self.seed)
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

    def toggle_fullscreen(self):
        x, y, w, h = self.monitor
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            display.place_window(x, y)
            self.screen = pygame.display.set_mode((w, h), pygame.NOFRAME)
        else:
            self.screen = pygame.display.set_mode(
                (int(w * 0.8), int(h * 0.8)), pygame.RESIZABLE)
        self._on_resize()

    def _on_resize(self):
        w, h = self.size
        self._create_surfaces()
        self.sim.resize(w, h)
        for pred in self.predators:
            pred.resize(w, h)
        print(f"  [DISPLAY] {w}x{h} {'fullscreen' if self.fullscreen else 'windowed'}")

    # ---- input --------------------------------------------------------

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.VIDEORESIZE and not self.fullscreen:
            self.screen = pygame.display.get_surface()
            self._on_resize()
        elif event.type == pygame.KEYDOWN:
            self.handle_key(event.key)

    def handle_key(self, key):
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
            self.help_alpha = 255
            self.help_auto_fade = False
        elif key == pygame.K_s:
            self.save_screenshot()
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

    def toggle_pause(self):
        self.paused = not self.paused
        if self.paused:
            self.wall_pause_begin = time.monotonic()
        elif self.wall_pause_begin is not None:
            self.wall_paused_total += time.monotonic() - self.wall_pause_begin
            self.wall_pause_begin = None
        print(f"  [{'PAUSED' if self.paused else 'RUNNING'}]")

    def add_black_hole(self):
        if config.BLACK_HOLE_ENABLED and len(self.predators) < MAX_BLACK_HOLES:
            self.predators.append(make_predator(len(self.predators), *self.size))
        print(f"  [BLACK HOLES] {len(self.predators)}")

    def remove_black_hole(self):
        if len(self.predators) > MIN_BLACK_HOLES:
            self.predators.pop()
        print(f"  [BLACK HOLES] {len(self.predators)}")

    def save_screenshot(self):
        """Save the trail layer (the artwork without overlays) as a PNG."""
        out_dir = self.opts.screenshot_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        while True:
            self.screenshot_count += 1
            path = out_dir / f"sp_screenshot_{self.screenshot_count:03d}.png"
            if not path.exists():
                break
        pygame.image.save(self.trail_surface, str(path))
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
        self.frame += 1

    def draw(self):
        """Render one frame onto the screen."""
        screen, trail, prof = self.screen, self.trail_surface, self.prof
        sim, predators, frame = self.sim, self.predators, self.frame

        prof.begin("fade_trails")
        rendering.fade_trails(trail)
        prof.end()

        prof.begin("draw_boids")
        if not self.paused or frame == 0:
            rendering.draw_boids(self.boid_layer, trail, sim, frame,
                                 config.TARGET_FPS * COLOR_CYCLE_SECS, predators)
        prof.end()

        prof.begin("draw_black_holes")
        rendering.draw_black_holes(trail, predators, frame)
        prof.end()

        if config.EVOLUTION_ENABLED and sim.birth_flashes:
            rendering.draw_birth_flashes(trail, sim.birth_flashes)
        if self.predator_explosions:
            rendering.draw_predator_explosions(trail, self.predator_explosions)

        prof.begin("composite_display")
        rendering.composite_display(screen, trail, self.galaxy_bg, self.twinkle_overlay,
                                    self.twinkle_data, frame)
        prof.end()

        if config.NEBULA_FIELDS_ENABLED and sim.nebula is not None:
            rendering.draw_nebula_clouds(screen, sim.nebula, frame)
        rendering.stamp_void_on_screen(screen, predators)

        prof.begin("apply_bloom")
        rendering.apply_bloom(screen, trail)
        prof.end()

        prof.begin("apply_lensing")
        rendering.apply_lensing(screen, predators, self.lens_maps)
        prof.end()

        prof.begin("overlays")
        self._draw_overlays()
        prof.end()

    def _draw_overlays(self):
        screen, sim = self.screen, self.sim
        if self.opts.show_hud:
            hud.render_hud(screen, self.font_hud, sim, self.frame, self.predators,
                           self.clock.get_fps())
            hud.render_elapsed_time(screen, self.elapsed_seconds())
            hud.render_participant_hint(screen)
        if config.EVOLUTION_ENABLED:
            hud.render_evolution_panel(screen, self.font_title, self.font_hud, sim,
                                       self.frame, predators=self.predators,
                                       starvation_events_total=self.starvation_total)
        if self.show_help and self.help_alpha > 0:
            w, h = self.size
            hud.draw_help_overlay(screen, self.help_alpha, self.font_title, self.font_hud,
                                  w, h, sim.num, len(self.predators))

        # Startup help fades out on its own after a few seconds.
        if self.help_auto_fade and self.show_help and \
                self.frame > HELP_DISPLAY_SECS * config.TARGET_FPS:
            self.help_alpha = max(0, self.help_alpha - HELP_FADE_SPEED)
            if self.help_alpha <= 0:
                self.show_help = self.help_auto_fade = False

    def run(self):
        """Main loop.  Returns when the window closes or ``frames`` is reached."""
        w, h = self.size
        print(f"\n  SELECTION PRESSURE  {w}x{h}, {self.sim.num} stars, seed {self.seed}")
        print("  ESC/Q quit  SPACE pause  R reset  F fullscreen  S screenshot  H help\n")
        frames_left = self.opts.frames
        while self.running:
            for event in pygame.event.get():
                self.handle_event(event)

            self.prof.begin("simulation")
            self.step()
            self.prof.end()
            self.draw()

            pygame.display.flip()
            self.clock.tick(self.opts.fps)
            self.prof.tick()

            if frames_left is not None:
                frames_left -= 1
                if frames_left <= 0:
                    self.running = False


def run(options: Options) -> None:
    """Initialise pygame, run the installation and shut down cleanly."""
    display.enable_dpi_awareness()
    pygame.init()
    try:
        App(options).run()
    finally:
        pygame.quit()
