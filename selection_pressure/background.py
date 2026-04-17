"""
SELECTION PRESSURE - Galaxy Background
======================================
Precomputed star field + nebula fog rendered at startup.
Zero per-frame cost except one surface blit.

Demonstrates knowledge transfer across modules:
  Module 1.1.1 (Color Basics)  — RGB channel manipulation, additive mixing
  Module 2.1.4 (Stars)         — Gaussian clusters, brightness variation,
                                  integer array indexing, cross patterns
  Module 3.4.1 (Convolution)   — Gaussian kernel concept for glow halos
  Module 4.1.3 (Mandelbrot)    — Sine-wave color mapping
  Module 6.1.1 (Perlin Noise)  — Smooth coherent noise for nebula fog
  Module 8     (Animation)     — Time-based sine oscillation for twinkling
"""

import numpy as np
import pygame
import config


# ============================================================
# STAR FIELD GENERATION
# ============================================================

def generate_star_field(width, height, seed=42):
    """
    Generate a multi-layer star field as a NumPy RGB array.

    Four depth layers create parallax-like depth:
      Layer 1 (distant):  single-pixel, dim, uniform distribution
      Layer 2 (medium):   Gaussian-clustered around galactic centers
      Layer 3 (bright):   scattered, 3x3 cross pattern with color tint
      Layer 4 (mega):     Gaussian glow halos, blue-white or warm-white

    Returns (stars_array, twinkle_data) where stars_array has shape
    (width, height, 3) matching pygame surfarray convention.
    """
    rng = np.random.default_rng(seed)
    stars = np.zeros((width, height, 3), dtype=np.float32)

    # --- Layer 1: Dense distant stars (uniform distribution) ---
    # [Module 2.1.4 Transfer] simple_star.py: random uniform placement
    dx = rng.integers(0, width, size=config.NUM_STARS_DISTANT)
    dy = rng.integers(0, height, size=config.NUM_STARS_DISTANT)
    brightness = rng.integers(20, 60, size=config.NUM_STARS_DISTANT).astype(
        np.float32)
    # [Module 1.1.1 Transfer] Per-channel tinting for warm/cool star colors
    tint_r = rng.uniform(0.8, 1.0, size=config.NUM_STARS_DISTANT).astype(
        np.float32)
    tint_b = rng.uniform(0.9, 1.2, size=config.NUM_STARS_DISTANT).astype(
        np.float32)
    for i in range(config.NUM_STARS_DISTANT):
        x, y = int(dx[i]), int(dy[i])
        b = brightness[i]
        stars[x, y, 0] = max(stars[x, y, 0], b * tint_r[i])
        stars[x, y, 1] = max(stars[x, y, 1], b)
        stars[x, y, 2] = max(stars[x, y, 2], b * tint_b[i])

    # --- Layer 2: Medium Gaussian-clustered stars ---
    # [Module 2.1.4 Transfer] gaussian_cluster.py + multi_cluster_solution.py
    stars_per_cluster = config.NUM_STARS_MEDIUM // max(
        1, len(config.STAR_CLUSTER_CENTERS))
    for cx_frac, cy_frac, spread_frac in config.STAR_CLUSTER_CENTERS:
        cx = cx_frac * width
        cy = cy_frac * height
        spread = spread_frac * min(width, height)

        mx = rng.normal(cx, spread, size=stars_per_cluster)
        my = rng.normal(cy, spread, size=stars_per_cluster)
        mx = np.clip(mx, 0, width - 1).astype(int)
        my = np.clip(my, 0, height - 1).astype(int)
        mb = rng.integers(60, 150, size=stars_per_cluster).astype(np.float32)

        for i in range(stars_per_cluster):
            x, y = int(mx[i]), int(my[i])
            b = mb[i]
            stars[x, y] = np.maximum(stars[x, y], b)
            # 2px extension for brighter stars
            if b > 100 and x + 1 < width:
                stars[x + 1, y] = np.maximum(stars[x + 1, y], b * 0.5)

    # --- Layer 3: Bright foreground stars with cross patterns ---
    # [Module 2.1.4 Transfer] brightness_variation.py cross pattern
    bx = rng.integers(4, width - 4, size=config.NUM_STARS_BRIGHT)
    by = rng.integers(4, height - 4, size=config.NUM_STARS_BRIGHT)
    bb = rng.integers(180, 256, size=config.NUM_STARS_BRIGHT).astype(
        np.float32)

    for i in range(config.NUM_STARS_BRIGHT):
        x, y = int(bx[i]), int(by[i])
        b = bb[i]
        # [Module 4.1.3 Transfer] Sine-wave color mapping for star tinting
        phase = rng.uniform(0, 2 * np.pi)
        tint = np.array([
            0.8 + 0.2 * np.sin(phase),
            0.9 + 0.1 * np.sin(phase + 2.094),
            0.8 + 0.2 * np.sin(phase + 4.189),
        ], dtype=np.float32)

        # 3x3 cross (center bright, arms dimmer, diagonals faint)
        stars[x, y] = np.maximum(stars[x, y], b * tint)
        for dx_off, dy_off in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = x + dx_off, y + dy_off
            stars[nx, ny] = np.maximum(stars[nx, ny], b * 0.6 * tint)
        for dx_off, dy_off in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            nx, ny = x + dx_off, y + dy_off
            stars[nx, ny] = np.maximum(stars[nx, ny], b * 0.25 * tint)

    # --- Layer 4: Mega stars with Gaussian glow halos ---
    # [Module 3.4.1 Transfer] Gaussian kernel stamp (convolution concept)
    twinkle_candidates = []
    mx_pos = rng.integers(8, width - 8, size=config.NUM_STARS_MEGA)
    my_pos = rng.integers(8, height - 8, size=config.NUM_STARS_MEGA)

    for i in range(config.NUM_STARS_MEGA):
        x, y = int(mx_pos[i]), int(my_pos[i])
        b = rng.uniform(220, 255)

        # Blue-white or warm-white tinting
        if rng.random() > 0.5:
            tint = np.array([0.85, 0.92, 1.0])
        else:
            tint = np.array([1.0, 0.95, 0.85])

        glow_radius = 6
        sigma = 2.5
        for gx in range(-glow_radius, glow_radius + 1):
            for gy in range(-glow_radius, glow_radius + 1):
                nx, ny = x + gx, y + gy
                if 0 <= nx < width and 0 <= ny < height:
                    dist_sq = gx * gx + gy * gy
                    intensity = b * np.exp(-dist_sq / (2 * sigma * sigma))
                    pixel_color = intensity * tint
                    stars[nx, ny] = np.maximum(stars[nx, ny], pixel_color)

        twinkle_candidates.append({
            'x': x, 'y': y, 'base_brightness': b,
            'tint': tint, 'glow_radius': glow_radius, 'sigma': sigma,
        })

    # Also include some bright Layer 3 stars as twinkle candidates
    for i in range(min(config.NUM_STARS_BRIGHT, 20)):
        twinkle_candidates.append({
            'x': int(bx[i]), 'y': int(by[i]),
            'base_brightness': float(bb[i]),
            'tint': np.array([1.0, 1.0, 1.0]),
            'glow_radius': 0, 'sigma': 0,
        })

    # Select twinkle stars and assign phase/frequency
    # [Module 8 Transfer] Per-element phase offsets for natural variation
    twinkle_data = None
    if config.TWINKLE_ENABLED and config.TWINKLE_COUNT > 0:
        n_twinkle = min(config.TWINKLE_COUNT, len(twinkle_candidates))
        selected = rng.choice(
            len(twinkle_candidates), size=n_twinkle, replace=False)
        twinkle_data = []
        for idx in selected:
            star = twinkle_candidates[idx].copy()
            star['phase'] = float(rng.uniform(0, 2 * np.pi))
            star['freq'] = float(rng.uniform(
                config.TWINKLE_SPEED_RANGE[0], config.TWINKLE_SPEED_RANGE[1]))
            twinkle_data.append(star)

    stars_uint8 = np.clip(stars, 0, 255).astype(np.uint8)
    return stars_uint8, twinkle_data


