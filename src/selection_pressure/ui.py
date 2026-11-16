"""
Shared look for every on-screen panel: colours, bundled fonts, sizes that
scale with the window, and the dark "glass" panel background.

Sizes are written in pixels for a 1080 px tall window and multiplied by
``UI.scale`` (window height / 1080, kept between 0.7 and 2.0).
"""

from __future__ import annotations

from importlib import resources

import pygame

# ---- colours (RGB) ----------------------------------------------------
TEXT = (220, 220, 232)
MUTED = (142, 142, 166)
ACCENT = (140, 180, 255)
UP = (60, 200, 180)  # gene evolved above its start value
DOWN = (220, 140, 50)  # gene evolved below its start value
MASS = (196, 90, 224)
HUNGRY_LOW = (122, 208, 106)
HUNGRY_HIGH = (240, 106, 58)
OTHER_FAMILIES = (74, 80, 102)
# pygame.draw replaces pixels instead of blending, so the panel colours
# below are pre-mixed with GLASS_FILL.
TRACK = (32, 32, 42, 200)  # empty bar or meter
TICK = (150, 150, 162, 230)
GLASS_FILL = (10, 10, 16, 184)
GLASS_EDGE = (40, 48, 70, 230)

MIN_SCALE, MAX_SCALE = 0.7, 2.0

_FONT_FILES = {
    "regular": "Inter-Regular.ttf",
    "semibold": "Inter-SemiBold.ttf",
    "mono": "JetBrainsMono-Regular.ttf",
}


def scale_for(height: int) -> float:
    return max(MIN_SCALE, min(MAX_SCALE, height / 1080))


def mix(a, b, t):
    """Linear blend of two colours, ``t`` in 0..1."""
    t = max(0.0, min(1.0, t))
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b, strict=False))


def hunger_color(fraction):
    return mix(HUNGRY_LOW, HUNGRY_HIGH, fraction)


class UI:
    """Fonts and measurements for the current window height."""

    def __init__(self, height: int, boost: float = 1.0):
        self._fonts: dict[tuple[str, int], pygame.font.Font] = {}
        self.boost = boost  # extra size, e.g. for a clip that will be scaled down
        self.resize(height)

    def resize(self, height: int) -> None:
        self.scale = min(MAX_SCALE, scale_for(height) * self.boost)
        s = self.px
        self.title = self.font("semibold", s(17))
        self.body = self.font("regular", s(15))
        self.small = self.font("regular", s(13))
        self.mono = self.font("mono", s(13))
        self.caps = self.font("mono", s(11))  # group headings, drawn in capitals
        self.big_mono = self.font("mono", s(30))  # kiosk clock

    def px(self, value: float) -> int:
        return max(1, round(value * self.scale))

    def font(self, face: str, size: int) -> pygame.font.Font:
        key = (face, size)
        if key not in self._fonts:
            path = resources.files(__package__) / "fonts" / _FONT_FILES[face]
            with resources.as_file(path) as file:
                self._fonts[key] = pygame.font.Font(str(file), size)
        return self._fonts[key]

    # ---- drawing helpers ------------------------------------------------

    def glass(self, size) -> pygame.Surface:
        """A transparent surface with the shared panel background and hairline."""
        w, h = size
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        r = self.px(8)
        pygame.draw.rect(panel, GLASS_FILL, (0, 0, w, h), border_radius=r)
        pygame.draw.rect(panel, GLASS_EDGE, (0, 0, w, h), width=1, border_radius=r)
        return panel

    def text(self, surface, font, text, pos, color=TEXT, anchor="topleft"):
        """Render ``text`` and blit it with the given rect anchor; returns its rect."""
        img = font.render(text, True, color)
        rect = img.get_rect(**{anchor: pos})
        surface.blit(img, rect)
        return rect

    def heading(self, surface, text, pos):
        return self.text(surface, self.caps, text.upper(), pos, MUTED)

    def meter(self, surface, rect, fraction, color):
        """A rounded track filled from the left to ``fraction``."""
        rect = pygame.Rect(rect)
        r = rect.height // 2
        pygame.draw.rect(surface, TRACK, rect, border_radius=r)
        fill = round(max(0.0, min(1.0, fraction)) * rect.width)
        if fill > 0:
            pygame.draw.rect(
                surface,
                color,
                (rect.x, rect.y, max(fill, rect.height), rect.height),
                border_radius=r,
            )

    def gene_bar(self, surface, rect, start, value):
        """Track with a tick at the start value, a fill to the mean and a dot on it.

        ``start`` and ``value`` are fractions of the gene's allowed range.
        """
        rect = pygame.Rect(rect)
        r = rect.height // 2
        pygame.draw.rect(surface, TRACK, rect, border_radius=r)
        sx = rect.x + round(max(0.0, min(1.0, start)) * rect.width)
        vx = rect.x + round(max(0.0, min(1.0, value)) * rect.width)
        if vx != sx:
            color = UP if vx > sx else DOWN
            pygame.draw.rect(
                surface, color, (min(sx, vx), rect.y, abs(vx - sx), rect.height), border_radius=r
            )
        tick = self.px(3)
        pygame.draw.line(surface, TICK, (sx, rect.y - tick), (sx, rect.bottom + tick - 1))
        pygame.draw.circle(surface, (255, 255, 255), (vx, rect.centery), self.px(4))

    def key_cap(self, surface, label, pos):
        """A small keyboard key; returns its rect."""
        img = self.caps.render(label, True, TEXT)
        pad = self.px(5)
        w = max(img.get_width() + 2 * pad, img.get_height() + pad)
        rect = pygame.Rect(pos[0], pos[1], w, img.get_height() + self.px(4))
        pygame.draw.rect(surface, (20, 20, 30, 220), rect, border_radius=self.px(3))
        pygame.draw.rect(surface, (68, 68, 90), rect, width=1, border_radius=self.px(3))
        surface.blit(img, img.get_rect(center=rect.center))
        return rect


def fit(panel: pygame.Surface, max_w: int, max_h: int) -> pygame.Surface:
    """Scale ``panel`` down (never up) so it fits inside ``max_w`` x ``max_h``."""
    w, h = panel.get_size()
    k = min(1.0, max_w / max(w, 1), max_h / max(h, 1))
    if k >= 1.0:
        return panel
    return pygame.transform.smoothscale(panel, (max(1, int(w * k)), max(1, int(h * k))))
