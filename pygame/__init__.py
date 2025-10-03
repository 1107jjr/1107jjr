"""Lightweight pygame stub for the automated tests.

The real project treats pygame as an optional dependency.  The CI environment
for these kata-style exercises does not provide pygame, therefore a very small
stub is provided so that the UI tests can run without the native library.
"""

from __future__ import annotations

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
    # Draw horizontal lines
    for x in range(rect.x, rect.x + rect.width):
        if 0 <= x < surface.width:
            if 0 <= rect.y < surface.height:
                surface.pixels[rect.y][x] = tuple(color)
            bottom = rect.y + rect.height - 1
            if 0 <= bottom < surface.height:
                surface.pixels[bottom][x] = tuple(color)
    # Draw vertical lines
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

    def Font(self, name: str | None, size: int) -> Font:  # noqa: N802 - mimic pygame
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


def draw_rect_wrapper(surface: Surface, color: Color, rect: Rect, width: int = 0):
    draw_rect(surface, color, rect, width)


class DrawModule:
    def rect(self, surface: Surface, color: Color, rect: Rect, width: int = 0):
        draw_rect_wrapper(surface, color, rect, width)


draw = DrawModule()


def image_tostring_wrapper(surface: Surface, mode: str) -> bytes:
    return image_tostring(surface, mode)


class ImageModule:
    def tostring(self, surface: Surface, mode: str) -> bytes:
        return image_tostring_wrapper(surface, mode)


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
