"""
SELECTION PRESSURE Rendering
============================
Scene rendering: trail fading, boid drawing, black hole effects, bloom
and gravitational lensing.  Text overlays live in ``hud.py``.

Every function reads visual parameters from the config module.
Simulation state is passed in — no simulation logic lives here.
"""

import numpy as np
import pygame
from . import config


# ============================================================
# CACHES (avoid per-frame allocation and recomputation)
# ============================================================

_fade_color = None
_fade_color_params = None
_bloom_lut = None
_bloom_intensity = None
_bloom_small_surf = None
_bloom_full_surf = None
_halo_surf_normal = None
_halo_surf_lunge = None
_halo_params = None


def _get_fade_color():
    """Return cached RGB fade color for BLEND_RGB_MULT fill."""
    global _fade_color, _fade_color_params
    params = (config.TRAIL_FADE_R, config.TRAIL_FADE_G, config.TRAIL_FADE_B)
    if _fade_color is None or _fade_color_params != params:
        _fade_color = (round(config.TRAIL_FADE_R * 255),
                       round(config.TRAIL_FADE_G * 255),
                       round(config.TRAIL_FADE_B * 255))
        _fade_color_params = params
    return _fade_color


def _get_bloom_lut():
    """Return cached bloom intensity LUT, rebuilding if config changed."""
    global _bloom_lut, _bloom_intensity
    if _bloom_lut is None or _bloom_intensity != config.BLOOM_INTENSITY:
        src = np.arange(256, dtype=np.float32)
        _bloom_lut = (src * config.BLOOM_INTENSITY).astype(np.uint8)
        _bloom_intensity = config.BLOOM_INTENSITY
    return _bloom_lut


def _get_halo_surfaces():
    """Return cached halo dimming surfaces (normal, lunge).

    Each surface is a radial gradient where pixel brightness = dimming
    factor (white = no change, darker = more dimming).  Blitted with
    BLEND_RGB_MULT to replace the per-frame numpy halo computation.
    """
    global _halo_surf_normal, _halo_surf_lunge, _halo_params
    params = (config.BLACK_HOLE_HALO_RADIUS, config.BLACK_HOLE_VOID_RADIUS,
              config.BLACK_HOLE_HALO_STRENGTH)
    if _halo_params == params:
        return _halo_surf_normal, _halo_surf_lunge
    _halo_params = params

    for is_lunge in (False, True):
        hr = config.BLACK_HOLE_HALO_RADIUS
        if is_lunge:
            hr = int(hr * 1.4)
        size = 2 * hr + 1
        surf = pygame.Surface((size, size))
        surf.fill((255, 255, 255))  # white = no dimming

        xs = np.arange(size, dtype=np.float32) - hr
        ys = np.arange(size, dtype=np.float32) - hr
        xx, yy = np.meshgrid(xs, ys, indexing='ij')
        dist = np.sqrt(xx * xx + yy * yy)

        vr = config.BLACK_HOLE_VOID_RADIUS
        t = np.clip((dist - vr) / (hr - vr + 1e-10), 0, 1)
        factor = (config.BLACK_HOLE_HALO_STRENGTH
                  + (1.0 - config.BLACK_HOLE_HALO_STRENGTH) * t)
        factor = np.where(dist < hr, factor, 1.0)
        factor_u8 = (factor * 255).astype(np.uint8)

        px = pygame.surfarray.pixels3d(surf)
        px[:, :, 0] = factor_u8
        px[:, :, 1] = factor_u8
        px[:, :, 2] = factor_u8
        del px

        if is_lunge:
            _halo_surf_lunge = surf
        else:
            _halo_surf_normal = surf

    return _halo_surf_normal, _halo_surf_lunge


# ============================================================
# COLOR UTILITIES
# ============================================================

def get_palette():
    """Return the currently active color palette."""
    return config.PALETTES.get(config.ACTIVE_PALETTE, config.PALETTES[0])


def get_palette_colors(frame_num, phase_offsets, total_frames):
    """Get interpolated RGB colors for all boids."""
    palette = get_palette()
    n_colors = len(palette)
    palette_arr = np.array(palette, dtype=np.float32)
    cycle_len = max(1, total_frames / max(1, config.COLOR_CYCLES))

    pos = ((frame_num / cycle_len) + phase_offsets) % 1.0
    idx_float = pos * n_colors
    idx_a = idx_float.astype(int) % n_colors
    idx_b = (idx_a + 1) % n_colors
    frac = (idx_float - np.floor(idx_float))[:, np.newaxis]

    return palette_arr[idx_a] * (1 - frac) + palette_arr[idx_b] * frac


