"""
Live tuning panel for the particle black holes.

A small pure-pygame panel of sliders and toggles, each bound directly to a
``config`` attribute, so a change takes effect on the next frame.  Press G to
show or hide it, M (or the Style button) to switch between the particle and
classic styles, and D to print the current values; paste them into
``config.py`` to keep them.
"""

from __future__ import annotations

import pygame

from . import config, ui

# (attr, label, kind, lo, hi)  kind in {"bool", "float"}
PARTICLE_CONTROLS = [
    ("BH_PD_INNER", "Inner / hole px", "float", 20.0, 200.0),
    ("BH_PD_OUTER", "Outer px", "float", 80.0, 500.0),
    ("BH_PD_INCLINATION", "Tilt (0=face-on)", "float", 0.0, 90.0),
    ("BH_PD_THICKNESS", "Disk thickness", "float", 0.02, 0.30),
    ("BH_PD_SPIN", "Spin speed", "float", 0.0, 3.0),
    ("BH_PD_BRIGHTNESS", "Exposure", "float", 0.0, 1.0),
    ("BH_PD_LUNGE_SCALE", "Lunge grow", "bool", 0, 1),
    ("BH_PD_LUNGE_SCALE_AMOUNT", "Lunge amount", "float", 1.0, 2.0),
    ("BH_PD_HALO_STRENGTH", "Halo keep (1=off)", "float", 0.0, 1.0),
    ("BH_PD_HALO_REACH", "Halo reach (xR)", "float", 1.0, 2.5),
    ("BH_PD_DARK_CENTER", "Dark center (xIn)", "float", 0.5, 1.5),
    ("BH_SCALE_SMOOTHING", "Grow smoothing", "float", 0.02, 0.40),
]

CONTROLS = {"particle": PARTICLE_CONTROLS, "classic": []}
_STYLE_KEY = "__STYLE__"


