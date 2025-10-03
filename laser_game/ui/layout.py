"""Layout constants for the laser game UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

# Tile metrics
TILE_SIZE: int = 96
GRID_PADDING: int = 24
BOARD_OUTER_PADDING: int = 32

# UI panel metrics
UI_PANEL_WIDTH: int = 320
UI_PANEL_PADDING: int = 24
UI_PANEL_SPACING: int = 18
UI_PANEL_HEADER_HEIGHT: int = 48
UI_BUTTON_SIZE: Tuple[int, int] = (80, 80)

# Tooltip metrics
TOOLTIP_HEIGHT: int = 120
TOOLTIP_PADDING: int = 16

# Colors expressed as RGB tuples
BACKGROUND_COLOR: Tuple[int, int, int] = (12, 14, 26)
BOARD_BACKGROUND_COLOR: Tuple[int, int, int] = (20, 24, 44)
PANEL_BACKGROUND_COLOR: Tuple[int, int, int] = (32, 36, 60)
TOOLTIP_BACKGROUND_COLOR: Tuple[int, int, int] = (40, 44, 72)
GRID_LINE_COLOR: Tuple[int, int, int] = (58, 64, 96)
TEXT_COLOR: Tuple[int, int, int] = (232, 236, 244)
ACCENT_COLOR: Tuple[int, int, int] = (255, 94, 0)

# Rendering order for composed scenes
DRAW_ORDER = ("board", "ui_panel", "tooltips")


@dataclass(frozen=True)
class BoardGeometry:
    """Pixel rectangles for the major UI regions."""

    board: Tuple[int, int, int, int]
    panel: Tuple[int, int, int, int]
    tooltip: Tuple[int, int, int, int]
    window: Tuple[int, int]


def compute_geometry(level_width: int, level_height: int) -> BoardGeometry:
    """Compute useful rectangles for rendering the game window."""

    board_width = level_width * TILE_SIZE
    board_height = level_height * TILE_SIZE

    board_x = BOARD_OUTER_PADDING
    board_y = BOARD_OUTER_PADDING

    panel_x = board_x + board_width + GRID_PADDING
    panel_y = board_y

    tooltip_width = (
        board_width
        + GRID_PADDING
        + UI_PANEL_WIDTH
    )

    tooltip_x = board_x
    tooltip_y = board_y + board_height + GRID_PADDING

    window_width = tooltip_x + tooltip_width + BOARD_OUTER_PADDING
    window_height = tooltip_y + TOOLTIP_HEIGHT + BOARD_OUTER_PADDING

    board_rect = (board_x, board_y, board_width, board_height)
    panel_rect = (panel_x, panel_y, UI_PANEL_WIDTH, board_height)
    tooltip_rect = (tooltip_x, tooltip_y, tooltip_width, TOOLTIP_HEIGHT)

    return BoardGeometry(
        board=board_rect,
        panel=panel_rect,
        tooltip=tooltip_rect,
        window=(window_width, window_height),
    )