# ============================================================
# GRAVITATIONAL LENSING PRECOMPUTATION
# ============================================================

def precompute_lens_maps():
    """Precompute gravitational lensing displacement maps.

    Returns dict with 'normal' and 'lunge' entries, each a tuple of
    (dx_map, dy_map, half_size).  Called once at startup.
    """
    lr = config.LENS_RADIUS
    lens_size = 2 * lr + 1
    lx = np.arange(lens_size) - lr
    ly = np.arange(lens_size) - lr
    lxx, lyy = np.meshgrid(lx, ly, indexing='ij')
    ldist = np.sqrt(lxx ** 2 + lyy ** 2)
    ldist_safe = np.maximum(ldist, 1e-10)

    t = np.clip(ldist / lr, 0, 1)
    displacement = config.LENS_STRENGTH * (1.0 - t) ** config.LENS_FALLOFF
    displacement = np.where(ldist <= lr, displacement, 0.0)
    displacement = np.where(
        ldist >= config.BLACK_HOLE_VOID_RADIUS, displacement, 0.0)

    # Positive direction = source is further from center than output pixel.
    # This pulls bright trail content inward toward the void (converging lens).
    lens_dx = (displacement * (lxx / ldist_safe)).astype(np.float32)
    lens_dy = (displacement * (lyy / ldist_safe)).astype(np.float32)

    # Lunge version: 1.4x radius, 1.4x strength
    lr_lunge = int(lr * 1.4)
    lens_size_l = 2 * lr_lunge + 1
    lx_l = np.arange(lens_size_l) - lr_lunge
    ly_l = np.arange(lens_size_l) - lr_lunge
    lxx_l, lyy_l = np.meshgrid(lx_l, ly_l, indexing='ij')
    ldist_l = np.sqrt(lxx_l ** 2 + lyy_l ** 2)
    ldist_safe_l = np.maximum(ldist_l, 1e-10)
    t_l = np.clip(ldist_l / lr_lunge, 0, 1)
    disp_l = (config.LENS_STRENGTH * 1.4) * (1.0 - t_l) ** config.LENS_FALLOFF
    disp_l = np.where(ldist_l <= lr_lunge, disp_l, 0.0)
    void_r_lunge = int(config.BLACK_HOLE_VOID_RADIUS * 1.4)
    disp_l = np.where(ldist_l >= void_r_lunge, disp_l, 0.0)
    lens_dx_lunge = (disp_l * (lxx_l / ldist_safe_l)).astype(np.float32)
    lens_dy_lunge = (disp_l * (lyy_l / ldist_safe_l)).astype(np.float32)

    return {
        'normal': (lens_dx, lens_dy, lr),
        'lunge': (lens_dx_lunge, lens_dy_lunge, lr_lunge),
    }


# ============================================================
# TRAIL FADING
# ============================================================

def fade_trails(trail_surface):
    """Apply per-channel fade to trail surface (warm-to-cool color shift).

    Uses two SDL fill operations (both run in C, no numpy):
    1. BLEND_RGB_MULT — multiply each channel by its fade factor
    2. BLEND_RGB_SUB  — subtract 1 to guarantee pixels reach zero

    The subtract is needed because SDL's integer multiply rounds up at low
    values (e.g. pixel=10, factor=247: (10*247+128)>>8 = 10), which would
    leave a permanent residual glow on every pixel a boid ever touched.
    """
    trail_surface.fill(_get_fade_color(),
                       special_flags=pygame.BLEND_RGB_MULT)
    trail_surface.fill((1, 1, 1),
                       special_flags=pygame.BLEND_RGB_SUB)


# ============================================================
# BOID DRAWING
# ============================================================

def _lineage_colors(lineage_ids, num_boids):
    """Map lineage_ids to unique hues on a fixed color ring.

    Each lineage_id maps to a distinct HSV hue; saturation and value are
    fixed at 1.0 so colors are vivid.  Returns (N, 3) float32 RGB array.
    """
    # Use golden-ratio spacing for perceptually distinct hues
    golden = 0.618033988749895
    hues = (lineage_ids.astype(np.float64) * golden) % 1.0
    # HSV->RGB inline (S=1, V=1)
    h6 = hues * 6.0
    sector = h6.astype(int) % 6
    frac = h6 - np.floor(h6)
    r = np.where(sector == 0, 1.0,
        np.where(sector == 1, 1.0 - frac,
        np.where(sector == 2, 0.0,
        np.where(sector == 3, 0.0,
        np.where(sector == 4, frac, 1.0)))))
    g = np.where(sector == 0, frac,
        np.where(sector == 1, 1.0,
        np.where(sector == 2, 1.0,
        np.where(sector == 3, 1.0 - frac,
        np.where(sector == 4, 0.0, 0.0)))))
    b = np.where(sector == 0, 0.0,
        np.where(sector == 1, 0.0,
        np.where(sector == 2, frac,
        np.where(sector == 3, 1.0,
        np.where(sector == 4, 1.0, 1.0 - frac)))))
    return np.stack([r * 255, g * 255, b * 255], axis=1).astype(np.float32)


