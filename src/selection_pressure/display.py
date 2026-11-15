"""Display discovery and platform helpers.

Windows needs two extras for a reliable projector setup: per-monitor DPI
awareness (otherwise pygame works in scaled logical pixels) and the real
desktop position of each monitor (so a borderless window can be placed on
the right screen).  Everything here is a no-op on other platforms.
"""

from __future__ import annotations

import ctypes
import os
import sys

import pygame

IS_WINDOWS = sys.platform == "win32"

# (x, y, width, height) in physical pixels
Rect = tuple[int, int, int, int]


def enable_dpi_awareness() -> None:
    """Ask Windows for physical pixels.  Must run before ``pygame.init()``."""
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor aware
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # older Windows
        except (AttributeError, OSError):
            pass


def minimize_console() -> None:
    """Minimise the console window so it cannot steal focus in a kiosk setup."""
    if not IS_WINDOWS:
        return
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
    except (AttributeError, OSError):
        pass


def _windows_monitor_rects() -> list[Rect]:
    import ctypes.wintypes

    rects: list[Rect] = []
    callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.c_ulong, ctypes.c_ulong,
        ctypes.POINTER(ctypes.wintypes.RECT), ctypes.c_double)

    def _collect(_monitor, _hdc, rect_ptr, _data):
        r = rect_ptr.contents
        rects.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True

    ctypes.windll.user32.EnumDisplayMonitors(None, None, callback_type(_collect), 0)
    return rects


def list_monitors() -> list[Rect]:
    """Return every monitor as ``(x, y, w, h)``.  Requires ``pygame.init()``."""
    if IS_WINDOWS:
        try:
            rects = _windows_monitor_rects()
            if rects:
                return rects
        except (AttributeError, OSError, ValueError):
            pass
    # Other platforms: sizes only, positions unknown.
    return [(0, 0, w, h) for w, h in pygame.display.get_desktop_sizes()]


def choose_display(monitors: list[Rect], requested: str) -> int:
    """Pick a monitor index.

    ``requested`` is ``"primary"``, ``"auto"`` (largest non-primary landscape
    screen, i.e. the projector) or an index such as ``"1"``.
    """
    if requested == "auto":
        secondary = [i for i, (x, y, _, _) in enumerate(monitors) if (x, y) != (0, 0)]
        if not secondary:
            return 0
        return max(secondary, key=lambda i: (monitors[i][2] >= monitors[i][3],
                                             monitors[i][2] * monitors[i][3]))
    if requested == "primary":
        return next((i for i, (x, y, _, _) in enumerate(monitors) if (x, y) == (0, 0)), 0)
    index = int(requested)
    if not 0 <= index < len(monitors):
        raise ValueError(
            f"display {index} does not exist; found {len(monitors)} "
            f"(valid: 0-{len(monitors) - 1})")
    return index


def place_window(x: int, y: int) -> None:
    """Position the next window created by ``pygame.display.set_mode``."""
    os.environ["SDL_VIDEO_WINDOW_POS"] = f"{x},{y}"
