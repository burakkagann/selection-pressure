"""
SELECTION PRESSURE HUD
======================
Everything drawn on top of the artwork:

* the evolution **strip** along the bottom (default view),
* the evolution **timeline** on the right (expanded view, ``I`` again),
* the **controls card** in the centre (``H``),
* a short start hint, and the exhibition hint and clock (``--kiosk`` only).

All panels share the look defined in ``ui.py``.  Panels are rebuilt a few
times a second and blitted from a cache in between.
"""

from __future__ import annotations

import numpy as np
import pygame

from . import config, ui
from .rendering import lineage_color
from .ui import ACCENT, DOWN, MASS, MUTED, OTHER_FAMILIES, TEXT, UP

REBUILD_FRAMES = 6  # rebuild cached panels every 6 frames (10 times a second)
TOP_FAMILIES = 6
STRIP_MIN_WIDTH = 1180  # narrower windows get a scaled-down strip

# (label, unit) for each gene, in config.GENOME_FIELDS order
GENES = [
    ("Separation", ""),
    ("Alignment", ""),
    ("Cohesion", ""),
    ("Personal space", "px"),
    ("Alignment range", "px"),
    ("Cohesion range", "px"),
    ("Top speed", ""),
    ("Minimum speed", ""),
    ("Agility", ""),
    ("Food sense", ""),
    ("Fortress trigger", ""),
]
GENE_GROUPS = [
    ("Flocking", (0, 1, 2)),
    ("Senses", (3, 4, 5, 9)),
    ("Movement", (6, 7, 8)),
    ("Survival", (10,)),
]
STRIP_GENES = (0, 6, 2, 9)  # the four that change the look the most

CONTROLS = [
    (
        "View",
        [
            (("I",), "Evolution panel: strip, timeline, off"),
            (("H",), "This card"),
            (("F",), "Fullscreen"),
            (("M",), "Black hole style"),
        ],
    ),
    (
        "World",
        [
            (("Space",), "Pause"),
            (("R",), "Restart"),
            (("+", "-"), "50 more or fewer stars"),
            (("]", "["), "Add or remove a black hole"),
        ],
    ),
    (
        "Make",
        [
            (("S",), "Screenshot, without panels"),
            (("G",), "Black hole tuning"),
            (("D",), "Print tuning values"),
            (("Esc",), "Quit"),
        ],
    ),
]


def format_gene(index, value):
    unit = GENES[index][1]
    if unit or index == 10:
        return f"{value:.0f} {unit}".strip()
    return f"{value:.2f}"


def gene_means(sim):
    means = []
    for name, default, _lo, _hi in config.GENOME_FIELDS:
        values = sim.per_boid_params.get(name) if sim.per_boid_params else None
        means.append(float(values.mean()) if values is not None and len(values) else default)
    return means


def _fraction(value, lo, hi):
    return (value - lo) / (hi - lo) if hi > lo else 0.5