def draw_boids(boid_layer, trail_surface, sim, frame, total_frames,
               predators):
    """Draw boid dots/streaks with palette colors, fear shift, and shimmer.

    Draws onto boid_layer (cleared each frame), then composites additively
    onto trail_surface.
    """
    # Choose color source: lineage-based or palette-based
    if config.EVOLUTION_COLOR_MODE and config.EVOLUTION_ENABLED:
        colors = _lineage_colors(sim.lineage_ids, sim.num)
    else:
        colors = get_palette_colors(frame, sim.phase_offsets, total_frames)

    # Fear color shift: boids near any predator redshift
    if (config.BLACK_HOLE_ENABLED and len(predators) > 0
            and config.BLACK_HOLE_FEAR_COLOR_SHIFT
            and sim._bh_dist is not None):
        # Use first predator's flee_radius for fear gradient
        flee_r = predators[0].params.flee_radius
        fear_factor = np.clip(1.0 - sim._bh_dist / flee_r, 0, 1)
        fear_color = np.array([255, 30, 10], dtype=np.float32)
        blend = fear_factor[:, np.newaxis] * 0.7
        colors = colors * (1 - blend) + fear_color * blend

    # --- Star energy visuals: brightness only (preserves lineage colors) ---
    if config.STAR_ENERGY_ENABLED:
        # Brightness maps to energy — starving stars dim, feeding stars brighten
        brightness = np.clip(sim.energy * 0.85 + 0.15, 0.15, 1.0)
        colors = colors * brightness[:, np.newaxis]

    # --- Quorum sensing visuals: fortress stars pulse in unison ---
    if config.QUORUM_ENABLED and config.QUORUM_VISUAL_PULSE:
        if np.any(sim.in_quorum):
            # Synchronized breathing pulse for fortress stars
            pulse = 0.8 + 0.2 * np.sin(frame * 0.1)
            quorum_boost = np.where(sim.in_quorum, pulse, 1.0)
            colors = colors * quorum_boost[:, np.newaxis]
            # Blue-white fortress tint
            fortress_tint = np.array([200, 220, 255], dtype=np.float32)
            blend = np.where(sim.in_quorum, 0.2, 0.0)[:, np.newaxis]
            colors = colors * (1 - blend) + fortress_tint * blend

    # --- Defensive formation visuals: silver shimmer on in_defensive boids ---
    if np.any(sim.in_defensive):
        silver = np.array(config.DEFENSIVE_SILVER_COLOR, dtype=np.float32)
        # Per-boid blend: 1.0 for defensive boids, 0.0 for others
        d_blend = np.where(sim.in_defensive,
                           config.DEFENSIVE_SILVER_BLEND, 0.0)[:, np.newaxis]
        colors = colors * (1.0 - d_blend) + silver * d_blend
        # Spatial shimmer wave (only affects defensive boids)
        t = frame / max(config.TARGET_FPS, 1)
        wave_dir_x = np.cos(t * 0.5)
        wave_dir_y = np.sin(t * 0.5)
        spatial_phase = (sim.positions[:, 0] * wave_dir_x
                         + sim.positions[:, 1] * wave_dir_y) * 0.02
        shimmer_val = (config.DEFENSIVE_SHIMMER_AMOUNT
                       * np.sin(2 * np.pi * config.DEFENSIVE_SHIMMER_SPEED * t
                                + spatial_phase))
        shimmer = 1.0 + np.where(sim.in_defensive, shimmer_val, 0.0)
        colors = colors * shimmer[:, np.newaxis]

    # Scale colors down for additive blending — prevents instant white-out
    # when boids overlap. 2-3 overlapping boids reach full brightness.
    colors = colors * 0.4

    speed_ratios = sim.speeds / sim.params.max_speed

    # Draw onto temporary black surface, then add to trail
    boid_layer.fill((0, 0, 0))

    # Effective streak width (defensive mode = thinner streaks)
    eff_streak_w = config.STREAK_WIDTH
    if np.any(sim.in_defensive):
        eff_streak_w = max(1, int(config.STREAK_WIDTH
                                  * config.DEFENSIVE_STREAK_TIGHTEN + 0.5))

    # Pre-convert numpy arrays to Python lists — eliminates per-iteration
    # numpy element access overhead (type checks, scalar wrapping).
    pos_x = sim.positions[:, 0].astype(np.intp).tolist()
    pos_y = sim.positions[:, 1].astype(np.intp).tolist()
    clipped = np.clip(colors, 0, 255).astype(np.uint8)
    col_r = clipped[:, 0].tolist()
    col_g = clipped[:, 1].tolist()
    col_b = clipped[:, 2].tolist()

    # Local references avoid repeated attribute lookups in the inner loop
    _draw_line = pygame.draw.line
    _draw_circle = pygame.draw.circle

    if config.STREAK_LENGTH > 0:
        vel_mag = sim.speeds.clip(1e-10)
        vel_ux = (sim.velocities[:, 0] / vel_mag).tolist()
        vel_uy = (sim.velocities[:, 1] / vel_mag).tolist()
        streak_lens = (config.STREAK_LENGTH * speed_ratios).tolist()

        for i in range(sim.num):
            x = pos_x[i]
            y = pos_y[i]
            color = (col_r[i], col_g[i], col_b[i])
            sl = streak_lens[i]
            tx = int(x - vel_ux[i] * sl)
            ty = int(y - vel_uy[i] * sl)
            _draw_line(boid_layer, color, (tx, ty), (x, y), eff_streak_w)
            _draw_circle(boid_layer, color, (x, y), max(1, eff_streak_w))
    else:
        if config.SPEED_AFFECTS_SIZE:
            speed_ratios_list = speed_ratios.tolist()
            for i in range(sim.num):
                r = max(2, int(config.GLOW_BASE_RADIUS
                               * (1.3 - 0.5 * speed_ratios_list[i])))
                _draw_circle(boid_layer,
                             (col_r[i], col_g[i], col_b[i]),
                             (pos_x[i], pos_y[i]), r)
        else:
            r = config.GLOW_BASE_RADIUS
            for i in range(sim.num):
                _draw_circle(boid_layer,
                             (col_r[i], col_g[i], col_b[i]),
                             (pos_x[i], pos_y[i]), r)

    # Additive composite: overlapping boids glow brighter
    trail_surface.blit(
        boid_layer, (0, 0), special_flags=pygame.BLEND_RGB_ADD)


