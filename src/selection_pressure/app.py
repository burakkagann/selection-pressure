"""
SELECTION PRESSURE - Galaxy Simulation (pygame)

Live galaxy simulation with evolving stars and black holes.
Exhibition installation with real-time evolutionary dynamics.

Controls:
    ESC / Q         Quit
    SPACE           Pause / resume simulation
    R               Reset simulation with current seed
    S               Save current frame as PNG
    F               Toggle fullscreen
    H               Toggle help overlay
    +/-             Adjust number of stars (+/- 50)
    [ / ]           Remove / add black hole (1-3)

Author: Burak Kagan (Pixels2GenAI Project)
Date: 2026-02-19
"""

import sys
import os
import time
import ctypes
import numpy as np

# --- Windows DPI Awareness (MUST run before pygame.init) ---
# Without this, Windows scales coordinates and pygame gets logical pixels
# instead of physical pixels, causing fullscreen/projector mismatches.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # 2 = per-monitor aware
except (AttributeError, OSError):
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # fallback for older Windows
    except (AttributeError, OSError):
        pass

# Hide the console window to prevent it from stealing focus during exhibition
try:
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 6)  # 6 = SW_MINIMIZE
except (AttributeError, OSError):
    pass

try:
    import pygame
except ImportError:
    print("ERROR: pygame not found. Install with: pip install pygame")
    sys.exit(1)

from . import background, config, rendering
from .simulation import BlackHolePredator, BoidsSimulation



# ============================================================
# FRAME PROFILER
# ============================================================

class FrameProfiler:
    """Lightweight per-frame timing that prints summaries periodically."""
    __slots__ = ('_timings', '_count', '_t0', '_label', '_interval')

    def __init__(self, interval=120):
        self._timings = {}
        self._count = 0
        self._t0 = 0.0
        self._label = ''
        self._interval = interval

    def begin(self, label):
        self._label = label
        self._t0 = time.perf_counter()

    def end(self):
        dt = time.perf_counter() - self._t0
        self._timings[self._label] = (
            self._timings.get(self._label, 0.0) + dt)

    def tick(self):
        """Call once per frame.  Prints and resets every _interval frames."""
        self._count += 1
        if self._count < self._interval:
            return
        total = sum(self._timings.values())
        n = self._count
        print(f"\n  [PROFILE] avg over {n} frames "
              f"({total / n * 1000:.1f} ms/frame):")
        for label, t in sorted(
                self._timings.items(), key=lambda x: -x[1]):
            avg = t / n * 1000
            pct = t / total * 100 if total > 0 else 0
            print(f"    {label:<24} {avg:6.2f} ms  ({pct:4.1f}%)")
        print()
        self._timings.clear()
        self._count = 0


# ============================================================
# HELPERS
# ============================================================

def make_sim():
    """Create a BoidsSimulation reflecting current config toggle state."""
    sim = BoidsSimulation(
        config.NUM_BOIDS, config.WIDTH, config.HEIGHT, config.SEED)
    # Sync runtime-toggled params that may differ from class defaults
    sim.params.attractor_enabled = config.ATTRACTOR_ENABLED
    sim.params.noise_influence = config.NOISE_INFLUENCE
    return sim


def make_predators():
    """Spawn predators at evenly spaced corner positions."""
    if not config.BLACK_HOLE_ENABLED or config.NUM_BLACK_HOLES <= 0:
        return []
    corners = [
        (config.WIDTH * 0.25, config.HEIGHT * 0.25),
        (config.WIDTH * 0.75, config.HEIGHT * 0.75),
        (config.WIDTH * 0.75, config.HEIGHT * 0.25),
        (config.WIDTH * 0.25, config.HEIGHT * 0.75),
    ]
    preds = []
    for i in range(config.NUM_BLACK_HOLES):
        pos = corners[i % len(corners)]
        preds.append(BlackHolePredator(
            config.WIDTH, config.HEIGHT, start_pos=pos, seed=123 + i))
    return preds


