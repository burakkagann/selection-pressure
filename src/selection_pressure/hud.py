"""
SELECTION PRESSURE HUD
======================
Text overlays drawn on top of the scene: status line, elapsed clock,
visitor hint, evolution panel and help overlay.
"""

import numpy as np
import pygame

from . import config


# ============================================================
# HUD (Heads-Up Display)
# ============================================================

def render_hud(screen, font, sim, frame, predators,
               actual_fps, wall_elapsed=0.0):
    """Render the top-left HUD status line."""
    hud = font.render(
        f"FPS: {actual_fps:.0f} | Stars: {sim.num} | "
        f"Frame: {frame}",
        True, (150, 150, 150)
    )
    screen.blit(hud, (10, 10))


# ============================================================
# PARTICIPANT HINT (bottom-center, subtle)
# ============================================================

_hint_font_cache = {}


def render_participant_hint(screen):
    """Draw subtle interaction hint at bottom-center for exhibition visitors."""
    size = 18
    if size not in _hint_font_cache:
        _hint_font_cache[size] = pygame.font.SysFont("consolas", size)
    font = _hint_font_cache[size]

    hint_surf = font.render(
        "[  ]   Add / Remove Black Holes", True, (120, 120, 120, 80))
    scr_w, scr_h = screen.get_size()
    x = (scr_w - hint_surf.get_width()) // 2
    y = scr_h - 30
    screen.blit(hint_surf, (x, y))


# ============================================================
# ELAPSED TIME (bottom-right, exhibition aesthetic)
# ============================================================

_time_font_cache = {}


def render_elapsed_time(screen, wall_elapsed):
    """Draw a minimal HH:MM:SS clock in the bottom-right corner.

    Designed to feel like part of the installation — visible at projection
    distance, balanced opposite the evolution panel.
    """
    hours = int(wall_elapsed) // 3600
    mins = (int(wall_elapsed) % 3600) // 60
    secs = int(wall_elapsed) % 60
    time_str = f"{hours:02d}:{mins:02d}:{secs:02d}"

    # Larger font for projection readability
    size = 32
    if size not in _time_font_cache:
        _time_font_cache[size] = pygame.font.SysFont("consolas", size)
    font = _time_font_cache[size]

    # Warm-gray — visible on projector
    color = (140, 135, 130)
    time_surf = font.render(time_str, True, color)

    # Bottom-right with comfortable margin
    margin = 20
    scr_w, scr_h = screen.get_size()
    x = scr_w - time_surf.get_width() - margin
    y = scr_h - time_surf.get_height() - margin
    screen.blit(time_surf, (x, y))


# ============================================================
# EVOLUTION PANEL (exhibition-friendly stats overlay)
# ============================================================

# Display labels for genome fields (matches GENOME_FIELDS order)
_GENOME_LABELS = [
    'Separation',  'Alignment',  'Cohesion',
    'Sep Radius',  'Ali Radius', 'Coh Radius',
    'Max Speed',   'Min Speed',  'Steer',
    'Chemotaxis',  'Quorum',
]

# Display labels for predator genome fields (matches PREDATOR_GENOME_FIELDS order)
_PRED_GENOME_LABELS = [
    'Speed',       'Steer',       'Sight',
    'Lunge Spd',   'Lunge Dur',   'Lunge CD',
    'Consume R',
]


_evo_panel_cache = None
_evo_panel_pos = None
_evo_cache_frame = -100