# ============================================================
# NEBULA RESOURCE CLOUDS
# ============================================================

# Precomputed radial gradient surfaces for nebula clouds (cached)
_nebula_glow_cache = {}


def draw_nebula_clouds(screen, nebula, frame):
    """Draw nebula resource clouds as soft translucent glows.

    Rich clouds glow warm gold-green (food); depleted clouds dim to olive.
    Visually distinct from background nebula (purple/blue decorative).
    Called AFTER galaxy background, BEFORE trail surface composite.
    """
    if nebula is None or not config.NEBULA_FIELDS_ENABLED:
        return

    for i in range(nebula.num):
        cx = int(round(nebula.positions[i, 0]))
        cy = int(round(nebula.positions[i, 1]))
        density = nebula.densities[i]

        # Visual radius scales with config cloud radius (smaller for rendering)
        vis_r = int(config.NEBULA_CLOUD_RADIUS * 0.6)

        # Get or create cached gradient surface for this size
        if vis_r not in _nebula_glow_cache:
            size = 2 * vis_r + 1
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            xs = np.arange(size, dtype=np.float32) - vis_r
            ys = np.arange(size, dtype=np.float32) - vis_r
            xx, yy = np.meshgrid(xs, ys, indexing='ij')
            dist = np.sqrt(xx * xx + yy * yy)
            # Gaussian falloff
            alpha = np.exp(-dist * dist / (2.0 * (vis_r * 0.4) ** 2))
            alpha = np.where(dist < vis_r, alpha, 0.0)
            _nebula_glow_cache[vis_r] = (surf, alpha)

        surf_template, alpha_template = _nebula_glow_cache[vis_r]

        # Color: warm gold-green for rich, dim olive for depleted
        rich_t = np.clip(density / config.NEBULA_CLOUD_MAX_DENSITY, 0, 1)
        # Subtle breathing animation
        breath = 0.9 + 0.1 * np.sin(frame * 0.03 + i * 1.5)
        base_alpha = rich_t * 0.35 * breath

        r = int(40 + 60 * rich_t)
        g = int(60 + 80 * rich_t)
        b = int(10 + 20 * rich_t)

        # Create the surface for this frame
        size = 2 * vis_r + 1
        cloud_surf = pygame.Surface((size, size), pygame.SRCALPHA)
        px = pygame.surfarray.pixels_alpha(cloud_surf)
        px[:] = (alpha_template * base_alpha * 255).astype(np.uint8)
        del px
        px_rgb = pygame.surfarray.pixels3d(cloud_surf)
        px_rgb[:, :, 0] = r
        px_rgb[:, :, 1] = g
        px_rgb[:, :, 2] = b
        del px_rgb

        screen.blit(cloud_surf, (cx - vis_r, cy - vis_r))