# ============================================================
# NEBULA FOG GENERATION
# ============================================================

def generate_nebula(width, height, seed=42):
    """
    Generate multi-layered nebula fog using smooth noise.

    Uses NumPy random grids upscaled with pygame.transform.smoothscale
    (same technique as the bloom pipeline) to create organic fog without
    external noise libraries.

    [Module 6.1.1 Transfer] Coherent noise concepts — smooth random fields
    [Module 1.1.1 Transfer] Per-channel RGB tinting, additive color mixing
    """
    rng = np.random.default_rng(seed)
    nebula = np.zeros((width, height, 3), dtype=np.float32)

    # Gaussian cluster mask: concentrate nebula around galactic centers
    yy, xx = np.meshgrid(np.arange(height), np.arange(width))
    cluster_mask = np.zeros((width, height), dtype=np.float32)
    for cx_frac, cy_frac, spread_frac in config.STAR_CLUSTER_CENTERS:
        cx = cx_frac * width
        cy = cy_frac * height
        spread = spread_frac * min(width, height) * 2.5
        dist_sq = (xx - cx) ** 2 + (yy - cy) ** 2
        cluster_mask += np.exp(-dist_sq / (2 * spread * spread))
    cluster_mask = np.clip(cluster_mask, 0, 1)
    # Low baseline so nebula isn't zero outside clusters
    cluster_mask = 0.15 + 0.85 * cluster_mask

    # Generate one smooth noise layer per nebula color per octave
    grid = config.NEBULA_GRID_SIZE
    for color_idx, (nr, ng, nb) in enumerate(config.NEBULA_COLORS):
        combined_noise = np.zeros((width, height), dtype=np.float32)
        amplitude = 1.0

        for octave in range(config.NEBULA_OCTAVES):
            octave_seed = seed + color_idx * 17 + octave * 7
            oct_rng = np.random.default_rng(octave_seed)

            # Grid size increases with octaves for finer detail
            g = grid * (2 ** octave)
            gh = max(1, g * height // width)
            noise_small = oct_rng.uniform(0, 1, size=(g, gh)).astype(
                np.float32)

            # Upscale to full resolution via pygame smoothscale (bilinear)
            noise_surf = pygame.Surface((g, gh))
            noise_gray = (noise_small * 255).astype(np.uint8)
            noise_rgb = np.stack(
                [noise_gray, noise_gray, noise_gray], axis=-1)
            pygame.surfarray.blit_array(noise_surf, noise_rgb)
            noise_full_surf = pygame.transform.smoothscale(
                noise_surf, (width, height))
            noise_full = pygame.surfarray.array3d(noise_full_surf)[:, :, 0]
            noise_full = noise_full.astype(np.float32) / 255.0

            combined_noise += noise_full * amplitude
            amplitude *= 0.5  # Each octave contributes less (persistence)

        # Normalize to [0, 1]
        combined_noise /= sum(0.5 ** o for o in range(config.NEBULA_OCTAVES))

        # Apply cluster mask
        combined_noise *= cluster_mask

        # Map to color channel intensities
        max_b = config.NEBULA_MAX_BRIGHTNESS
        nebula[:, :, 0] += combined_noise * nr * max_b / 255.0
        nebula[:, :, 1] += combined_noise * ng * max_b / 255.0
        nebula[:, :, 2] += combined_noise * nb * max_b / 255.0

    return np.clip(nebula, 0, 255).astype(np.uint8)


# ============================================================
# COMPOSITE GALAXY BACKGROUND
# ============================================================

def generate_galaxy_background(width, height, seed=42):
    """
    Compose the full galaxy background: nebula fog + star field.

    Returns (galaxy_surface, twinkle_data).
    """
    print("  Generating galaxy background...")

    # Nebula fog (Module 6.1.1 + 1.1.1)
    print("    Nebula fog (smooth noise + cluster mask)...")
    nebula = generate_nebula(width, height, seed=seed + 100)

    # Star field (Module 2.1.4 + 4.1.3 + 3.4.1)
    print("    Star field (Gaussian clusters + cross patterns + glow halos)...")
    stars, twinkle_data = generate_star_field(width, height, seed=seed + 200)

    # [Module 1.1.1 Transfer] Additive color mixing — stars are light ON nebula
    combined = nebula.astype(np.float32) + stars.astype(np.float32)
    combined = np.clip(combined, 0, 255).astype(np.uint8)

    galaxy_surface = pygame.Surface((width, height))
    pygame.surfarray.blit_array(galaxy_surface, combined)

    print("    Galaxy background ready.")
    return galaxy_surface, twinkle_data


# ============================================================
# TWINKLE ANIMATION
# ============================================================

def update_twinkle_overlay(overlay, twinkle_data, frame, fps):
    """
    Animate twinkling stars with per-star sine-wave brightness modulation.

    [Module 8 Transfer] Time-based sine oscillation with phase offsets.

    Stamps modulated star glows onto a cleared overlay surface each frame.
    The overlay is composited additively onto the screen.
    """
    overlay.fill((0, 0, 0))
    t = frame / max(fps, 1)

    for star in twinkle_data:
        x, y = star['x'], star['y']
        base_b = star['base_brightness']
        tint = star['tint']
        phase = star['phase']
        freq = star['freq']
        glow_r = star['glow_radius']
        sigma = star['sigma']

        modulator = 1.0 + config.TWINKLE_AMPLITUDE * np.sin(
            2 * np.pi * freq * t + phase)
        b = base_b * modulator

        if glow_r > 0 and sigma > 0:
            # Mega star: re-stamp Gaussian glow halo at modulated brightness
            for gx in range(-glow_r, glow_r + 1):
                for gy in range(-glow_r, glow_r + 1):
                    nx, ny = x + gx, y + gy
                    if 0 <= nx < config.WIDTH and 0 <= ny < config.HEIGHT:
                        dist_sq = gx * gx + gy * gy
                        intensity = b * np.exp(
                            -dist_sq / (2 * sigma * sigma))
                        color = tuple(
                            int(min(255, intensity * c)) for c in tint)
                        overlay.set_at((nx, ny), color)
        else:
            # Cross-pattern star: modulate center + arms
            color = tuple(int(min(255, max(0, b * c))) for c in tint)
            dim = tuple(int(min(255, max(0, b * 0.6 * c))) for c in tint)
            overlay.set_at((x, y), color)
            for dx_off, dy_off in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = x + dx_off, y + dy_off
                if 0 <= nx < config.WIDTH and 0 <= ny < config.HEIGHT:
                    overlay.set_at((nx, ny), dim)