def render_evolution_panel(screen, font_title, font_body, sim, frame=0,
                           predators=None, starvation_events_total=0):
    """Draw a unified bottom-left panel: boid genome + predator stats.

    Top section: boid genome drift bars, diversity, lineage distribution.
    Bottom section (if predators active): per-predator starvation bars,
    kill counts, generation, evolved genome values.

    Panel is rebuilt every 6 frames and blitted from cache otherwise.
    """
    global _evo_panel_cache, _evo_panel_pos, _evo_cache_frame

    if not config.EVOLUTION_ENABLED or not sim.per_boid_params:
        return

    # Use cached panel surface when possible (10 updates/sec is enough)
    if (_evo_panel_cache is not None
            and frame - _evo_cache_frame < 6):
        screen.blit(_evo_panel_cache, _evo_panel_pos)
        return

    _evo_cache_frame = frame

    # Determine if predator section is included
    show_predators = (predators is not None
                      and len(predators) > 0
                      and config.BLACK_HOLE_ENABLED
                      and config.PREDATOR_EVOLUTION_ENABLED)
    n_preds = len(predators) if show_predators else 0

    pad_x, pad_y = 14, 10
    line_h = font_body.get_linesize() + 3
    title_h = font_title.get_linesize() + 4
    label_col_w = 110  # width reserved for text labels
    bar_w = 100   # width of each genome drift bar
    bar_h = 8     # height of each bar
    starv_bar_w = 100  # starvation bar width
    starv_bar_h = 10

    # --- Compute boid stats ---
    ids, counts = np.unique(sim.lineage_ids, return_counts=True)
    unique_count = len(ids)
    diversity = unique_count / max(sim.num, 1)
    top_sort = np.argsort(-counts)

    # Top lineages for display (up to 5)
    top_n = min(5, len(ids))
    top_lineages = [(ids[top_sort[i]], counts[top_sort[i]]) for i in range(top_n)]

    # Full sorted distribution for population color bar
    all_lineages_sorted = [(ids[top_sort[i]], counts[top_sort[i]])
                           for i in range(len(ids))]

    # Genome means and defaults
    genome_stats = []
    for i, (field_name, default, lo, hi) in enumerate(config.GENOME_FIELDS):
        arr = sim.per_boid_params.get(field_name)
        if arr is not None:
            mean_val = float(arr.mean())
            std_val = float(arr.std())
        else:
            mean_val = default
            std_val = 0.0
        label = _GENOME_LABELS[i] if i < len(_GENOME_LABELS) else field_name
        genome_stats.append((label, mean_val, default, lo, hi, std_val))

    # --- Panel sizing ---
    n_genome = len(genome_stats)
    n_lineage_rows = top_n
    bar_row_h = max(line_h, bar_h + 8)

    pop_bar_h = 14
    total_rows = (1              # title
                  + n_genome     # genome bars
                  + 1            # spacer
                  + 1            # diversity
                  + n_lineage_rows  # top lineages
                  + 1)           # population bar label
    panel_w = 320
    panel_h = (pad_y * 2 + title_h + n_genome * bar_row_h
               + (total_rows - n_genome) * line_h
               + pop_bar_h + 10)

    # Add height for predator section (side-by-side columns, fixed height)
    if show_predators:
        n_pred_genome = len(config.PREDATOR_GENOME_FIELDS)
        mass_bar_lines = (line_h + 2) if config.ACCRETION_HUNGER_ENABLED else 0
        # Height for ONE predator column (all predators same height)
        single_pred_h = (2 * line_h + 2 + mass_bar_lines
                         + n_pred_genome * bar_row_h)
        pred_section_h = title_h + 4 + single_pred_h
        panel_h += pred_section_h
        # Widen panel for multiple predators (side-by-side columns)
        pred_col_w = 150  # width per predator column
        min_pred_panel_w = pad_x * 2 + n_preds * pred_col_w + (n_preds - 1) * 6
        panel_w = max(panel_w, min_pred_panel_w)

    # Position: bottom-left corner
    panel_x = 16
    _, scr_h_panel = screen.get_size()
    panel_y = scr_h_panel - panel_h - 16

    # --- Create alpha surface ---
    panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    panel.fill((10, 10, 15, 190))

    text_col = (200, 200, 210, 220)
    dim_col = (140, 140, 150, 200)
    accent_col = (140, 180, 255, 220)
    bar_bg_col = (40, 40, 50, 200)
    sep_col = (60, 60, 70, 160)

    y = pad_y

    # ===== BOID SECTION =====

    # Title with selection count right-aligned
    title_surf = font_title.render("Star Genome", True, accent_col)
    panel.blit(title_surf, (pad_x, y))
    gen_surf = font_body.render(
        f"{sim.total_consumed} sel", True, dim_col)
    panel.blit(gen_surf, (panel_w - pad_x - gen_surf.get_width(), y + 6))
    y += title_h

    # --- Genome drift bars ---
    for label, mean_val, default, lo, hi, std_val in genome_stats:
        lbl_surf = font_body.render(label, True, text_col)
        panel.blit(lbl_surf, (pad_x, y))

        bx = pad_x + label_col_w
        by = y + 2
        pygame.draw.rect(panel, bar_bg_col, (bx, by, bar_w, bar_h))

        range_span = hi - lo
        if range_span > 0:
            default_frac = (default - lo) / range_span
            mean_frac = (mean_val - lo) / range_span
        else:
            default_frac = 0.5
            mean_frac = 0.5

        def_px = int(bx + default_frac * bar_w)
        pygame.draw.line(panel, (120, 120, 130, 200),
                         (def_px, by - 1), (def_px, by + bar_h + 1), 1)

        mean_px = int(bx + mean_frac * bar_w)
        if mean_val > default:
            fill_color = (60, 200, 180, 220)
        else:
            fill_color = (220, 140, 50, 220)
        x0 = min(def_px, mean_px)
        x1 = max(def_px, mean_px)
        if x1 > x0:
            pygame.draw.rect(panel, fill_color, (x0, by + 1, x1 - x0, bar_h - 2))

        pygame.draw.circle(panel, (255, 255, 255, 240),
                           (mean_px, by + bar_h // 2), 3)

        val_str = f"{mean_val:.2f}" if abs(mean_val) < 10 else f"{mean_val:.1f}"
        val_surf = font_body.render(val_str, True, dim_col)
        panel.blit(val_surf, (bx + bar_w + 6, y))

        y += bar_row_h

    # --- Spacer ---
    y += 4

    # --- Diversity ---
    div_label = f"Diversity: {unique_count}/{sim.num} ({diversity:.0%})"
    div_surf = font_body.render(div_label, True, text_col)
    panel.blit(div_surf, (pad_x, y))
    y += line_h

    # --- Top lineages with color swatches ---
    golden = 0.618033988749895
    for rank, (lin_id, lin_count) in enumerate(top_lineages):
        pct = lin_count / max(sim.num, 1)
        hue = (float(lin_id) * golden) % 1.0
        h6 = hue * 6.0
        sector = int(h6) % 6
        frac = h6 - int(h6)
        if sector == 0:   rgb = (1.0, frac, 0.0)
        elif sector == 1: rgb = (1.0 - frac, 1.0, 0.0)
        elif sector == 2: rgb = (0.0, 1.0, frac)
        elif sector == 3: rgb = (0.0, 1.0 - frac, 1.0)
        elif sector == 4: rgb = (frac, 0.0, 1.0)
        else:             rgb = (1.0, 0.0, 1.0 - frac)
        swatch_col = (int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255))

        sx = pad_x
        sy = y + 2
        pygame.draw.rect(panel, swatch_col, (sx, sy, 10, 10))

        lin_surf = font_body.render(
            f" #{lin_id}  {lin_count} stars ({pct:.0%})", True, text_col)
        panel.blit(lin_surf, (sx + 14, y))
        y += line_h

    # --- Population color bar ---
    y += 4
    pop_label = font_body.render("Population", True, dim_col)
    panel.blit(pop_label, (pad_x, y))
    y += line_h - 2

    pop_bar_x = pad_x
    pop_bar_total_w = panel_w - pad_x * 2
    pygame.draw.rect(panel, bar_bg_col,
                     (pop_bar_x, y, pop_bar_total_w, pop_bar_h))

    cx = pop_bar_x
    for lin_id, lin_count in all_lineages_sorted:
        seg_w = max(1, int(lin_count / max(sim.num, 1) * pop_bar_total_w))
        if cx + seg_w > pop_bar_x + pop_bar_total_w:
            seg_w = pop_bar_x + pop_bar_total_w - cx
        if seg_w <= 0:
            break
        hue = (float(lin_id) * golden) % 1.0
        h6 = hue * 6.0
        sector = int(h6) % 6
        frac = h6 - int(h6)
        if sector == 0:   rgb = (1.0, frac, 0.0)
        elif sector == 1: rgb = (1.0 - frac, 1.0, 0.0)
        elif sector == 2: rgb = (0.0, 1.0, frac)
        elif sector == 3: rgb = (0.0, 1.0 - frac, 1.0)
        elif sector == 4: rgb = (frac, 0.0, 1.0)
        else:             rgb = (1.0, 0.0, 1.0 - frac)
        seg_col = (int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255))
        pygame.draw.rect(panel, seg_col, (cx, y + 1, seg_w, pop_bar_h - 2))
        cx += seg_w

    y += pop_bar_h + 4

    # ===== PREDATOR SECTION (side-by-side columns) =====

    if show_predators:
        # Separator line
        pygame.draw.line(panel, sep_col,
                         (pad_x, y), (panel_w - pad_x, y), 1)
        y += 4

        # Sub-header with death count right-aligned
        pred_title = font_title.render("Black Holes", True, accent_col)
        panel.blit(pred_title, (pad_x, y))
        ev_surf = font_body.render(
            f"{starvation_events_total} deaths", True, dim_col)
        panel.blit(ev_surf, (panel_w - pad_x - ev_surf.get_width(), y + 6))
        y += title_h

        starvation_max = max(1, config.PREDATOR_STARVATION_FRAMES)
        col_gap = 6  # gap between predator columns

        # Draw each predator in its own column
        for idx, pred in enumerate(predators):
            col_x = pad_x + idx * (pred_col_w + col_gap)
            cy = y  # reset vertical position for each column

            # Column header: #idx Gen N | kills
            header = f"#{idx} G{pred.generation} {pred.kill_count}/{pred.total_kills}"
            hdr_surf = font_body.render(header, True, text_col)
            panel.blit(hdr_surf, (col_x, cy))
            cy += line_h

            # Compact bar layout for columns
            col_label_w = 42  # shorter labels in columns
            col_bar_w = pred_col_w - col_label_w - 6

            # Starvation bar
            starvation_frac = min(1.0,
                                  pred.frames_since_last_kill / starvation_max)
            lbl_surf = font_body.render("Hgr", True, dim_col)
            panel.blit(lbl_surf, (col_x, cy))

            bx = col_x + col_label_w
            by = cy + 1
            pygame.draw.rect(panel, bar_bg_col,
                             (bx, by, col_bar_w, starv_bar_h))

            fill_w = max(0, int(starvation_frac * col_bar_w))
            if starvation_frac < 0.5:
                t = starvation_frac / 0.5
                fill_col = (int(60 + 195 * t), int(200 - 60 * t), 60, 220)
            elif starvation_frac < 0.8:
                t = (starvation_frac - 0.5) / 0.3
                fill_col = (255, int(140 - 80 * t), int(60 - 40 * t), 220)
            else:
                t = (starvation_frac - 0.8) / 0.2
                pulse = 1.0
                if starvation_frac > 0.9:
                    pulse = 0.7 + 0.3 * abs(
                        ((frame % 20) / 20.0) * 2.0 - 1.0)
                fill_col = (min(255, int(255 * pulse)),
                            int(60 * (1.0 - t) * pulse),
                            int(20 * pulse), 240)

            if fill_w > 0:
                pygame.draw.rect(panel, fill_col,
                                 (bx + 1, by + 1, fill_w - 2, starv_bar_h - 2))
            cy += line_h + 2

            # Mass bar (accretion hunger)
            if config.ACCRETION_HUNGER_ENABLED:
                mass_frac = ((pred.mass - config.BH_MASS_MIN)
                             / max(1e-10, config.BH_MASS_MAX - config.BH_MASS_MIN))
                mass_frac = max(0.0, min(1.0, mass_frac))

                lbl_surf = font_body.render("Mas", True, dim_col)
                panel.blit(lbl_surf, (col_x, cy))

                bx = col_x + col_label_w
                by = cy + 1
                pygame.draw.rect(panel, bar_bg_col,
                                 (bx, by, col_bar_w, starv_bar_h))

                fill_w = max(0, int(mass_frac * col_bar_w))
                mass_r = int(120 + 135 * mass_frac)
                mass_g = int(60 * (1.0 - mass_frac * 0.6))
                mass_b = int(180 + 75 * mass_frac)
                mass_col = (mass_r, mass_g, mass_b, 220)

                if fill_w > 0:
                    pygame.draw.rect(panel, mass_col,
                                     (bx + 1, by + 1,
                                      fill_w - 2, starv_bar_h - 2))
                cy += line_h + 2

            # Genome drift bars (compact for column)
            pp = pred.params
            for gi, (field_name, default, lo, hi) in enumerate(
                    config.PREDATOR_GENOME_FIELDS):
                label = _PRED_GENOME_LABELS[gi]
                val = getattr(pp, field_name)

                # Short 3-char label for compact columns
                short_lbl = label[:3]
                lbl_surf = font_body.render(short_lbl, True, text_col)
                panel.blit(lbl_surf, (col_x, cy))

                bx = col_x + col_label_w
                by = cy + 2
                pygame.draw.rect(panel, bar_bg_col,
                                 (bx, by, col_bar_w, bar_h))

                range_span = hi - lo
                if range_span > 0:
                    default_frac = (default - lo) / range_span
                    val_frac = (val - lo) / range_span
                else:
                    default_frac = 0.5
                    val_frac = 0.5

                def_px = int(bx + default_frac * col_bar_w)
                pygame.draw.line(panel, (120, 120, 130, 200),
                                 (def_px, by - 1),
                                 (def_px, by + bar_h + 1), 1)

                val_px = int(bx + val_frac * col_bar_w)
                if val > default:
                    fill_color = (60, 200, 180, 220)
                else:
                    fill_color = (220, 140, 50, 220)
                x0 = min(def_px, val_px)
                x1 = max(def_px, val_px)
                if x1 > x0:
                    pygame.draw.rect(panel, fill_color,
                                     (x0, by + 1, x1 - x0,
                                      bar_h - 2))

                pygame.draw.circle(
                    panel, (255, 255, 255, 240),
                    (val_px, by + bar_h // 2), 3)

                cy += bar_row_h

        # Advance y past the predator section (single column height)
        y = y + single_pred_h

    # --- Cache and blit panel onto screen ---
    _evo_panel_cache = panel
    _evo_panel_pos = (panel_x, panel_y)
    screen.blit(panel, (panel_x, panel_y))


# ============================================================

# ============================================================
# HELP OVERLAY
# ============================================================

def draw_help_overlay(screen, alpha, font_title, font_body,
                      screen_w, screen_h, num_stars, num_black_holes):
    """Draw a semi-transparent help panel on the right side of the screen."""
    if alpha <= 0:
        return

    # --- Build text lines ---
    title = "SELECTION PRESSURE - Controls"
    separator = chr(0x2500) * 20  # horizontal box-drawing line

    controls = [
        ("H", "Toggle this help"),
        ("ESC / Q", "Quit"),
        ("SPACE", "Pause / Resume"),
        ("R", "Reset"),
        ("S", "Screenshot"),
        ("F", "Fullscreen"),
        ("+/-", "Stars (+/- 50)"),
        ("[ / ]", "Add / Remove black hole"),
    ]

    # Live status section
    status_lines = [
        f"Stars: {num_stars}",
        f"Black Holes: {num_black_holes}",
    ]

    # --- Measure layout ---
    pad_x, pad_y = 20, 16
    line_h = font_body.get_linesize() + 2
    title_h = font_title.get_linesize() + 4

    # Total lines: title + separator + controls + separator + "Status" + status
    num_lines = (1 + 1 + len(controls) + 1 + 1 + len(status_lines))
    panel_h = pad_y * 2 + title_h + num_lines * line_h
    panel_w = 320

    # Position: right edge, vertically centered
    panel_x = screen_w - panel_w - 16
    panel_y = max(16, (screen_h - panel_h) // 2)

    # --- Create alpha surface ---
    panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    bg_alpha = int(alpha * 0.75)
    panel.fill((10, 10, 15, bg_alpha))

    # --- Render text onto panel ---
    a = int(alpha)
    text_col = (210, 210, 220, a)
    dim_col = (150, 150, 160, a)
    accent_col = (140, 180, 255, a)

    y = pad_y

    # Title
    title_surf = font_title.render(title, True, accent_col)
    panel.blit(title_surf, (pad_x, y))
    y += title_h

    # Separator
    sep_surf = font_body.render(separator, True, dim_col)
    panel.blit(sep_surf, (pad_x, y))
    y += line_h

    # Controls
    for key, desc in controls:
        if key == "":
            y += line_h // 2  # half-height spacer
            continue
        key_surf = font_body.render(f"{key:<12}", True, accent_col)
        desc_surf = font_body.render(desc, True, text_col)
        panel.blit(key_surf, (pad_x, y))
        panel.blit(desc_surf, (pad_x + 110, y))
        y += line_h

    # Status separator
    y += line_h // 2
    status_label = f"{chr(0x2500)*2} Status {chr(0x2500)*2}"
    sep2_surf = font_body.render(status_label, True, dim_col)
    panel.blit(sep2_surf, (pad_x, y))
    y += line_h

    # Status lines
    for line in status_lines:
        line_surf = font_body.render(line, True, text_col)
        panel.blit(line_surf, (pad_x, y))
        y += line_h

    # --- Blit panel onto screen ---
    screen.blit(panel, (panel_x, panel_y))
