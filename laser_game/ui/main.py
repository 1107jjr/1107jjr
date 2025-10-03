"""Minimal pygame-powered UI layer for interactive laser level editing."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..game import LaserGame, LevelLoader, SolutionValidator


@dataclass
class PlacementTool:
    """Represents the current placement mode for the UI."""

    name: str
    mirror_orientation: str = "/"
    prism_spread: int = 1
    energy_drain: int = 1


class LaserGameUI:
    """Interactive user interface that maps mouse input to grid placements."""

    cell_size: int = 56
    grid_padding: int = 24
    side_panel_width: int = 260
    footer_height: int = 140

    background_color = (16, 18, 24)
    grid_color = (68, 74, 90)
    beam_color = (255, 92, 56)
    mirror_color = (120, 200, 255)
    prism_color = (255, 210, 48)
    energy_field_color = (155, 92, 255)
    emitter_color = (255, 120, 120)
    target_color = (120, 255, 160)

    def __init__(self, level_name: str = "level_intro") -> None:
        import pygame  # Imported lazily to keep tests lightweight when pygame is missing.

        self.pg = pygame
        self.pg.init()

        package_root = Path(__file__).resolve().parents[1]
        self.level_loader = LevelLoader(package_root / "levels")
        self.validator = SolutionValidator(self.level_loader, package_root / "solutions")

        self.level_name = level_name
        self.initial_level = self.level_loader.load(level_name)
        self.active_level = copy.deepcopy(self.initial_level)
        self.pending_placements: List[Dict[str, object]] = []

        self.tool = PlacementTool(name="mirror")
        self.status_message = "Links klicken: platzieren, Rechts klicken: entfernen."
        self.validation_status: Optional[bool] = None

        self._apply_pending_placements()

        total_width = (
            self.grid_padding
            + self.active_level.width * self.cell_size
            + self.side_panel_width
        )
        total_height = (
            self.grid_padding
            + self.active_level.height * self.cell_size
            + self.footer_height
        )
        self.screen = self.pg.display.set_mode((total_width, total_height))
        self.pg.display.set_caption("Laser Game UI")
        self.font = self.pg.font.SysFont("Fira Code", 18)
        self.small_font = self.pg.font.SysFont(None, 16)

        self.clock = self.pg.time.Clock()
        self.running = True

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------
    def run(self) -> None:
        while self.running:
            for event in self.pg.event.get():
                if event.type == self.pg.QUIT:
                    self.running = False
                elif event.type == self.pg.MOUSEBUTTONDOWN:
                    self._handle_mouse(event)
                elif event.type == self.pg.KEYDOWN:
                    self._handle_key(event)

            self._draw()
            self.clock.tick(60)

        self.pg.quit()

    def _handle_mouse(self, event) -> None:
        grid_position = self._grid_from_mouse(event.pos)
        if grid_position is None:
            return
        if event.button == 1:
            self._place_at(grid_position)
        elif event.button == 3:
            self._remove_at(grid_position)

    def _grid_from_mouse(self, pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        x, y = pos
        origin_x = self.grid_padding
        origin_y = self.grid_padding
        grid_width = self.active_level.width * self.cell_size
        grid_height = self.active_level.height * self.cell_size
        if not (origin_x <= x < origin_x + grid_width):
            return None
        if not (origin_y <= y < origin_y + grid_height):
            return None
        grid_x = (x - origin_x) // self.cell_size
        grid_y = (y - origin_y) // self.cell_size
        return int(grid_x), int(grid_y)

    def _handle_key(self, event) -> None:
        key = event.key
        if key == self.pg.K_ESCAPE:
            self.running = False
        elif key == self.pg.K_1:
            self.tool.name = "mirror"
            self._set_status("Werkzeug: Spiegel")
        elif key == self.pg.K_2:
            self.tool.name = "prism"
            self._set_status("Werkzeug: Prisma")
        elif key == self.pg.K_3:
            self.tool.name = "energy_field"
            self._set_status("Werkzeug: Energiefeld")
        elif key == self.pg.K_o:
            self.tool.mirror_orientation = "\\" if self.tool.mirror_orientation == "/" else "/"
            self._set_status(f"Spiegelorientierung: {self.tool.mirror_orientation}")
        elif key == self.pg.K_MINUS:
            if self.tool.name == "prism" and self.tool.prism_spread > 0:
                self.tool.prism_spread -= 1
                self._set_status(f"Prisma Spread: {self.tool.prism_spread}")
            if self.tool.name == "energy_field" and self.tool.energy_drain > 1:
                self.tool.energy_drain -= 1
                self._set_status(f"Energieentzug: {self.tool.energy_drain}")
        elif key in (self.pg.K_PLUS, self.pg.K_EQUALS):
            if self.tool.name == "prism":
                self.tool.prism_spread += 1
                self._set_status(f"Prisma Spread: {self.tool.prism_spread}")
            if self.tool.name == "energy_field":
                self.tool.energy_drain += 1
                self._set_status(f"Energieentzug: {self.tool.energy_drain}")
        elif key == self.pg.K_u:
            self.undo()
        elif key == self.pg.K_r:
            self.reset()
        elif key == self.pg.K_v:
            self.validate()

    # ------------------------------------------------------------------
    # Placement management
    # ------------------------------------------------------------------
    def _place_at(self, grid_position: Tuple[int, int]) -> None:
        placement = self._create_placement(grid_position)
        self.pending_placements = [
            p
            for p in self.pending_placements
            if tuple(p["position"]) != grid_position
        ]
        self.pending_placements.append(placement)
        self._set_status(
            f"Platziert {placement['type']} bei {tuple(placement['position'])}"
        )
        self._apply_pending_placements()

    def _remove_at(self, grid_position: Tuple[int, int]) -> None:
        before = len(self.pending_placements)
        self.pending_placements = [
            p
            for p in self.pending_placements
            if tuple(p["position"]) != grid_position
        ]
        if len(self.pending_placements) != before:
            self._set_status(f"Entfernt Platzierung bei {grid_position}")
            self._apply_pending_placements()

    def undo(self) -> None:
        if not self.pending_placements:
            self._set_status("Keine Platzierungen zum Rückgängig machen.")
            return
        removed = self.pending_placements.pop()
        self._set_status(
            f"Rückgängig: {removed['type']} bei {tuple(removed['position'])}"
        )
        self._apply_pending_placements()

    def reset(self) -> None:
        if not self.pending_placements:
            self._set_status("Keine temporären Platzierungen vorhanden.")
            return
        self.pending_placements.clear()
        self._set_status("Alle temporären Platzierungen entfernt.")
        self._apply_pending_placements()

    def validate(self) -> None:
        solution_data = {"placements": [dict(p) for p in self.pending_placements]}
        test_level = self.validator.apply_solution(
            copy.deepcopy(self.initial_level), solution_data
        )
        game = LaserGame(test_level)
        game.propagate()
        self.validation_status = game.level_complete()
        if self.validation_status:
            self._set_status("Alle Ziele erreicht!")
        else:
            self._set_status("Noch nicht alle Ziele erreicht.")

    def _create_placement(self, grid_position: Tuple[int, int]) -> Dict[str, object]:
        placement: Dict[str, object] = {
            "type": self.tool.name,
            "position": [grid_position[0], grid_position[1]],
        }
        if self.tool.name == "mirror":
            placement["orientation"] = self.tool.mirror_orientation
        elif self.tool.name == "prism":
            placement["spread"] = self.tool.prism_spread
        elif self.tool.name == "energy_field":
            placement["drain"] = self.tool.energy_drain
        return placement

    def _apply_pending_placements(self) -> None:
        self.validation_status = None
        base_level = copy.deepcopy(self.initial_level)
        solution = {"placements": [dict(p) for p in self.pending_placements]}
        self.active_level = self.validator.apply_solution(base_level, solution)
        self.game = LaserGame(self.active_level)
        self.game.propagate()

    def _set_status(self, message: str) -> None:
        self.status_message = message

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------
    def _draw(self) -> None:
        self.screen.fill(self.background_color)
        self._draw_grid()
        self._draw_elements()
        self._draw_beam()
        self._draw_sidebar()
        self._draw_footer()
        self.pg.display.flip()

    def _draw_grid(self) -> None:
        origin_x = self.grid_padding
        origin_y = self.grid_padding
        width = self.active_level.width * self.cell_size
        height = self.active_level.height * self.cell_size
        for i in range(self.active_level.width + 1):
            x = origin_x + i * self.cell_size
            self.pg.draw.line(
                self.screen,
                self.grid_color,
                (x, origin_y),
                (x, origin_y + height),
                1,
            )
        for j in range(self.active_level.height + 1):
            y = origin_y + j * self.cell_size
            self.pg.draw.line(
                self.screen,
                self.grid_color,
                (origin_x, y),
                (origin_x + width, y),
                1,
            )

    def _draw_elements(self) -> None:
        for emitter in self.active_level.emitters:
            self._draw_emitter(emitter.position)
        for position, target in self.active_level.targets.items():
            self._draw_target(position, target.required_energy)
        for position, mirror in self.active_level.mirrors.items():
            self._draw_mirror(position, mirror.orientation)
        for position, prism in self.active_level.prisms.items():
            self._draw_prism(position, prism.spread)
        for position, field in self.active_level.energy_fields.items():
            self._draw_energy_field(position, field.drain)

    def _draw_emitter(self, position: Tuple[int, int]) -> None:
        rect = self._cell_rect(position)
        self.pg.draw.rect(self.screen, self.emitter_color, rect, border_radius=6)

    def _draw_target(self, position: Tuple[int, int], required: int) -> None:
        center = self._cell_center(position)
        self.pg.draw.circle(self.screen, self.target_color, center, self.cell_size // 3, 2)
        text = self.small_font.render(str(required), True, self.target_color)
        text_rect = text.get_rect(center=center)
        self.screen.blit(text, text_rect)

    def _draw_mirror(self, position: Tuple[int, int], orientation: str) -> None:
        rect = self._cell_rect(position)
        if orientation == "/":
            start = rect.topright
            end = rect.bottomleft
        else:
            start = rect.topleft
            end = rect.bottomright
        self.pg.draw.line(self.screen, self.mirror_color, start, end, 3)

    def _draw_prism(self, position: Tuple[int, int], spread: int) -> None:
        rect = self._cell_rect(position)
        points = [
            (rect.centerx, rect.top + 6),
            (rect.right - 6, rect.bottom - 6),
            (rect.left + 6, rect.bottom - 6),
        ]
        self.pg.draw.polygon(self.screen, self.prism_color, points)
        text = self.small_font.render(str(spread), True, self.background_color)
        text_rect = text.get_rect(center=(rect.centerx, rect.centery + 10))
        self.screen.blit(text, text_rect)

    def _draw_energy_field(self, position: Tuple[int, int], drain: int) -> None:
        rect = self._cell_rect(position)
        surface = self.pg.Surface((rect.width, rect.height), self.pg.SRCALPHA)
        surface.fill((*self.energy_field_color, 120))
        self.screen.blit(surface, rect)
        text = self.small_font.render(str(drain), True, (240, 240, 255))
        text_rect = text.get_rect(center=rect.center)
        self.screen.blit(text, text_rect)

    def _draw_beam(self) -> None:
        origin_x = self.grid_padding
        origin_y = self.grid_padding
        for segment in self.game.path:
            start = self._cell_center(segment.start)
            end = self._cell_center(segment.end)
            self.pg.draw.line(self.screen, self.beam_color, start, end, 4)

    def _draw_sidebar(self) -> None:
        sidebar_x = self.grid_padding + self.active_level.width * self.cell_size + 24
        y = self.grid_padding
        header = self.font.render("Werkzeuge", True, (220, 220, 230))
        self.screen.blit(header, (sidebar_x, y))
        y += 32
        for label in [
            "[1] Spiegel",
            "[2] Prisma",
            "[3] Energiefeld",
            "[O] Spiegel drehen",
            "[+/-] Werte anpassen",
            "[U] Undo, [R] Reset, [V] Validieren",
        ]:
            text = self.small_font.render(label, True, (200, 200, 210))
            self.screen.blit(text, (sidebar_x, y))
            y += 22

        current_tool = f"Aktiv: {self.tool.name}"
        tool_text = self.small_font.render(current_tool, True, (255, 255, 255))
        self.screen.blit(tool_text, (sidebar_x, y + 10))
        y += 40

        mirror_text = self.small_font.render(
            f"Spiegel: {self.tool.mirror_orientation}", True, (180, 220, 255)
        )
        prism_text = self.small_font.render(
            f"Prisma Spread: {self.tool.prism_spread}", True, (255, 230, 180)
        )
        drain_text = self.small_font.render(
            f"Energieentzug: {self.tool.energy_drain}", True, (210, 190, 255)
        )
        self.screen.blit(mirror_text, (sidebar_x, y))
        self.screen.blit(prism_text, (sidebar_x, y + 22))
        self.screen.blit(drain_text, (sidebar_x, y + 44))

    def _draw_footer(self) -> None:
        y = self.grid_padding + self.active_level.height * self.cell_size + 20
        status = self.small_font.render(self.status_message, True, (230, 230, 240))
        self.screen.blit(status, (self.grid_padding, y))
        y += 26
        placement_info = f"Platzierungen: {len(self.pending_placements)}"
        info_text = self.small_font.render(placement_info, True, (200, 200, 210))
        self.screen.blit(info_text, (self.grid_padding, y))
        y += 26
        if self.validation_status is True:
            validation_text = "Status: Ziele erreicht"
            color = (120, 255, 160)
        elif self.validation_status is False:
            validation_text = "Status: Ziele noch offen"
            color = (255, 160, 120)
        else:
            validation_text = "Status: Noch nicht validiert"
            color = (200, 200, 210)
        text = self.small_font.render(validation_text, True, color)
        self.screen.blit(text, (self.grid_padding, y))

    def _cell_rect(self, position: Tuple[int, int]):
        origin_x = self.grid_padding
        origin_y = self.grid_padding
        x = origin_x + position[0] * self.cell_size
        y = origin_y + position[1] * self.cell_size
        return self.pg.Rect(x + 2, y + 2, self.cell_size - 4, self.cell_size - 4)

    def _cell_center(self, position: Tuple[int, int]) -> Tuple[int, int]:
        rect = self._cell_rect(position)
        return rect.centerx, rect.centery


def run(level_name: str = "level_intro") -> None:
    """Entry point helper used by external callers."""

    ui = LaserGameUI(level_name=level_name)
    ui.run()


if __name__ == "__main__":
    run()