class Hud:
    """Draws the panels; owns their caches."""

    def __init__(self, ui_: ui.UI):
        self.ui = ui_
        self._cache: dict[str, tuple[int, pygame.Surface]] = {}

    def invalidate(self):
        self._cache.clear()

    def _cached(self, key, frame, build):
        hit = self._cache.get(key)
        if hit is not None and 0 <= frame - hit[0] < REBUILD_FRAMES:
            return hit[1]
        surface = build()
        self._cache[key] = (frame, surface)
        return surface

    # ---- shared pieces ---------------------------------------------------

    def _families(self, sim):
        ids, counts = np.unique(sim.lineage_ids[: sim.num], return_counts=True)
        order = np.argsort(-counts, kind="stable")
        top = [(int(ids[i]), int(counts[i])) for i in order[:TOP_FAMILIES]]
        diversity = len(ids) / max(sim.num, 1)
        return top, len(ids), diversity

    def _family_bar(self, panel, rect, sim, top):
        u = self.ui
        rect = pygame.Rect(rect)
        bar = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(bar, OTHER_FAMILIES, bar.get_rect())
        x, total = 0, max(sim.num, 1)
        for lineage, count in top:
            w = round(count / total * rect.width)
            pygame.draw.rect(bar, lineage_color(lineage), (x, 0, w, rect.height))
            x += w
        mask = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=u.px(3))
        bar.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        panel.blit(bar, rect)

    def _hole_rows(self, panel, x, y, width, predators, collapsed):
        """Black hole table: header plus one row per hole.  Returns the new y."""
        u, s = self.ui, self.ui.px
        gap = s(12)
        label_w = max(u.small.size("Black holes")[0], u.body.size("3 · g99")[0]) + gap
        eaten_w = u.mono.size("9999 eaten")[0]
        meter_w = max(s(20), (width - label_w - eaten_w - 3 * gap) // 2)
        hx = x + label_w
        mx = hx + meter_w + gap
        row_h = s(22)
        u.text(panel, u.small, "Black holes", (x, y), MUTED)
        if not predators:
            u.text(panel, u.small, "none", (hx, y), MUTED)
            return y + row_h
        u.text(panel, u.small, "hunger", (hx, y), MUTED)
        u.text(panel, u.small, "mass", (mx, y), MUTED)
        u.text(panel, u.small, f"{collapsed} collapsed", (x + width, y), MUTED, "topright")
        y += row_h
        starve = max(1, config.PREDATOR_STARVATION_FRAMES)
        span = max(1e-10, config.BH_MASS_MAX - config.BH_MASS_MIN)
        for i, pred in enumerate(predators):
            mid = y + row_h // 2
            u.text(panel, u.body, f"{i + 1} · g{pred.generation}", (x, mid), TEXT, "midleft")
            hunger = min(1.0, pred.frames_since_last_kill / starve)
            meter_h = s(6)
            u.meter(
                panel, (hx, mid - meter_h // 2, meter_w, meter_h), hunger, ui.hunger_color(hunger)
            )
            mass = (pred.mass - config.BH_MASS_MIN) / span
            u.meter(panel, (mx, mid - meter_h // 2, meter_w, meter_h), mass, MASS)
            u.text(panel, u.mono, f"{pred.total_kills} eaten", (x + width, mid), MUTED, "midright")
            y += row_h
        return y

    # ---- B: lower-third strip ----------------------------------------------

    def draw_strip(self, screen, sim, predators, collapsed, frame):
        """Draw the strip; returns its rect on screen."""
        u = self.ui
        sw, sh = screen.get_size()
        margin = u.px(24)
        panel = self._cached(
            "strip", frame, lambda: self._build_strip(sw - 2 * margin, sim, predators, collapsed)
        )
        panel = ui.fit(panel, sw - 2 * margin, sh // 3)
        rect = panel.get_rect(midbottom=(sw // 2, sh - margin))
        screen.blit(panel, rect)
        return rect

    def _build_strip(self, width, sim, predators, collapsed):
        u, s = self.ui, self.ui.px
        width = max(width, s(STRIP_MIN_WIDTH))
        pad_x, pad_y, gap = s(22), s(14), s(34)
        inner = width - 2 * pad_x - 2 * gap
        widths = [round(inner * f / 4.0) for f in (1.15, 1.6, 1.25)]
        xs = [pad_x, pad_x + widths[0] + gap, pad_x + widths[0] + widths[1] + 2 * gap]
        row_h = s(22)
        holes_h = row_h * (1 + max(len(predators), 1))
        height = 2 * pad_y + max(holes_h, 2 * row_h + s(4), u.title.get_linesize() + s(22))
        panel = u.glass((width, height))
        top = pad_y

        # families
        families, count, diversity = self._families(sim)
        x, w = xs[0], widths[0]
        u.text(panel, u.title, "Families", (x, top), ACCENT)
        u.text(
            panel,
            u.mono,
            f"{sim.num} stars · {diversity:.0%} diverse",
            (x + w, top + s(3)),
            MUTED,
            "topright",
        )
        bar_y = top + u.title.get_linesize() + s(8)
        self._family_bar(panel, (x, bar_y, w, s(10)), sim, families)

        # four genes, two columns
        means = gene_means(sim)
        x, w = xs[1], widths[1]
        cell_w = (w - s(26)) // 2
        for k, gi in enumerate(STRIP_GENES):
            cx = x + (k % 2) * (cell_w + s(26))
            cy = top + (k // 2) * (row_h + s(4))
            self._gene_row(panel, gi, means[gi], cx, cy, cell_w, s(96), s(52))

        # black holes
        self._hole_rows(panel, xs[2], top, widths[2], predators, collapsed)
        return panel

    def _gene_row(self, panel, gi, mean, x, y, width, label_w, value_w):
        u, s = self.ui, self.ui.px
        _name, default, lo, hi = config.GENOME_FIELDS[gi]
        mid = y + s(11)
        u.text(panel, u.body, GENES[gi][0], (x, mid), TEXT, "midleft")
        bar_w = width - label_w - value_w - s(10)
        bar = (x + label_w, mid - s(3), bar_w, s(6))
        u.gene_bar(panel, bar, _fraction(default, lo, hi), _fraction(mean, lo, hi))
        u.text(panel, u.mono, format_gene(gi, mean), (x + width, mid), MUTED, "midright")

    # ---- C: evolution timeline -------------------------------------------

    def draw_timeline(self, screen, sim, predators, collapsed, history, frame):
        u = self.ui
        sw, sh = screen.get_size()
        margin = u.px(24)
        panel = self._cached(
            "timeline", frame, lambda: self._build_timeline(sim, predators, collapsed, history)
        )
        panel = ui.fit(panel, int(sw * 0.45), sh - 2 * margin)
        rect = panel.get_rect(topright=(sw - margin, margin))
        screen.blit(panel, rect)
        return rect

    def _build_timeline(self, sim, predators, collapsed, history):
        u, s = self.ui, self.ui.px
        width, pad_x, pad_y = s(400), s(18), s(16)
        inner = width - 2 * pad_x
        row_h = s(22)
        head_h = u.caps.get_linesize() + s(6)
        chart_h = s(90)
        n_groups = len(GENE_GROUPS)
        height = (
            2 * pad_y
            + u.title.get_linesize()
            + s(8) + head_h + chart_h + s(6) + u.small.get_linesize()
            + s(12) + n_groups * (head_h + s(8)) + len(GENES) * row_h
            + s(12) + row_h * (1 + max(len(predators), 1))
            + s(10) + u.small.get_linesize()
        )  # fmt: skip
        panel = u.glass((width, height))
        x, y = pad_x, pad_y

        span = history.span_frames() / config.TARGET_FPS
        when = (
            "starting"
            if len(history) < 2
            else (f"last {span:.0f} s" if span < 90 else f"last {span / 60:.0f} min")
        )
        u.text(panel, u.title, "Evolution", (x, y), ACCENT)
        u.text(panel, u.mono, when, (x + inner, y + s(3)), MUTED, "topright")
        y += u.title.get_linesize() + s(8)

        # families over time
        u.heading(panel, "Families over time", (x, y))
        y += head_h
        families, count, diversity = self._families(sim)
        self._family_area(
            panel, pygame.Rect(x, y, inner, chart_h), history, [f for f, _ in families]
        )
        y += chart_h + s(6)
        largest = families[0][1] / max(sim.num, 1) if families else 0.0
        summary = f"{count} families · {diversity:.0%} diverse · largest {largest:.0%}"
        u.text(panel, u.small, summary, (x, y), MUTED)
        y += u.small.get_linesize() + s(12)

        # genes
        series = history.gene_series()
        means = gene_means(sim)
        label_w, value_w = s(126), s(56)
        for g, (group, members) in enumerate(GENE_GROUPS):
            y += s(8) if g else 0  # air above each group but the first
            u.heading(panel, group, (x, y))
            y += head_h
            for gi in members:
                mid = y + row_h // 2
                u.text(panel, u.body, GENES[gi][0], (x, mid), TEXT, "midleft")
                spark = pygame.Rect(
                    x + label_w, y + s(3), inner - label_w - value_w - s(8), row_h - s(6)
                )
                values = series[:, gi] if len(series) else np.array([means[gi]])
                self._sparkline(panel, spark, values, config.GENOME_FIELDS[gi][1])
                u.text(
                    panel, u.mono, format_gene(gi, means[gi]), (x + inner, mid), MUTED, "midright"
                )
                y += row_h
        y += s(12)

        y = self._hole_rows(panel, x, y, inner, predators, collapsed)
        y += s(10)

        # legend
        ly = y + u.small.get_linesize() // 2
        lx = x
        for kind, label in (("dash", "start value"), (UP, "above start"), (DOWN, "below start")):
            if kind == "dash":
                for dx in range(0, s(14), s(4)):
                    pygame.draw.line(
                        panel, ui.TICK, (lx + dx, ly), (lx + min(dx + s(2), s(14)), ly)
                    )
            else:
                pygame.draw.rect(panel, kind, (lx, ly - s(3), s(14), s(6)), border_radius=s(2))
            r = u.text(panel, u.small, label, (lx + s(20), ly), MUTED, "midleft")
            lx = r.right + s(16)
        return panel

    def _family_area(self, panel, rect, history, family_ids):
        """Stacked area of the current top families' shares over time."""
        pygame.draw.rect(panel, ui.TRACK, rect, border_radius=self.ui.px(3))
        if len(history) == 0 or not family_ids:
            return
        shares = history.family_shares(family_ids)
        if len(shares) == 1:
            shares = np.repeat(shares, 2, axis=0)
        n = len(shares)
        cols = min(n, rect.width)
        idx = np.linspace(0, n - 1, cols).round().astype(int)
        shares = shares[idx]
        xs = np.linspace(rect.left, rect.right - 1, cols)
        lower = np.zeros(cols)
        colours = [lineage_color(f) for f in family_ids] + [OTHER_FAMILIES]
        for j, colour in enumerate(colours):
            upper = lower + shares[:, j]
            top = rect.bottom - upper * rect.height
            bottom = rect.bottom - lower * rect.height
            points = list(zip(xs, top, strict=False)) + list(
                zip(xs[::-1], bottom[::-1], strict=False)
            )
            if (upper - lower).max() > 0:
                pygame.draw.polygon(panel, colour, points)
            lower = upper

    def _sparkline(self, panel, rect, values, start):
        u = self.ui
        lo = min(values.min(), start)
        hi = max(values.max(), start)
        if hi - lo < 1e-9:
            lo, hi = lo - 1.0, hi + 1.0
        pad = (hi - lo) * 0.12
        lo, hi = lo - pad, hi + pad

        def y_of(v):
            return rect.bottom - (v - lo) / (hi - lo) * rect.height

        sy = round(y_of(start))
        for dx in range(0, rect.width, u.px(5)):
            pygame.draw.line(
                panel, ui.TICK, (rect.x + dx, sy), (rect.x + min(dx + u.px(2), rect.width), sy)
            )
        colour = UP if values[-1] >= start else DOWN
        n = len(values)
        if n > 1:
            cols = min(n, rect.width)
            idx = np.linspace(0, n - 1, cols).round().astype(int)
            xs = np.linspace(rect.left, rect.right, cols)
            pygame.draw.aalines(
                panel, colour, False, list(zip(xs, y_of(values[idx]), strict=False))
            )
        pygame.draw.circle(panel, (255, 255, 255), (rect.right, round(y_of(values[-1]))), u.px(2.5))

    # ---- controls card ---------------------------------------------------

    def draw_help(self, screen):
        sw, sh = screen.get_size()
        panel = self._cache.get("help", (0, None))[1]
        if panel is None:
            panel = self._build_help()
            self._cache["help"] = (-(10**9), panel)  # never expires
        panel = ui.fit(panel, int(sw * 0.94), int(sh * 0.9))
        screen.blit(panel, panel.get_rect(center=(sw // 2, sh // 2)))

    def _build_help(self):
        u, s = self.ui, self.ui.px
        pad, col_w, gap, caps_w = s(26), s(340), s(36), s(84)
        row_h = s(30)
        rows = max(len(items) for _, items in CONTROLS)
        width = 2 * pad + len(CONTROLS) * col_w + (len(CONTROLS) - 1) * gap
        title_h = u.title.get_linesize() + s(14)
        head_h = u.caps.get_linesize() + s(8)
        height = 2 * pad + title_h + head_h + rows * row_h + s(10) + u.small.get_linesize()
        panel = u.glass((width, height))
        u.text(panel, u.title, "Controls", (pad, pad), ACCENT)
        y0 = pad + title_h
        for c, (group, items) in enumerate(CONTROLS):
            x = pad + c * (col_w + gap)
            u.heading(panel, group, (x, y0))
            y = y0 + head_h
            for keys, label in items:
                kx = x
                for key in keys:
                    r = u.key_cap(panel, key, (kx, y + s(4)))
                    kx = r.right + s(5)
                u.text(panel, u.body, label, (x + caps_w, r.centery), TEXT, "midleft")
                y += row_h
        foot = "Press H to close. Everything else lives in config.py."
        u.text(panel, u.small, foot, (pad, height - pad), MUTED, "bottomleft")
        return panel

    # ---- small text ------------------------------------------------------

    def draw_start_hint(self, screen, alpha, bottom, right=None):
        """The fading 'I panel  H controls' hint, right-aligned at ``right`` above ``bottom``."""
        u, s = self.ui, self.ui.px
        hint = pygame.Surface((s(260), s(30)), pygame.SRCALPHA)
        x = 0
        for key, label in (("I", "panel"), ("H", "controls")):
            r = u.key_cap(hint, key, (x, s(4)))
            r2 = u.text(hint, u.caps, label, (r.right + s(6), r.centery), MUTED, "midleft")
            x = r2.right + s(16)
        hint = hint.subsurface((0, 0, max(1, x - s(16)), hint.get_height())).copy()
        hint.set_alpha(alpha)
        sw, _ = screen.get_size()
        right = sw - s(30) if right is None else right
        screen.blit(hint, hint.get_rect(bottomright=(right, bottom)))

    def draw_visitor_hint(self, screen, bottom):
        u = self.ui
        sw, _ = screen.get_size()
        u.text(
            screen,
            u.body,
            "]  add      [  remove      black holes",
            (sw // 2, bottom),
            MUTED,
            "midbottom",
        )

    def draw_clock(self, screen, seconds, bottom):
        u = self.ui
        sw, _ = screen.get_size()
        t = int(seconds)
        text = f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"
        u.text(screen, u.big_mono, text, (sw - u.px(24), bottom), (140, 135, 130), "bottomright")