# ============================================================
# MAIN
# ============================================================

def main():
    pygame.init()

    # ---- Detect monitors with actual pixel positions (Windows API) ----
    # desktop_sizes only gives (w, h) per monitor — no position info.
    # We need the real x,y so we can place the window on the correct screen.
    monitor_rects = []  # list of (x, y, w, h) in physical pixels
    try:
        import ctypes.wintypes
        MONITORENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_bool,
            ctypes.c_ulong, ctypes.c_ulong,
            ctypes.POINTER(ctypes.wintypes.RECT), ctypes.c_double)

        def _enum_cb(hMon, hdc, lprc, data):
            r = lprc.contents
            monitor_rects.append((r.left, r.top,
                                  r.right - r.left, r.bottom - r.top))
            return True

        ctypes.windll.user32.EnumDisplayMonitors(
            None, None, MONITORENUMPROC(_enum_cb), 0)
    except Exception:
        pass

    # Fallback: use pygame sizes at (0,0) if Windows API failed
    if not monitor_rects:
        desktop_sizes = pygame.display.get_desktop_sizes()
        monitor_rects = [(0, 0, w, h) for w, h in desktop_sizes]

    print()
    print(f"  Monitors detected: {len(monitor_rects)}")
    for i, (mx, my, mw, mh) in enumerate(monitor_rects):
        primary = " (primary)" if (mx == 0 and my == 0) else ""
        print(f"    [{i}] {mw}x{mh} at ({mx},{my}){primary}")

    # ---- Choose target display ----
    # SP_DISPLAY env var: 0, 1, 2... to pick explicitly.
    # Default: pick the non-primary monitor (the projector).
    display_override = os.environ.get('SP_DISPLAY')
    if display_override is not None:
        target_display = int(display_override)
    elif len(monitor_rects) > 1:
        # Pick the best projector candidate: non-primary, landscape, largest
        non_primary = [
            (i, mx, my, mw, mh) for i, (mx, my, mw, mh)
            in enumerate(monitor_rects) if mx != 0 or my != 0]
        # Prefer landscape (w >= h), then largest area
        non_primary.sort(key=lambda m: (m[3] >= m[4], m[3] * m[4]),
                         reverse=True)
        target_display = non_primary[0][0] if non_primary else 0
    else:
        target_display = 0

    tx, ty, tw, th = monitor_rects[target_display]
    config.WIDTH = tw
    config.HEIGHT = th
    print(f"  -> Target: display [{target_display}] "
          f"{tw}x{th} at ({tx},{ty})")
    print(f"     (override with: set SP_DISPLAY=0  or  set SP_DISPLAY=1)")
    print()

    # Position SDL window at the target monitor's top-left corner
    os.environ['SDL_VIDEO_WINDOW_POS'] = f"{tx},{ty}"

    # Borderless fullscreen window — stays visible when interacting with other
    # monitors (unlike exclusive FULLSCREEN which minimizes on focus loss).
    # Critical for exhibition: piece on projector + other apps on main screen.
    screen = pygame.display.set_mode((config.WIDTH, config.HEIGHT),
                                     pygame.NOFRAME)
    # Verify actual surface size matches what we asked for
    actual_w, actual_h = screen.get_size()
    if (actual_w, actual_h) != (config.WIDTH, config.HEIGHT):
        print(f"  WARNING: Requested {config.WIDTH}x{config.HEIGHT} "
              f"but got {actual_w}x{actual_h} — adjusting")
        config.WIDTH = actual_w
        config.HEIGHT = actual_h

    pygame.display.set_caption(
        "SELECTION PRESSURE [SPACE=pause, R=reset, H=help]")
    clock = pygame.time.Clock()

    # Cache fonts once (avoids per-frame SysFont overhead)
    font_hud = pygame.font.SysFont('consolas', 20)
    font_help_title = pygame.font.SysFont('consolas', 28, bold=True)
    font_help = pygame.font.SysFont('consolas', 20)

    # The trail surface holds persistent pixel data
    trail_surface = pygame.Surface((config.WIDTH, config.HEIGHT))
    trail_surface.fill((0, 0, 0))

    # Temporary surface for additive boid drawing (cleared each frame)
    boid_layer = pygame.Surface((config.WIDTH, config.HEIGHT))
    boid_layer.set_colorkey((0, 0, 0))  # black = transparent for blit

    sim = make_sim()

    predators = make_predators()

    # Galaxy background (precomputed — zero per-frame rendering cost)
    galaxy_bg = None
    twinkle_data = None
    twinkle_overlay = None
    if config.GALAXY_BG_ENABLED:
        galaxy_bg, twinkle_data = background.generate_galaxy_background(
            config.WIDTH, config.HEIGHT, seed=config.SEED)
        if config.TWINKLE_ENABLED and twinkle_data:
            twinkle_overlay = pygame.Surface((config.WIDTH, config.HEIGHT))
            twinkle_overlay.set_colorkey((0, 0, 0))

    # Precompute gravitational lensing displacement maps
    lens_maps = rendering.precompute_lens_maps()

    # Predator explosion effects (starvation death visuals)
    predator_explosions = []
    predator_starvation_total = 0  # lifetime count for panel display

    running = True
    paused = False
    fullscreen = True
    frame = 0
    wall_start = time.monotonic()
    wall_paused_total = 0.0       # accumulated pause duration
    wall_pause_begin = None       # set when pause starts
    screenshot_count = 0

    # Help overlay state
    show_help = True            # visible on startup
    help_alpha = 255            # current opacity (0-255)
    help_auto_fade = True       # auto-fade after startup display

    HELP_DISPLAY_SECS = 5       # seconds before auto-fade begins
    HELP_FADE_SPEED = 3         # alpha decrease per frame during fade-out

    # Estimate total frames for color cycling (30s default cycle)
    total_frames_est = config.TARGET_FPS * 30

    print()
    print("  SELECTION PRESSURE - Galaxy Simulation")
    print("  ======================================")
    print(f"  Resolution: {config.WIDTH}x{config.HEIGHT}")
    print(f"  Stars: {config.NUM_BOIDS}")
    print()
    print("  Controls:")
    print("    ESC/Q = Quit    SPACE = Pause    R = Reset")
    print("    +/- = Stars     F = Fullscreen   S = Screenshot")
    print("    [/] = BH count  H = Help overlay")
    prof = FrameProfiler(interval=120)  # report every 2s at 60 FPS

    print()

    while running:
        # --- Event handling ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False

                elif event.key == pygame.K_SPACE:
                    paused = not paused
                    if paused:
                        wall_pause_begin = time.monotonic()
                    elif wall_pause_begin is not None:
                        wall_paused_total += time.monotonic() - wall_pause_begin
                        wall_pause_begin = None
                    state = "PAUSED" if paused else "RUNNING"
                    print(f"  [{state}]")

                elif event.key == pygame.K_r:
                    sim = make_sim()
                    predators = make_predators()
                    trail_surface.fill((0, 0, 0))
                    frame = 0
                    wall_start = time.monotonic()
                    wall_paused_total = 0.0
                    wall_pause_begin = None
                    if config.GALAXY_BG_ENABLED:
                        galaxy_bg, twinkle_data = (
                            background.generate_galaxy_background(
                                config.WIDTH, config.HEIGHT,
                                seed=config.SEED))
                    predator_explosions = []
                    predator_starvation_total = 0
                    print(f"  [RESET] {config.NUM_BOIDS} stars,"
                          f" seed={config.SEED}")

                elif event.key == pygame.K_f:
                    fullscreen = not fullscreen
                    if fullscreen:
                        config.WIDTH = tw
                        config.HEIGHT = th
                        os.environ['SDL_VIDEO_WINDOW_POS'] = f"{tx},{ty}"
                        screen = pygame.display.set_mode(
                            (config.WIDTH, config.HEIGHT),
                            pygame.NOFRAME)
                    else:
                        # Windowed at 80% of target resolution
                        win_w = int(tw * 0.8)
                        win_h = int(th * 0.8)
                        screen = pygame.display.set_mode(
                            (win_w, win_h), pygame.RESIZABLE)
                        config.WIDTH, config.HEIGHT = screen.get_size()
                    # Recreate surfaces to match new screen dimensions
                    trail_surface = pygame.Surface(
                        (config.WIDTH, config.HEIGHT))
                    trail_surface.fill((0, 0, 0))
                    boid_layer = pygame.Surface(
                        (config.WIDTH, config.HEIGHT))
                    boid_layer.set_colorkey((0, 0, 0))
                    if config.GALAXY_BG_ENABLED:
                        galaxy_bg, twinkle_data = (
                            background.generate_galaxy_background(
                                config.WIDTH, config.HEIGHT,
                                seed=config.SEED))
                        if config.TWINKLE_ENABLED and twinkle_data:
                            twinkle_overlay = pygame.Surface(
                                (config.WIDTH, config.HEIGHT))
                            twinkle_overlay.set_colorkey((0, 0, 0))
                    print(f"  [DISPLAY] {config.WIDTH}x{config.HEIGHT}"
                          f" {'fullscreen' if fullscreen else 'windowed'}")

                elif event.key == pygame.K_h:
                    show_help = not show_help
                    help_alpha = 255
                    help_auto_fade = False  # manual toggle cancels auto-fade

                elif event.key == pygame.K_s:
                    screenshot_count += 1
                    path = os.path.join(
                        config.SCRIPT_DIR,
                        f"sp_screenshot_{screenshot_count:03d}.png")
                    pygame.image.save(trail_surface, path)
                    print(f"  [SAVED] {path}")

                elif event.key == pygame.K_RIGHTBRACKET:
                    # Add a black hole (max 3)
                    if len(predators) < 3:
                        corners = [
                            (config.WIDTH * 0.25, config.HEIGHT * 0.25),
                            (config.WIDTH * 0.75, config.HEIGHT * 0.75),
                            (config.WIDTH * 0.75, config.HEIGHT * 0.25),
                        ]
                        idx = len(predators)
                        pos = corners[idx % len(corners)]
                        predators.append(BlackHolePredator(
                            config.WIDTH, config.HEIGHT,
                            start_pos=pos, seed=123 + idx))
                        config.NUM_BLACK_HOLES = len(predators)
                    print(f"  [BLACK HOLES] {len(predators)}")

                elif event.key == pygame.K_LEFTBRACKET:
                    # Remove a black hole (min 1)
                    if len(predators) > 1:
                        predators.pop()
                        config.NUM_BLACK_HOLES = len(predators)
                    print(f"  [BLACK HOLES] {len(predators)}")

                elif event.key in (pygame.K_PLUS, pygame.K_EQUALS,
                                   pygame.K_KP_PLUS):
                    add_n = min(50, 2000 - sim.num)
                    if add_n > 0:
                        sim.add_boids(add_n, frame)
                        config.NUM_BOIDS = sim.num
                    print(f"  [STARS] {sim.num}")

                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    remove_n = min(50, sim.num - 10)
                    if remove_n > 0:
                        sim.remove_boids(remove_n)
                        config.NUM_BOIDS = sim.num
                    print(f"  [STARS] {sim.num}")

        # --- Simulation step ---
        prof.begin('simulation')
        if not paused:
            if config.BLACK_HOLE_ENABLED:
                for pred in predators:
                    others = [p for p in predators if p is not pred]
                    pred.step(sim.positions, others, sim=sim)
            sim.step(frame,
                     predators if config.BLACK_HOLE_ENABLED else None)

            # Check predator starvation (after step so kill resets are current)
            if config.BLACK_HOLE_ENABLED and config.PREDATOR_EVOLUTION_ENABLED:
                new_explosions = sim.check_predator_starvation(
                    predators, frame)
                if new_explosions:
                    predator_explosions.extend(new_explosions)
                    predator_starvation_total += len(new_explosions)

            frame += 1
        prof.end()

        # --- Render trails (per-channel fade for color-shifting trails) ---
        prof.begin('fade_trails')
        rendering.fade_trails(trail_surface)
        prof.end()

        # --- Draw boid dots ---
        prof.begin('draw_boids')
        if not paused or frame == 0:
            rendering.draw_boids(
                boid_layer, trail_surface, sim, frame, total_frames_est,
                predators)
        prof.end()

        # --- Black hole visual effects ---
        prof.begin('draw_black_holes')
        rendering.draw_black_holes(trail_surface, predators, frame)
        prof.end()

        # --- Evolution birth flashes (cyan ring at respawn points) ---
        if config.EVOLUTION_ENABLED and sim.birth_flashes:
            rendering.draw_birth_flashes(trail_surface, sim.birth_flashes)

        # --- Predator explosion effects (starvation death visuals) ---
        if predator_explosions:
            rendering.draw_predator_explosions(
                trail_surface, predator_explosions)

        # --- Display compositing ---
        prof.begin('composite_display')
        rendering.composite_display(
            screen, trail_surface, galaxy_bg, twinkle_overlay,
            twinkle_data, frame)
        prof.end()

        # --- Nebula resource clouds (behind trails, above galaxy BG) ---
        if config.NEBULA_FIELDS_ENABLED and sim.nebula is not None:
            rendering.draw_nebula_clouds(screen, sim.nebula, frame)

        # --- Black hole void (opaque on final screen) ---
        rendering.stamp_void_on_screen(screen, predators)

        # --- Bloom ---
        prof.begin('apply_bloom')
        rendering.apply_bloom(screen, trail_surface)
        prof.end()

        # --- Gravitational lensing ---
        prof.begin('apply_lensing')
        rendering.apply_lensing(screen, predators, lens_maps)
        prof.end()

        # --- HUD ---
        prof.begin('hud_and_overlays')
        actual_fps = clock.get_fps()
        # Wall-clock elapsed (excludes paused time)
        now = time.monotonic()
        pause_adj = (now - wall_pause_begin) if wall_pause_begin else 0.0
        wall_elapsed = now - wall_start - wall_paused_total - pause_adj
        rendering.render_hud(
            screen, font_hud, sim, frame, predators,
            actual_fps)

        # --- Elapsed time (bottom-right) ---
        rendering.render_elapsed_time(screen, wall_elapsed)

        # --- Participant hint (bottom-center) ---
        rendering.render_participant_hint(screen)

        # --- Evolution panel (bottom-left, unified boid + predator) ---
        if config.EVOLUTION_ENABLED:
            rendering.render_evolution_panel(
                screen, font_help_title, font_hud, sim, frame,
                predators=predators,
                starvation_events_total=predator_starvation_total)

        # --- Help overlay ---
        if show_help and help_alpha > 0:
            rendering.draw_help_overlay(
                screen, help_alpha, font_help_title,
                font_help, config.WIDTH, config.HEIGHT)
        prof.end()

        # Auto-fade: after HELP_DISPLAY_SECS, gradually reduce opacity
        if help_auto_fade and show_help:
            if frame > HELP_DISPLAY_SECS * config.TARGET_FPS:
                help_alpha = max(0, help_alpha - HELP_FADE_SPEED)
                if help_alpha <= 0:
                    show_help = False
                    help_auto_fade = False

        pygame.display.flip()
        clock.tick(config.TARGET_FPS)
        prof.tick()

    pygame.quit()
    print("\n  Goodbye!")


if __name__ == '__main__':
    main()
