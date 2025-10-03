"""Helpers for loading and rasterising SVG UI assets."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Mapping, Tuple

from . import layout

try:  # pragma: no cover - optional dependency
    import pygame
except ImportError:  # pragma: no cover - optional dependency
    pygame = None  # type: ignore

try:  # pragma: no cover - optional dependency
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtGui import QImage, QPainter
except ImportError:  # pragma: no cover - optional dependency
    QSvgRenderer = None  # type: ignore
    QImage = None  # type: ignore
    QPainter = None  # type: ignore


ASSET_FILES: Mapping[str, str] = {
    "board_tile": "board_tile.svg",
    "mirror": "mirror.svg",
    "goal": "goal.svg",
    "ui_button": "ui_button.svg",
}

DEFAULT_SIZES: Mapping[str, Tuple[int, int]] = {
    "board_tile": (layout.TILE_SIZE, layout.TILE_SIZE),
    "mirror": (layout.TILE_SIZE, layout.TILE_SIZE),
    "goal": (layout.TILE_SIZE, layout.TILE_SIZE),
    "ui_button": layout.UI_BUTTON_SIZE,
}


@dataclass
class AssetLibrary:
    """Stores rasterised versions of SVG assets."""

    surfaces: Dict[str, "pygame.Surface"]
    backend: str

    def __getitem__(self, key: str) -> "pygame.Surface":
        return self.surfaces[key]


def _ensure_pygame() -> None:
    if pygame is None:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "pygame is required to load UI assets. Install it with 'pip install pygame'."
        )


def _render_with_qt(svg_path: Path, size: Tuple[int, int]) -> "pygame.Surface":
    _ensure_pygame()
    if QSvgRenderer is None or QImage is None or QPainter is None:  # pragma: no cover
        raise RuntimeError(
            "PySide6 is required to rasterise SVG assets or install 'cairosvg'."
        )

    renderer = QSvgRenderer(str(svg_path))
    image = QImage(size[0], size[1], QImage.Format_ARGB32_Premultiplied)
    image.fill(0)

    painter = QPainter(image)
    renderer.render(painter)
    painter.end()

    ptr = image.bits()
    ptr.setsize(image.width() * image.height() * 4)
    buffer = bytes(ptr)
    surface = pygame.image.frombuffer(buffer, size, "BGRA").convert_alpha()
    return surface.copy()


def _render_with_cairosvg(svg_path: Path, size: Tuple[int, int]) -> "pygame.Surface":
    _ensure_pygame()
    try:  # pragma: no cover - optional dependency
        import cairosvg
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "Neither PySide6 nor cairosvg is installed; cannot rasterise SVG assets."
        ) from exc

    png_bytes = cairosvg.svg2png(
        url=str(svg_path), output_width=size[0], output_height=size[1]
    )
    surface = pygame.image.load(io.BytesIO(png_bytes)).convert_alpha()
    return surface


def rasterise_svg(svg_path: Path, size: Tuple[int, int]) -> "pygame.Surface":
    """Render a single SVG to the requested resolution."""

    if QSvgRenderer is not None:  # pragma: no cover - optional dependency
        return _render_with_qt(svg_path, size)
    return _render_with_cairosvg(svg_path, size)


def load_svg_assets(
    *,
    asset_root: Path | None = None,
    sizes: Mapping[str, Tuple[int, int]] | None = None,
    only: Iterable[str] | None = None,
) -> AssetLibrary:
    """Rasterise all required SVG assets for the UI layer."""

    _ensure_pygame()

    root = Path(asset_root or Path(__file__).resolve().parents[1] / "assets")
    targets = dict(DEFAULT_SIZES)
    if sizes:
        targets.update(sizes)

    if only is None:
        names = ASSET_FILES.keys()
    else:
        names = list(only)

    surfaces: Dict[str, "pygame.Surface"] = {}
    backend = "qt" if QSvgRenderer is not None else "cairosvg"

    for name in names:
        filename = ASSET_FILES.get(name)
        if filename is None:
            raise KeyError(f"Unknown asset '{name}'.")
        path = root / filename
        if not path.exists():
            raise FileNotFoundError(path)
        size = targets.get(name)
        if size is None:
            raise KeyError(f"No target size configured for asset '{name}'.")
        surfaces[name] = rasterise_svg(path, size)

    return AssetLibrary(surfaces=surfaces, backend=backend)