# ============================================================
# BLACK HOLE VISUAL EFFECTS
# ============================================================

def draw_black_holes(trail_surface, predators, frame):
    """Draw all black hole visual effects onto trail_surface.

    Includes: dark halo, accretion particles, photon ring, accretion glow,
    dark void, photon sphere, and consume flash effects.
    """
    if not config.BLACK_HOLE_ENABLED or len(predators) == 0:
        return

    # Dark halo: gradually dim trail pixels near each black hole.
    # The void doesn't just cover light — it *drains* nearby brightness.
    # Uses precomputed radial gradient surfaces blitted with BLEND_RGB_MULT
    # instead of per-frame numpy computation (~2-3ms -> ~0.1ms per predator).
    if (config.BLACK_HOLE_HALO_RADIUS > 0
            and config.BLACK_HOLE_HALO_STRENGTH < 1.0):
        halo_normal, halo_lunge = _get_halo_surfaces()
        for pred in predators:
            cx = int(round(pred.position[0]))
            cy = int(round(pred.position[1]))
            if pred.lunging:
                halo_surf = halo_lunge
                hr = int(config.BLACK_HOLE_HALO_RADIUS * 1.4)
            else:
                halo_surf = halo_normal
                hr = config.BLACK_HOLE_HALO_RADIUS

            # Scale halo by mass (heavier BH = larger dimming area)
            if config.ACCRETION_HUNGER_ENABLED:
                mass_scale = pred.mass ** config.BH_MASS_RADIUS_EXPONENT
                hr = int(hr * mass_scale)
                orig_size = halo_surf.get_size()
                new_size = (int(orig_size[0] * mass_scale),
                            int(orig_size[1] * mass_scale))
                if new_size != orig_size:
                    halo_surf = pygame.transform.scale(halo_surf, new_size)

            trail_surface.blit(halo_surf, (cx - hr, cy - hr),
                               special_flags=pygame.BLEND_RGB_MULT)

    for pred in predators:
        bh_x = int(round(pred.position[0]))
        bh_y = int(round(pred.position[1]))

        # Accretion disk: spiraling particles drawn BEFORE void
        # so the void circle covers particles that reach the center.
        if config.ACCRETION_ENABLED:
            pred.step_accretion()
            for ap in pred.accretion:
                angle, radius, init_r = ap[0], ap[1], ap[2]
                ar, ag, ab, age = ap[3], ap[4], ap[5], ap[6]
                # Absolute position (tracks black hole movement)
                px = bh_x + radius * np.cos(angle)
                py = bh_y + radius * np.sin(angle)
                # Brightness: heats up as radius shrinks, fades with age
                t_life = age / max(pred.params.accretion_lifetime, 1)
                heat = 1.0 + 0.6 * (1.0 - radius / max(init_r, 1))
                fade = 1.0 - t_life ** 0.7
                bright = max(0.0, min(1.0, heat * fade))
                color = (int(ar * bright), int(ag * bright),
                         int(ab * bright))
                # Size grows slightly as particle spirals inward
                dot_r = max(
                    1, int(2 + (1.0 - radius / max(init_r, 1)) * 2))
                pygame.draw.circle(
                    trail_surface, color,
                    (int(round(px)), int(round(py))), dot_r)

        # Visual scaling during lunge + mass
        lunge_scale = 1.4 if pred.lunging else 1.0
        mass_scale = (pred.mass ** config.BH_MASS_RADIUS_EXPONENT
                      if config.ACCRETION_HUNGER_ENABLED else 1.0)
        void_r = int(config.BLACK_HOLE_VOID_RADIUS * lunge_scale * mass_scale)

        # --- Option 1: Photon ring (concentric warm glow rings) ---
        if config.PHOTON_RING_ENABLED:
            # Layers from outside in: faint deep red -> white-hot
            glow_defs = [
                (35, (40, 10, 5), 8),       # outer: faint deep red
                (25, (120, 50, 10), 5),      # mid-outer: warm amber
                (18, (200, 100, 30), 4),     # mid: bright orange
                (12, (255, 180, 80), 3),     # inner: hot orange-yellow
                (6,  (255, 230, 180), 2),    # innermost: white-hot
            ]
            for offset, gc, gw in glow_defs:
                gr = void_r + offset
                if pred.lunging:
                    gc = tuple(min(255, int(c * 1.4)) for c in gc)
                pygame.draw.circle(
                    trail_surface, gc, (bh_x, bh_y), gr, width=gw)
        else:
            # Fallback: original single ring
            ring_r = int(config.BLACK_HOLE_RING_RADIUS * lunge_scale)
            ring_w = 3 if pred.lunging else 2
            ring_col = (
                min(255, int(config.BLACK_HOLE_RING_COLOR[0]
                             * (2.0 if pred.lunging else 1.0))),
                config.BLACK_HOLE_RING_COLOR[1],
                min(255, int(config.BLACK_HOLE_RING_COLOR[2]
                             * (1.5 if pred.lunging else 1.0)))
            )
            pygame.draw.circle(
                trail_surface, ring_col,
                (bh_x, bh_y), ring_r, width=ring_w)

        # --- Option 2: Accretion glow (persistent orbiting warm ring) ---
        if config.ACCRETION_GLOW_ENABLED:
            glow_r = void_r + 20
            n_glow = 48
            bright_a = frame * 0.015   # bright spot rotates (~7s/rev)
            for k in range(n_glow):
                a = 2.0 * np.pi * k / n_glow
                # Doppler: brightness peaks at bright_a, dims opposite
                doppler = 0.3 + 0.7 * (0.5 + 0.5 * np.cos(a - bright_a))
                if pred.lunging:
                    doppler = min(1.0, doppler * 1.3)
                gx = bh_x + int(glow_r * np.cos(a))
                gy = bh_y + int(glow_r * np.sin(a))
                gc = (int(255 * doppler), int(150 * doppler),
                      int(40 * doppler))
                pygame.draw.circle(trail_surface, gc, (gx, gy), 3)

        # Dark void (always on top — truly black center)
        pygame.draw.circle(
            trail_surface, (0, 0, 0),
            (bh_x, bh_y), void_r
        )

        # --- Option 3: Photon sphere (thin bright rim at void edge) ---
        if config.PHOTON_SPHERE_ENABLED:
            rim_c = (255, 255, 240) if pred.lunging else (255, 240, 220)
            pygame.draw.circle(
                trail_surface, rim_c,
                (bh_x, bh_y), void_r + 1, width=1)

        # Consume flash effects (warm orange = death)
        pred.age_flashes()
        for flash in pred.flashes:
            fx, fy = int(round(flash[0])), int(round(flash[1]))
            age = flash[5]
            flash_r = 5 + age * 3
            alpha = max(0, 255 - age * 22)
            flash_color = (
                min(255, int(flash[2] * alpha / 255)),
                min(255, int(flash[3] * alpha / 255)),
                min(255, int(flash[4] * alpha / 255))
            )
            if alpha > 0:
                pygame.draw.circle(
                    trail_surface, flash_color,
                    (fx, fy), flash_r, width=2
                )


