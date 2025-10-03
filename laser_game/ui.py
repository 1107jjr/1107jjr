"""Minimal pygame based UI helpers for headless testing.

This module intentionally keeps the rendering deterministic so it can be
exercised in automated tests using the SDL ``dummy`` video driver.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


# Pygame is optional for the library but required for the UI helpers.  The
# import is performed lazily in ``ensure_pygame`` so test environments can
# control the SDL configuration (e.g. select the ``dummy`` video driver).
_PYGAME = None


def ensure_pygame():
    global _PYGAME
    if _PYGAME is None:
        # Tests configure ``SDL_VIDEODRIVER`` to ``dummy`` before importing
        # pygame.  We use ``setdefault`` so that real applications can pick a
        # different driver if required.
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        _PYGAME = __import__("pygame")
        _PYGAME.display.init()
        _PYGAME.font.init()
    return _PYGAME


@dataclass
class ToolSelection:
    """Current tool selection within the UI."""

    tool_type: str = "mirror"
    options: Dict[str, object] = None

    def as_placement(self, position: Tuple[int, int]) -> Dict[str, object]:
        placement: Dict[str, object] = {"type": self.tool_type, "position": position}
        if self.options:
            placement.update(self.options)
        return placement


class LaserGameUI:
    """Very small pygame driven UI wrapper used for automated tests."""

    def __init__(
        self,
        game,
        *,
        cell_size: int = 32,
        surface=None,
        use_display: bool = False,
    ) -> None:
        pygame = ensure_pygame()
        self.game = game
        self.cell_size = cell_size
        width = self.game.level.width * cell_size
        height = self.game.level.height * cell_size
        self.surface = surface or pygame.Surface((width, height))
        self.screen = None
        if use_display:
            self.screen = pygame.display.set_mode((width, height))
        self.pending_placements: List[Dict[str, object]] = []
        self.tool = ToolSelection(options={"orientation": "/"})
        # Fonts are initialised with the default pygame font to keep rendering
        # deterministic across environments.
        self.font = pygame.font.Font(pygame.font.get_default_font(), 14)

    # ------------------------------------------------------------------
    # Input handling
    def select_tool(self, tool_type: str, **options: object) -> None:
        self.tool = ToolSelection(tool_type=tool_type, options=options or None)

    def process_events(self, events: Iterable[object]) -> None:
        pygame = ensure_pygame()
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_click(event.pos)

    def _grid_from_pixel(self, pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        x, y = pos
        grid_x = x // self.cell_size
        grid_y = y // self.cell_size
        if not self.game.level.inside((grid_x, grid_y)):
            return None
        return grid_x, grid_y

    def _handle_click(self, pos: Tuple[int, int]) -> None:
        grid_pos = self._grid_from_pixel(pos)
        if grid_pos is None:
            return
        placement = self.tool.as_placement(grid_pos)
        self.pending_placements.append(placement)

    def flush_pending_to_game(self) -> None:
        if not self.pending_placements:
            return
        self.game.queue_pending_placements(self.pending_placements)
        self.pending_placements.clear()

    # ------------------------------------------------------------------
    # Rendering helpers
    def render(self):
        pygame = ensure_pygame()
        self.surface.fill((24, 24, 30))
        self._draw_grid()
        self._draw_placements()
        if self.screen:
            self.screen.blit(self.surface, (0, 0))
            pygame.display.flip()
        return self.surface

    def _draw_grid(self) -> None:
        pygame = ensure_pygame()
        width = self.game.level.width
        height = self.game.level.height
        for x in range(width):
            for y in range(height):
                rect = pygame.Rect(
                    x * self.cell_size,
                    y * self.cell_size,
                    self.cell_size,
                    self.cell_size,
                )
                pygame.draw.rect(self.surface, (40, 40, 55), rect, 1)

    def _draw_placements(self) -> None:
        pygame = ensure_pygame()
        for position, mirror in self.game.level.mirrors.items():
            self._fill_cell(position, (80, 140, 255))
            self._draw_text(position, mirror.orientation)
        for position, prism in self.game.level.prisms.items():
            self._fill_cell(position, (255, 200, 80))
            self._draw_text(position, str(prism.spread))

    def _fill_cell(self, position: Tuple[int, int], color: Tuple[int, int, int]) -> None:
        pygame = ensure_pygame()
        rect = pygame.Rect(
            position[0] * self.cell_size,
            position[1] * self.cell_size,
            self.cell_size,
            self.cell_size,
        )
        self.surface.fill(color, rect)

    def _draw_text(self, position: Tuple[int, int], text: str) -> None:
        pygame = ensure_pygame()
        # Render text centred in the cell.  Using the default font makes the
        # output deterministic across systems.
        label = self.font.render(text, True, (0, 0, 0))
        rect = label.get_rect()
        rect.center = (
            position[0] * self.cell_size + self.cell_size // 2,
            position[1] * self.cell_size + self.cell_size // 2,
        )
        self.surface.blit(label, rect)


__all__ = ["LaserGameUI"]