class TuningPanel:
    """Immediate-mode slider/toggle panel bound to the config BH_* values.

    ``on_style_click`` is called when the Style button is clicked; the app
    owns the current style and passes it to :meth:`draw`.
    """

    def __init__(self, on_style_click):
        self.visible = False
        self._on_style_click = on_style_click
        self._drag_attr = None
        self._rects = {}  # attr -> (kind, hitbox, track_rect), screen coords
        self._bounds = pygame.Rect(0, 0, 0, 0)

    def toggle(self):
        self.visible = not self.visible
        self._drag_attr = None

    # ------------------------------------------------------------
    def handle_event(self, event):
        """Handle a mouse event; returns True when the panel consumed it."""
        if not self.visible:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return self._mouse_down(event.pos)
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._drag_attr = None
        elif event.type == pygame.MOUSEMOTION and self._drag_attr is not None:
            entry = self._rects.get(self._drag_attr)
            if entry is None:  # the style changed mid-drag
                self._drag_attr = None
                return False
            self._apply_slider(self._drag_attr, entry[2], event.pos[0])
            return True
        return False

    def _mouse_down(self, pos):
        if not self._bounds.collidepoint(pos):
            return False
        for attr, (kind, hitbox, track) in self._rects.items():
            if attr == _STYLE_KEY:
                if hitbox.collidepoint(pos):
                    self._on_style_click()
                    return True
            elif kind == "bool":
                if hitbox.collidepoint(pos):
                    setattr(config, attr, not bool(getattr(config, attr)))
                    return True
            elif track.collidepoint(pos) or hitbox.collidepoint(pos):
                self._drag_attr = attr
                self._apply_slider(attr, track, pos[0])
                return True
        return True  # clicks on the panel background never reach the piece

    @staticmethod
    def _apply_slider(attr, track, mouse_x):
        lo, hi = _range(attr)
        frac = max(0.0, min(1.0, (mouse_x - track.x) / max(track.width, 1)))
        setattr(config, attr, lo + frac * (hi - lo))

    # ------------------------------------------------------------
    @staticmethod
    def dump(style):
        """Print the active style's values in config.py syntax."""
        print(f"\n  # --- black hole tuning (style={style}); paste into config.py ---")
        print(f'  BLACK_HOLE_STYLE = "{style}"')
        for attr, _, kind, _, _ in CONTROLS.get(style, []):
            val = getattr(config, attr)
            print(f"  {attr} = {bool(val)}" if kind == "bool" else f"  {attr} = {float(val):.3f}")
        print()

    # ------------------------------------------------------------
    def draw(self, surface, style, ui_, note=""):
        """Draw the panel in the top-right corner, sized by ``ui_`` (a ``ui.UI``)."""
        if not self.visible:
            return
        s = ui_.px
        controls = CONTROLS.get(style, [])
        width, pad, row_h = s(400), s(18), s(30)
        header_h = pad + ui_.title.get_linesize() + s(8)
        rows = len(controls) + 1 + (1 if note else 0)  # + style button (+ note)
        height = header_h + rows * row_h + pad
        sw, _ = surface.get_size()
        ox, oy = sw - width - s(24), s(24)
        self._bounds = pygame.Rect(ox, oy, width, height)
        self._rects = {}

        panel = ui_.glass((width, height))
        ui_.text(panel, ui_.title, "Black hole tuning", (pad, pad), ui.ACCENT)
        ui_.text(
            panel, ui_.caps, "D PRINTS VALUES", (width - pad, pad + s(4)), ui.MUTED, "topright"
        )

        track_x = pad + s(150)
        value_w = s(46)
        track_w = width - track_x - pad - value_w
        y = header_h

        def label(text, color=ui.TEXT):
            ui_.text(panel, ui_.body, text, (pad, y + row_h // 2), color, "midleft")

        # --- Style switch button ---
        label("Style")
        btn = pygame.Rect(track_x, y + s(4), track_w + value_w, row_h - s(8))
        pygame.draw.rect(panel, (34, 44, 66, 230), btn, border_radius=s(4))
        pygame.draw.rect(panel, (90, 120, 180), btn, width=1, border_radius=s(4))
        ui_.text(panel, ui_.small, f"{style}  (click or M)", btn.center, (200, 220, 255), "center")
        self._rects[_STYLE_KEY] = ("btn", btn.move(ox, oy), btn.move(ox, oy))
        y += row_h

        if note:
            label(note, ui.DOWN)
            y += row_h

        # --- Active controls ---
        for attr, text, kind, lo, hi in controls:
            val = getattr(config, attr)
            label(text)
            mid = y + row_h // 2
            if kind == "bool":
                box = pygame.Rect(track_x, mid - s(9), s(18), s(18))
                pygame.draw.rect(panel, ui.TRACK, box, border_radius=s(3))
                pygame.draw.rect(panel, (90, 100, 130), box, width=1, border_radius=s(3))
                if val:
                    pygame.draw.rect(panel, ui.UP, box.inflate(-s(8), -s(8)), border_radius=s(2))
                self._rects[attr] = ("bool", box.move(ox, oy), box.move(ox, oy))
            else:
                frac = max(0.0, min(1.0, (float(val) - lo) / max(hi - lo, 1e-9)))
                track = pygame.Rect(track_x, mid - s(3), track_w - s(8), s(6))
                ui_.meter(panel, track, frac, ui.ACCENT)
                knob_x = round(track.x + frac * track.width)
                knob = pygame.Rect(knob_x - s(5), mid - s(8), s(10), s(16))
                pygame.draw.rect(panel, (220, 230, 255), knob, border_radius=s(3))
                ui_.text(
                    panel, ui_.mono, f"{float(val):.2f}", (width - pad, mid), ui.MUTED, "midright"
                )
                self._rects[attr] = ("float", knob.move(ox, oy), track.move(ox, oy))
            y += row_h

        surface.blit(panel, (ox, oy))


def _range(attr):
    for controls in CONTROLS.values():
        for a, _, _, lo, hi in controls:
            if a == attr:
                return lo, hi
    return 0.0, 1.0