# ============================================================
# BLACK HOLE VOID ON SCREEN (post-composite)
# ============================================================

def stamp_void_on_screen(screen, predators):
    """Stamp truly-black void circles onto the final composited screen.

    draw_black_holes() paints the void on trail_surface, but the additive
    composite (trail + galaxy background) lets stars shine through black
    pixels.  This function runs AFTER composite_display to guarantee the
    event horizon is fully opaque — no light escapes.

    Call order: composite_display -> stamp_void_on_screen -> apply_bloom -> apply_lensing
    Lensing warps around the sharp void edge (physically correct).
    """
    if not config.BLACK_HOLE_ENABLED or len(predators) == 0:
        return
    for pred in predators:
        bh_x = int(round(pred.position[0]))
        bh_y = int(round(pred.position[1]))
        lunge_scale = 1.4 if pred.lunging else 1.0
        mass_scale = (pred.mass ** config.BH_MASS_RADIUS_EXPONENT
                      if config.ACCRETION_HUNGER_ENABLED else 1.0)
        void_r = int(config.BLACK_HOLE_VOID_RADIUS * lunge_scale * mass_scale)
        pygame.draw.circle(screen, (0, 0, 0), (bh_x, bh_y), void_r)


# ============================================================
# BIRTH FLASH (evolution respawn effect)
# ============================================================

def draw_birth_flashes(trail_surface, birth_flashes):
    """Draw cyan ring pulses at boid respawn points.

    Each flash is [x, y, age].  Distinct from warm-orange death flashes.
    """
    for flash in birth_flashes:
        fx, fy, age = int(round(flash[0])), int(round(flash[1])), flash[2]
        flash_r = 4 + age * 2
        alpha = max(0, 255 - age * 18)
        if alpha > 0:
            color = (0, min(255, int(200 * alpha / 255)),
                     min(255, int(255 * alpha / 255)))
            pygame.draw.circle(
                trail_surface, color, (fx, fy), flash_r, width=2)


