"""Lightweight pygame stub used for automated tests.

When the real pygame package is available it is preferred automatically, so
regular runtime code can rely on the full SDL implementation.  Tests that rely
on the deterministic stub can force it via the
`LASER_GAME_FORCE_PYGAME_STUB=1` environment variable.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import sys
from pathlib import Path

_STUB_ROOT = Path(__file__).resolve().parent
_FORCE_STUB = os.environ.get("LASER_GAME_FORCE_PYGAME_STUB") == "1"
_SELF_MODULE = sys.modules.get(__name__)


def _load_real_module():
    """Attempt to load the real pygame module from site-packages."""

    search_paths = []
    for entry in sys.path:
        try:
            resolved = Path(entry).resolve()
        except Exception:
            search_paths.append(entry)
            continue
        if resolved == _STUB_ROOT.parent:
            continue
        search_paths.append(entry)
    spec = importlib.machinery.PathFinder.find_spec("pygame", search_paths)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        sys.modules[__name__] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            if _SELF_MODULE is not None:
                sys.modules[__name__] = _SELF_MODULE
            else:
                sys.modules.pop(__name__, None)
            raise
        return module
    return None


_real_module = None
if not _FORCE_STUB:
    try:
        _real_module = _load_real_module()
    except Exception:
        _real_module = None


if _real_module is not None:
    sys.modules[__name__] = _real_module
    globals().update(_real_module.__dict__)
    __all__ = getattr(_real_module, "__all__", [])
else:
    from dataclasses import dataclass
    from typing import Iterable, List, Sequence, Tuple

    Color = Tuple[int, int, int]

    class Surface:
        def __init__(self, size: Sequence[int]) -> None:
            self.width, self.height = size
            self.pixels: List[List[Color]] = [
                [(0, 0, 0) for _ in range(self.width)] for _ in range(self.height)
            ]

        def fill(self, color: Color, rect: "Rect" | None = None) -> None:
            if rect is None:
                for row in self.pixels:
                    for x in range(self.width):
                        row[x] = tuple(color)
                return
            x0 = max(rect.x, 0)
            y0 = max(rect.y, 0)
            x1 = min(rect.x + rect.width, self.width)
            y1 = min(rect.y + rect.height, self.height)
            for y in range(y0, y1):
                for x in range(x0, x1):
                    self.pixels[y][x] = tuple(color)

        def blit(self, other: "Surface", rect: "Rect") -> None:
            x_start = rect.x
            y_start = rect.y
            for y in range(other.height):
                ty = y_start + y
                if not (0 <= ty < self.height):
                    continue
                for x in range(other.width):
                    tx = x_start + x
                    if 0 <= tx < self.width:
                        self.pixels[ty][tx] = other.pixels[y][x]

        def get_rect(self) -> "Rect":
            return Rect(0, 0, self.width, self.height)

    class Rect:
        def __init__(self, x: int, y: int, width: int, height: int) -> None:
            self.x = x
            self.y = y
            self.width = width
            self.height = height

        @property
        def center(self) -> Tuple[int, int]:
            return (self.x + self.width // 2, self.y + self.height // 2)

        @center.setter
        def center(self, value: Tuple[int, int]) -> None:
            cx, cy = value
            self.x = cx - self.width // 2
            self.y = cy - self.height // 2

    def draw_rect(surface: Surface, color: Color, rect: Rect, width: int = 0) -> None:
        for x in range(rect.x, rect.x + rect.width):
            if 0 <= x < surface.width:
                if 0 <= rect.y < surface.height:
                    surface.pixels[rect.y][x] = tuple(color)
                bottom = rect.y + rect.height - 1
                if 0 <= bottom < surface.height:
                    surface.pixels[bottom][x] = tuple(color)
        for y in range(rect.y, rect.y + rect.height):
            if 0 <= y < surface.height:
                if 0 <= rect.x < surface.width:
                    surface.pixels[y][rect.x] = tuple(color)
                right = rect.x + rect.width - 1
                if 0 <= right < surface.width:
                    surface.pixels[y][right] = tuple(color)

    def image_tostring(surface: Surface, mode: str) -> bytes:
        if mode != "RGB":
            raise ValueError("Only RGB mode is supported in the stub")
        data = bytearray()
        for row in surface.pixels:
            for pixel in row:
                data.extend(pixel)
        return bytes(data)

    class Font:
        def __init__(self, name: str | None, size: int) -> None:
            self.size = size

        def render(self, text: str, antialias: bool, color: Color) -> Surface:
            width = max(1, len(text) * self.size // 2)
            height = max(1, self.size)
            surf = Surface((width, height))
            surf.fill(color)
            return surf

    class FontModule:
        def init(self) -> None:  # pragma: no cover - stub behaviour
            pass

        def quit(self) -> None:  # pragma: no cover
            pass

        def Font(self, name: str | None, size: int) -> Font:  # noqa: N802
            return Font(name, size)

        def get_default_font(self) -> str:
            return "default"

    class DisplayModule:
        def __init__(self) -> None:
            self._surface: Surface | None = None

        def init(self) -> None:  # pragma: no cover
            pass

        def set_mode(self, size: Sequence[int]) -> Surface:
            self._surface = Surface(size)
            return self._surface

        def flip(self) -> None:  # pragma: no cover
            pass

    @dataclass
    class Event:
        type: int
        button: int | None = None
        pos: Tuple[int, int] | None = None

    class EventModule:
        def Event(self, event_type: int, **attributes) -> Event:  # noqa: N802
            return Event(type=event_type, **attributes)

    display = DisplayModule()
    font = FontModule()
    event = EventModule()

    MOUSEBUTTONDOWN = 1

    class DrawModule:
        def rect(self, surface: Surface, color: Color, rect: Rect, width: int = 0):
            draw_rect(surface, color, rect, width)

    draw = DrawModule()

    class ImageModule:
        def tostring(self, surface: Surface, mode: str) -> bytes:
            return image_tostring(surface, mode)

    image = ImageModule()

    def quit() -> None:  # pragma: no cover
        display._surface = None

    __all__ = [
        "Surface",
        "Rect",
        "display",
        "font",
        "draw",
        "event",
        "image",
        "Font",
        "Event",
        "MOUSEBUTTONDOWN",
        "quit",
    ]