# ============================================================
# PREDATOR EXPLOSION (starvation death effect)
# ============================================================

# Explosion lifetime in frames (visual only — does not affect simulation)
_EXPLOSION_LIFETIME = 45

def draw_predator_explosions(trail_surface, explosions):
    """Draw dramatic expanding ring + particle burst at predator death sites.

    Each explosion is [x, y, age].  Ages are incremented in-place.
    Expired explosions are removed from the list.

    Much larger than birth/consume flashes — the predator's death is a
    major event with 3-4 concentric rings (white-hot inner -> orange outer)
    plus scattered bright particles.
    """
    alive = []
    for exp in explosions:
        fx, fy, age = int(round(exp[0])), int(round(exp[1])), exp[2]
        t = age / _EXPLOSION_LIFETIME  # 0.0 -> 1.0 over lifetime

        # Overall brightness fade
        brightness = max(0.0, 1.0 - t ** 0.6)

        # Ring 1: outermost — large, faint orange-red
        r1 = int(30 + age * 5)
        a1 = max(0, int(120 * brightness))
        if a1 > 0:
            c1 = (min(255, int(255 * brightness * 0.7)),
                  min(255, int(100 * brightness * 0.5)),
                  min(255, int(20 * brightness * 0.3)))
            pygame.draw.circle(trail_surface, c1, (fx, fy), r1, width=3)

        # Ring 2: mid — bright orange
        r2 = int(20 + age * 3.5)
        a2 = max(0, int(180 * brightness))
        if a2 > 0:
            c2 = (min(255, int(255 * brightness)),
                  min(255, int(160 * brightness * 0.7)),
                  min(255, int(40 * brightness * 0.3)))
            pygame.draw.circle(trail_surface, c2, (fx, fy), r2, width=3)

        # Ring 3: inner — yellow-white, hot core
        r3 = int(10 + age * 2)
        a3 = max(0, int(220 * brightness))
        if a3 > 0:
            c3 = (min(255, int(255 * brightness)),
                  min(255, int(230 * brightness)),
                  min(255, int(150 * brightness * 0.8)))
            pygame.draw.circle(trail_surface, c3, (fx, fy), r3, width=2)

        # Ring 4: innermost — white-hot flash (early frames only)
        if age < 15:
            r4 = int(5 + age * 1.2)
            c4 = (min(255, int(255 * brightness)),
                  min(255, int(255 * brightness)),
                  min(255, int(240 * brightness)))
            pygame.draw.circle(trail_surface, c4, (fx, fy), r4, width=2)

        # Particle scatter — bright dots radiating outward
        if age < 30:
            n_particles = max(1, 16 - age // 2)
            for k in range(n_particles):
                angle = (k / n_particles) * 2 * 3.14159 + age * 0.15
                dist = 15 + age * 4.5 + k * 2
                px = fx + int(dist * np.cos(angle))
                py = fy + int(dist * np.sin(angle))
                pb = max(0.0, brightness * (1.0 - age / 30))
                pc = (min(255, int(255 * pb)),
                      min(255, int(200 * pb)),
                      min(255, int(80 * pb)))
                pygame.draw.circle(trail_surface, pc, (px, py), 2)

        # Age this explosion
        exp[2] += 1
        if exp[2] < _EXPLOSION_LIFETIME:
            alive.append(exp)

    # Prune dead explosions in-place
    explosions[:] = alive


# ============================================================
# DISPLAY COMPOSITING
# ============================================================

def composite_display(screen, trail_surface, galaxy_bg, twinkle_overlay,
                      twinkle_data, frame):
    """Composite all layers onto the screen surface."""
    if config.GALAXY_BG_ENABLED and galaxy_bg is not None:
        # Layer 1: Static galaxy background (stars + nebula fog)
        screen.blit(galaxy_bg, (0, 0))

        # Layer 1.5: Twinkling stars (Module 8: time-based animation)
        if (config.TWINKLE_ENABLED and twinkle_data
                and twinkle_overlay is not None):
            from .background import update_twinkle_overlay
            update_twinkle_overlay(
                twinkle_overlay, twinkle_data, frame, config.TARGET_FPS)
            screen.blit(twinkle_overlay, (0, 0),
                        special_flags=pygame.BLEND_RGB_ADD)

        # Layer 2: Boid trails composited additively on top of galaxy.
        # Black trail pixels (faded areas) add nothing — galaxy shows
        # through.  Active trails glow brighter than the background.
        # [Module 1.1.1 Transfer] Additive color mixing.
        screen.blit(trail_surface, (0, 0),
                    special_flags=pygame.BLEND_RGB_ADD)
    else:
        # Original behavior: trail surface is the only layer
        screen.blit(trail_surface, (0, 0))


# ============================================================
# BLOOM
# ============================================================

def apply_bloom(screen, trail_surface):
    """Downscale-blur-upscale the trail, then add to screen as soft glow.

    Applied to screen only (not trail_surface), so trails don't accumulate
    blur and screenshots (which save trail_surface) stay clean.

    Optimized: LUT applied on the small surface (~130K px instead of ~2M),
    nearest-neighbor upscale instead of bilinear, and cached surfaces to
    avoid per-frame allocation.
    """
    global _bloom_small_surf, _bloom_full_surf
    if not config.BLOOM_ENABLED or config.BLOOM_INTENSITY <= 0:
        return

    scr_w, scr_h = screen.get_size()
    small_w = max(1, scr_w // config.BLOOM_DOWNSCALE)
    small_h = max(1, scr_h // config.BLOOM_DOWNSCALE)

    # Cache intermediate surfaces to avoid per-frame allocation
    if (_bloom_small_surf is None
            or _bloom_small_surf.get_size() != (small_w, small_h)):
        _bloom_small_surf = pygame.Surface((small_w, small_h))
    if (_bloom_full_surf is None
            or _bloom_full_surf.get_size() != (scr_w, scr_h)):
        _bloom_full_surf = pygame.Surface((scr_w, scr_h))

    # Downscale: smoothscale averages nearby pixels (cheap box blur)
    pygame.transform.smoothscale(trail_surface, (small_w, small_h),
                                 _bloom_small_surf)
    # Dim the bloom by intensity factor — on the SMALL surface (16x fewer px)
    lut = _get_bloom_lut()
    bpx = pygame.surfarray.pixels3d(_bloom_small_surf)
    bpx[:] = lut[bpx]
    del bpx  # release surface lock
    # Nearest-neighbor upscale (much faster than smoothscale)
    pygame.transform.scale(_bloom_small_surf,
                           (scr_w, scr_h), _bloom_full_surf)
    # Additive composite: soft glow halo appears around bright areas
    screen.blit(_bloom_full_surf, (0, 0), special_flags=pygame.BLEND_RGB_ADD)


# ============================================================
# GRAVITATIONAL LENSING
# ============================================================

def apply_lensing(screen, predators, lens_maps):
    """Warp screen pixels around each black hole using precomputed maps.

    Applied to screen only — trail_surface stays unmodified so screenshots
    remain clean.
    """
    if (not config.LENS_ENABLED or not config.BLACK_HOLE_ENABLED
            or len(predators) == 0):
        return

    scr_px = pygame.surfarray.pixels3d(screen)
    scr_w, scr_h = screen.get_size()

    for pred in predators:
        cx = int(round(pred.position[0]))
        cy = int(round(pred.position[1]))

        # Select normal or lunge displacement map
        if pred.lunging:
            dx_map, dy_map, half = lens_maps['lunge']
        else:
            dx_map, dy_map, half = lens_maps['normal']

        # Mass-scaled lensing: heavier black holes warp more strongly
        mass_lens = (pred.mass ** config.BH_MASS_RADIUS_EXPONENT
                     if config.ACCRETION_HUNGER_ENABLED else 1.0)

        # Bounding box clipped to actual screen surface size
        x0 = max(0, cx - half)
        x1 = min(scr_w, cx + half + 1)
        y0 = max(0, cy - half)
        y1 = min(scr_h, cy + half + 1)
        if x1 <= x0 or y1 <= y0:
            continue

        # Slice of displacement map matching the clipped region
        mx0 = x0 - (cx - half)
        mx1 = mx0 + (x1 - x0)
        my0 = y0 - (cy - half)
        my1 = my0 + (y1 - y0)

        # Source pixel coordinates (where to sample from)
        local_x = np.arange(x0, x1)[:, np.newaxis]
        local_y = np.arange(y0, y1)[np.newaxis, :]
        src_x = (local_x + dx_map[mx0:mx1, my0:my1] * mass_lens).astype(np.intp)
        src_y = (local_y + dy_map[mx0:mx1, my0:my1] * mass_lens).astype(np.intp)

        # Clamp to actual screen bounds
        np.clip(src_x, 0, scr_w - 1, out=src_x)
        np.clip(src_y, 0, scr_h - 1, out=src_y)

        # Remap: read from source positions, write to output region
        warped = scr_px[src_x, src_y]
        scr_px[x0:x1, y0:y1] = warped
    del scr_px  # release surface lock before HUD drawing
