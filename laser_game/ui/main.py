"""Interactive UI for visualising laser levels using pygame."""

from __future__ import annotations

import argparse
import os
import time
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import pygame

from ..game import (
    Amplifier,
    BeamSegment,
    Direction,
    LaserGame,
    Level,
    LevelLoader,
    Mirror,
    Splitter,
    Bomb,
)

ASSET_ENV_VAR = "LASER_GAME_ASSET_ROOT"
LEVEL_ENV_VAR = "LASER_GAME_LEVEL_ROOT"


@dataclass(frozen=True)
class UIDirectories:
    """Bundle with resolved directories required by the UI."""

    asset_root: Path
    level_root: Path


def _default_asset_root() -> Path:
    return Path(__file__).resolve().parents[1] / "assets"


def _default_level_root() -> Path:
    return Path(__file__).resolve().parents[1] / "levels"


def _read_directory(env_var: str, fallback: Path) -> Path:
    value = os.environ.get(env_var)
    if value:
        return Path(value).expanduser()
    return fallback


def resolve_directories(check_exists: bool = True) -> UIDirectories:
    """Resolve UI directories using environment variables.

    Parameters
    ----------
    check_exists:
        When *True*, raise :class:`FileNotFoundError` if a resolved directory does
        not exist on disk. Disable this in contexts where you want to inspect the
        chosen paths without touching the filesystem.
    """

    asset_root = _read_directory(ASSET_ENV_VAR, _default_asset_root())
    level_root = _read_directory(LEVEL_ENV_VAR, _default_level_root())

    if check_exists:
        missing = [path for path in (asset_root, level_root) if not path.exists()]
        if missing:
            missing_str = ", ".join(str(path) for path in missing)
            raise FileNotFoundError(
                f"Required UI resource directories do not exist: {missing_str}"
            )

    return UIDirectories(asset_root=asset_root, level_root=level_root)


@dataclass
class GridGeometry:
    """Geometry helpers derived from the current level and screen size."""

    origin: Tuple[int, int]
    cell_size: int

    def cell_to_topleft(self, cell: Tuple[int, int]) -> Tuple[int, int]:
        x, y = cell
        return (
            self.origin[0] + x * self.cell_size,
            self.origin[1] + y * self.cell_size,
        )

    def cell_to_center(self, cell: Tuple[int, int]) -> Tuple[int, int]:
        top_left = self.cell_to_topleft(cell)
        return (
            top_left[0] + self.cell_size // 2,
            top_left[1] + self.cell_size // 2,
        )


class LaserGameApp:
    """Pygame driven application for the laser puzzle."""

    background_gradient_top = (26, 32, 56)
    background_gradient_bottom = (10, 12, 24)
    chrome_color = (32, 38, 62, 228)
    chrome_border = (64, 72, 104, 255)
    panel_glow = (70, 140, 255, 80)
    grid_color = (78, 88, 122)
    beam_color = (255, 140, 60)
    emitter_color = (130, 210, 255)
    target_color = (140, 255, 180)
    mirror_color = (240, 240, 240)
    text_primary = (232, 236, 244)
    text_secondary = (168, 176, 196)
    border_radius = 22
    obstacle_color = (190, 80, 100)
    obstacle_border = (255, 180, 200)
    bomb_color = (255, 220, 110)

    def __init__(
        self,
        screen_size: Tuple[int, int] = (1440, 900),
        *,
        directories: Optional[UIDirectories] = None,
    ) -> None:
        pygame.init()
        pygame.display.set_caption("Laser Game")
        self.screen_flags = pygame.RESIZABLE
        self.windowed_size = screen_size
        self.fullscreen = False
        self.screen = pygame.display.set_mode(screen_size, self.screen_flags)
        self.clock = pygame.time.Clock()
        if hasattr(pygame.font, "SysFont"):
            sys_font = pygame.font.SysFont
            self.font = sys_font("segoeui", 18)
            self.small_font = sys_font("segoeui", 15)
            self.bold_font = sys_font("segoeui", 24, bold=True)
        else:  # pragma: no cover - pygame stub fallback
            default_font = pygame.font.get_default_font()
            self.font = pygame.font.Font(default_font, 18)
            self.small_font = pygame.font.Font(default_font, 15)
            self.bold_font = pygame.font.Font(default_font, 24)

        self.layout_sidebar_width = 360
        self.layout_header_height = 140
        self.layout_footer_height = 96
        self.layout_margin = 28

        self.directories = directories or resolve_directories()
        self.level_loader = LevelLoader(self.directories.level_root)
        self.level_names: List[str] = sorted(
            [path.stem for path in self.level_loader.root.glob("*.json")]
        )
        if not self.level_names:
            raise RuntimeError("No levels available to load.")

        self.level_index: int = 0
        self.level: Optional[Level] = None
        self.game: Optional[LaserGame] = None
        self.playthrough: Dict[str, object] = {}
        self.geometry: Optional[GridGeometry] = None
        self.visible_target_energy: Dict[Tuple[int, int], int] = {}

        self.mode: str = "intro"
        self.score: int = 0
        self.combo: int = 0
        self.completed_levels: Dict[str, bool] = {}
        self.points_history: List[Tuple[str, int]] = []

        self._needs_update = False

        now = time.perf_counter()
        self.last_time = now
        self.footer_visible_until = now + 6.0
        self.instructions_visible_until = now + 10.0
        self.show_instructions = True

        self.pulse_speed = 3.5  # grid cells per second
        self.active_pulse = False
        self.timeline: List[List[BeamSegment]] = []
        self.completed_segments: List[BeamSegment] = []
        self.render_segments: List[BeamSegment] = []
        self.active_segments: List[BeamSegment] = []
        self.timeline_progress: float = 0.0
        self.timeline_index: int = 0
        self.hit_queue: List[Dict[str, object]] = []
        self.explosion_queue: List[Dict[str, object]] = []
        self.obstacle_removal_queue: List[Dict[str, object]] = []
        self.hidden_obstacles: Set[Tuple[int, int]] = set()
        self.hit_animations: List[Dict[str, object]] = []
        self.explosion_animations: List[Dict[str, object]] = []
        self.energy_particles: List[Dict[str, object]] = []
        self.max_energy_level = 8
        self.energy_stage_names = [
            "Level 0",
            "Level 1",
            "Level 2",
            "Level 3",
            "Level 4",
            "Level 5",
            "Level 6",
            "Level 7",
            "Level 8",
        ]
        self.energy_palette = [
            (36, 40, 60),
            (62, 92, 168),
            (74, 128, 210),
            (96, 168, 255),
            (128, 208, 255),
            (160, 236, 200),
            (208, 244, 140),
            (248, 204, 96),
            (255, 156, 72),
        ]
        self.icon_cache: Dict[Tuple[str, int, str], pygame.Surface] = {}
        self.hit_animation_duration = 0.6
        self.explosion_animation_duration = 0.8
        self.level_complete_flash_duration = 2.5
        self.status_message: Optional[str] = None
        self.status_message_until: float = 0.0
        self.rotation_locked_cell: Optional[Tuple[int, int]] = None
        self.rotation_lock_expires: float = 0.0
        self._recent_placement: Optional[Tuple[str, Tuple[int, int]]] = None
        self.level_complete_time: Optional[float] = None
        self.button_rect = pygame.Rect(0, 0, 0, 0)
        self.start_button_rect = pygame.Rect(0, 0, 0, 0)
        self.toolbar_buttons: List[Tuple[pygame.Rect, str]] = []
        self.selected_tool: str = "mirror"
        self.tool_palette = [
            {"id": "mirror", "label": "Spiegel", "hint": "Spiegel platzieren oder drehen (R wiederholen)"},
            {"id": "splitter", "label": "Splitter", "hint": "Zweite Strahlabzweigung"},
            {"id": "splitter_triple", "label": "Triple", "hint": "Dreiwege-Teilung"},
            {"id": "splitter_cross", "label": "Cross", "hint": "Kreuz-Reflektor"},
            {"id": "amplifier", "label": "Amplifier", "hint": "Energie verstaerken"},
            {"id": "bomb", "label": "Bombe", "hint": "Hindernisse sprengen"},
        ]
        self.base_tool_limits: Dict[str, int] = {}
        self.remaining_tools: Dict[str, int] = {}
        self.level_nodes: List[Dict[str, object]] = []
        self.map_hover_index: Optional[int] = None

        self.back_button_rect = pygame.Rect(0, 0, 0, 0)
        self.level_start_time = time.perf_counter()
        self.load_level(self.level_names[self.level_index])

    # ------------------------------------------------------------------
    # Level handling
    # ------------------------------------------------------------------
    def load_level(self, name: str) -> None:
        """Load a level and prepare the runtime artefacts."""

        self.level = self.level_loader.load(name)
        self.game = LaserGame(self.level)
        limits = getattr(self.level, "tool_limits", {})
        if limits:
            normalized_limits: Dict[str, int] = {}
            for tool_id, value in limits.items():
                key = self._normalise_tool_id(tool_id)
                normalized_limits[key] = int(value)
            available_keys = {self._normalise_tool_id(tool["id"]) for tool in self.tool_palette}
            for key in available_keys:
                normalized_limits.setdefault(key, 0)
            self.base_tool_limits = normalized_limits
        else:
            self.base_tool_limits = {}
        self.remaining_tools = dict(self.base_tool_limits)
        self._clear_pulse_state(reset_game=True)
        self.rotation_locked_cell = None
        self.rotation_lock_expires = 0.0
        self.status_message = None
        self._needs_update = True
        self.update_playthrough(force=True)
        now = time.perf_counter()
        self.footer_visible_until = now + 6.0
        self.instructions_visible_until = now + 10.0
        self.show_instructions = True
        self.level_start_time = now

    def start_game(self) -> None:
        if self.mode == "intro":
            self.mode = "map"
            self._build_level_nodes()
            return
        if self.mode == "play":
            return
        self.mode = "play"
        self.score = 0
        self.combo = 0
        self.completed_levels.clear()
        self.points_history.clear()
        self._clear_pulse_state(reset_game=True)
        self.remaining_tools = dict(self.base_tool_limits)
        now = time.perf_counter()
        self.footer_visible_until = now + 6.0
        self.instructions_visible_until = now + 12.0
        self.show_instructions = True

    def cycle_level(self, direction: int) -> None:
        """Advance the level index and load the new level."""

        if not self.level_names:
            return
        self.level_index = (self.level_index + direction) % len(self.level_names)
        self.load_level(self.level_names[self.level_index])

    def update_playthrough(self, force: bool = False) -> None:
        if not self.game:
            return
        if not force and not self._needs_update:
            return
        metadata = self.game.level.metadata if self.level else {}
        self.playthrough = {"metadata": metadata}
        title = "Laser Game"
        if metadata:
            title = (
                "Laser Game - "
                f"{metadata.get('name', 'Unknown')} "
                f"({metadata.get('difficulty', '???')})"
            )
        pygame.display.set_caption(title)
        self.geometry = self._compute_geometry()
        self._clear_pulse_state()
        self._needs_update = False

    def _compute_geometry(self) -> Optional[GridGeometry]:
        if not self.level:
            return None
        width, height = self.screen.get_size()
        margin = self.layout_margin
        available_w = max(
            width - self.layout_sidebar_width - margin * 3, 80
        )
        available_h = max(
            height - self.layout_header_height - self.layout_footer_height - margin * 3,
            80,
        )
        cell_size = int(
            min(
                available_w / max(self.level.width, 1),
                available_h / max(self.level.height, 1),
            )
        )
        cell_size = max(cell_size, 28)
        total_w = cell_size * self.level.width
        total_h = cell_size * self.level.height
        origin_x = margin
        origin_y = self.layout_header_height + margin
        return GridGeometry(origin=(origin_x, origin_y), cell_size=cell_size)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def draw(self) -> None:
        if self.mode == "intro":
            self._draw_intro_screen()
            pygame.display.flip()
            return
        if self.mode == "map":
            self._draw_level_map()
            pygame.display.flip()
            return
        if not self.level or not self.geometry:
            self._draw_intro_screen()
            pygame.display.flip()
            return

        board_rect = pygame.Rect(
            self.geometry.origin[0],
            self.geometry.origin[1],
            self.geometry.cell_size * self.level.width,
            self.geometry.cell_size * self.level.height,
        )

        self._draw_background()
        self._draw_board_container(board_rect)
        sidebar_rect = self._draw_sidebar(board_rect)
        banner_rect = self._draw_top_banner()
        footer_rect = self._draw_footer()

        self._draw_grid()
        self._draw_emitters()
        self._draw_targets()
        self._draw_mirrors()
        self._draw_splitters()
        self._draw_amplifiers()
        self._draw_obstacles()
        self._draw_bombs()
        self._draw_beam_path()
        self._draw_effects()
        self._draw_metadata(banner_rect, sidebar_rect, footer_rect)

        pygame.display.flip()

    def _draw_intro_screen(self) -> None:
        self._draw_background()
        self.toolbar_buttons = []
        width, height = self.screen.get_size()
        margin = self.layout_margin
        card_width = min(width - margin * 2, 1040)
        card_height = min(height - margin * 2, 580)
        card_rect = pygame.Rect(
            (width - card_width) // 2,
            (height - card_height) // 2,
            card_width,
            card_height,
        )
        mouse_pos = pygame.mouse.get_pos()
        shadow = self._alpha_surface((card_rect.width + 24, card_rect.height + 24))
        pygame.draw.rect(
            shadow,
            (12, 14, 24, 110),
            shadow.get_rect(),
            border_radius=self.border_radius * 2,
        )
        self.screen.blit(shadow, (card_rect.x - 12, card_rect.y - 8))
        gradient = self._alpha_surface(card_rect.size)
        for y in range(card_rect.height):
            t = y / max(1, card_rect.height - 1)
            color = (
                int(60 + 50 * (1 - t)),
                int(84 + 72 * t),
                int(168 + 48 * (1 - t)),
                235,
            )
            pygame.draw.line(gradient, color, (0, y), (card_rect.width, y))
        mask = self._alpha_surface(card_rect.size)
        pygame.draw.rect(
            mask,
            (255, 255, 255, 255),
            mask.get_rect(),
            border_radius=self.border_radius * 2,
        )
        gradient.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        outline = self._alpha_surface(card_rect.size)
        self._rounded_rect(
            outline, (255, 255, 255, 42), outline.get_rect(), width=2, radius=self.border_radius * 2
        )
        gradient.blit(outline, (0, 0))
        self.screen.blit(gradient, card_rect.topleft)
        title = self.bold_font.render("Laser Pulse Odyssey", True, self.text_primary)
        subtitle = self.small_font.render(
            "Optimiere Spiegel, Splitter und Energiequellen in dynamischen Levels.",
            True,
            self.text_secondary,
        )
        title_rect = title.get_rect(topleft=(card_rect.x + 44, card_rect.y + 40))
        subtitle_rect = subtitle.get_rect(topleft=(card_rect.x + 44, title_rect.bottom + 8))
        self.screen.blit(title, title_rect)
        self.screen.blit(subtitle, subtitle_rect)
        legend_items = [
            ("Emitter", "Startet den Laserstrahl in die Grundrichtung", ("emitter", "EAST|1.0")),
            ("Ziele", "Füllen sich mit Energie bis sie aktiviert sind", ("target", "")),
            ("Splitter", "Verzweigen Strahlen in neue Pfade", ("splitter", "dual")),
            ("3er-Splitter", "Verteilt Energie nach links, vorne und rechts", ("splitter", "triple")),
            ("Bomben", "Sprengen Hindernisse innerhalb ihres Radius", ("bomb", "")),
            ("Amplifier", "Verstärken Energie für lange Routen", ("amplifier", "")),
            ("Hindernisse", "Blockieren den Weg bis sie beseitigt werden", ("obstacle", "")),
        ]
        icon_size = 50
        legend_y = subtitle_rect.bottom + 30
        for label, description, spec in legend_items:
            icon = self._get_icon_surface(spec[0], icon_size, spec[1])
            icon_pos = (card_rect.x + 44, legend_y)
            self.screen.blit(icon, icon_pos)
            text_x = icon_pos[0] + icon_size + 18
            label_surface = self.font.render(label, True, self.text_primary)
            desc_surface = self.small_font.render(description, True, self.text_secondary)
            self.screen.blit(label_surface, (text_x, icon_pos[1]))
            self.screen.blit(desc_surface, (text_x, icon_pos[1] + label_surface.get_height() + 2))
            legend_y += icon_size + 16
        paragraph_lines = [
            "- Bomben löschen Hindernisse während einer Simulation sofort – ein Neustart setzt sie zurück.",
            "- Splitter senden jetzt alle Strahlen zeitgleich in jede Richtung.",
            "- Amplifier bündeln Energie für entlegene Ziele und Combo-Ketten.",
            "- Ziele zeigen stets ihren aktuellen Fortschritt gegenüber dem Soll.",
        ]
        paragraph_y = legend_y + 12
        for line in paragraph_lines:
            surface = self.small_font.render(line, True, self.text_secondary)
            self.screen.blit(surface, (card_rect.x + 44, paragraph_y))
            paragraph_y += surface.get_height() + 6
        button_width = 288
        button_height = 64
        button_rect = pygame.Rect(
            card_rect.centerx - button_width // 2,
            card_rect.bottom - button_height - 32,
            button_width,
            button_height,
        )
        hovered_button = button_rect.collidepoint(mouse_pos)
        button_surface = self._alpha_surface(button_rect.size)
        for x_pos in range(button_rect.width):
            ratio = x_pos / max(1, button_rect.width - 1)
            r = int(255 - 35 * ratio)
            g = int(158 + 40 * ratio)
            b = int(96 + 24 * ratio)
            if hovered_button:
                r = min(255, r + 20)
                g = min(255, g + 20)
                b = min(255, b + 20)
            pygame.draw.line(button_surface, (r, g, b, 240), (x_pos, 0), (x_pos, button_rect.height))
        border_alpha = 130 if hovered_button else 100
        self._rounded_rect(button_surface, (255, 255, 255, border_alpha), button_surface.get_rect(), width=2, radius=20)
        if hovered_button:
            glow = self._alpha_surface((button_rect.width + 12, button_rect.height + 12))
            pygame.draw.rect(glow, (255, 200, 140, 90), glow.get_rect(), border_radius=22)
            self.screen.blit(glow, (button_rect.x - 6, button_rect.y - 6), special_flags=pygame.BLEND_RGBA_ADD)
        label = self.bold_font.render("Mission starten", True, (28, 12, 6))
        label_rect = label.get_rect(center=(button_rect.width // 2 - 20, button_rect.height // 2 - 4))
        button_surface.blit(label, label_rect)
        arrow_points = [
            (button_rect.width - 44, button_rect.height // 2),
            (button_rect.width - 60, button_rect.height // 2 - 12),
            (button_rect.width - 60, button_rect.height // 2 + 12),
        ]
        pygame.draw.polygon(button_surface, (28, 12, 6), arrow_points)
        hint = self.small_font.render("ENTER oder LEERTASTE", True, (35, 18, 9))
        hint_rect = hint.get_rect(center=(button_rect.width // 2, button_rect.height - 18))
        button_surface.blit(hint, hint_rect)
        self.screen.blit(button_surface, button_rect.topleft)
        self.start_button_rect = button_rect

    def _build_level_nodes(self) -> None:
        self.level_nodes = []
        width, height = self.screen.get_size()
        margin = self.layout_margin
        cols = max(3, min(5, len(self.level_names)))
        rows = max(1, (len(self.level_names) + cols - 1) // cols)
        available_w = width - margin * 2
        available_h = height - margin * 2
        grid_w = available_w / max(cols, 1)
        grid_h = available_h / max(rows, 1)
        radius = int(min(grid_w, grid_h) * 0.22)
        for index, name in enumerate(self.level_names):
            col = index % cols
            row = index // cols
            center_x = int(margin + grid_w * (col + 0.5))
            center_y = int(margin + grid_h * (row + 0.5))
            rect = pygame.Rect(center_x - radius, center_y - radius, radius * 2, radius * 2)
            self.level_nodes.append(
                {
                    "index": index,
                    "name": name,
                    "center": (center_x, center_y),
                    "rect": rect,
                    "radius": radius,
                }
            )

    def _draw_level_map(self) -> None:
        self._draw_background()
        if not self.level_nodes:
            self._build_level_nodes()
        title = self.bold_font.render("Level-Auswahl", True, self.text_primary)
        subtitle = self.small_font.render("Klicke auf eine Station oder nutze <-/->/Enter/Esc", True, self.text_secondary)
        title_pos = (self.layout_margin + 24, self.layout_margin + 24)
        self.screen.blit(title, title_pos)
        self.screen.blit(subtitle, (title_pos[0], title_pos[1] + title.get_height() + 8))
        mouse_pos = pygame.mouse.get_pos()
        for idx in range(len(self.level_nodes) - 1):
            start_center = self.level_nodes[idx]["center"]
            end_center = self.level_nodes[idx + 1]["center"]
            pygame.draw.line(self.screen, (60, 80, 140), start_center, end_center, 6)
            pygame.draw.line(self.screen, (180, 200, 255, 160), start_center, end_center, 2)
        hover_index = None
        for node in self.level_nodes:
            idx = node["index"]
            name = node["name"]
            center = node["center"]
            status = self.completed_levels.get(self.level_names[idx], False)
            active = idx == self.level_index
            hovered = node["rect"].collidepoint(mouse_pos)
            if hovered:
                hover_index = idx
            base_radius = node["radius"]
            scale = 1.0
            if status:
                scale = 1.08
            if active:
                scale = 1.15
            if hovered:
                scale = 1.3
            radius = int(base_radius * scale)
            node["rect"] = pygame.Rect(center[0] - radius, center[1] - radius, radius * 2, radius * 2)
            diameter = radius * 2
            surface = self._alpha_surface((diameter, diameter))
            fill_color = (90, 120, 200, 210)
            if status:
                fill_color = (120, 180, 255, 225)
            if active:
                fill_color = (255, 150, 120, 235)
            if hovered:
                fill_color = (255, 190, 140, 240)
            pygame.draw.circle(surface, fill_color, (radius, radius), radius)
            pygame.draw.circle(surface, (255, 255, 255, 180), (radius, radius), radius, 3)
            if hovered:
                glow = self._alpha_surface((diameter + 20, diameter + 20))
                pygame.draw.circle(glow, (255, 200, 160, 90), ((diameter + 20) // 2, (diameter + 20) // 2), radius + 10)
                self.screen.blit(glow, (center[0] - (diameter + 20) // 2, center[1] - (diameter + 20) // 2), special_flags=pygame.BLEND_RGBA_ADD)
            self.screen.blit(surface, (center[0] - radius, center[1] - radius))
            label = self.font.render(str(idx + 1), True, self.text_primary)
            self.screen.blit(label, label.get_rect(center=center))
            caption = self.small_font.render(name.replace("level_", ""), True, self.text_primary)
            self.screen.blit(caption, caption.get_rect(midtop=(center[0], center[1] + radius + 6)))
        self.map_hover_index = hover_index

    def _enter_level(self, level_index: int) -> None:
        if not self.level_names:
            return
        self.level_index = level_index % len(self.level_names)
        self.load_level(self.level_names[self.level_index])
        self.mode = "play"
        now = time.perf_counter()
        self.footer_visible_until = now + 6.0
        self.instructions_visible_until = now + 10.0
        self.show_instructions = True

    def _current_target_energy(self) -> Dict[Tuple[int, int], int]:
        return dict(self.visible_target_energy)

    def _clear_pulse_state(self, reset_game: bool = False) -> None:
        if reset_game and self.game:
            self.game.reset()
        self.active_pulse = False
        self.timeline = []
        self.completed_segments = []
        self.render_segments = []
        self.active_segments = []
        self.timeline_progress = 0.0
        self.timeline_index = 0
        self.hit_queue = []
        self.explosion_queue = []
        self.obstacle_removal_queue = []
        self.hit_animations = []
        self.explosion_animations = []
        self.hidden_obstacles.clear()
        self.level_complete_time = None
        if self.level:
            self.visible_target_energy = {pos: 0 for pos in self.level.targets}
        else:
            self.visible_target_energy = {}

    def _set_status_message(self, message: str, duration: float = 3.0) -> None:
        self.status_message = message
        self.status_message_until = time.perf_counter() + duration

    def _rotation_locked(self, cell: Tuple[int, int]) -> bool:
        return (
            self.rotation_locked_cell is not None
            and self.rotation_locked_cell == cell
            and time.perf_counter() < self.rotation_lock_expires
        )

    def _spawn_energy_particles(self, position: Tuple[int, int], energy_level: int) -> None:
        if not self.geometry:
            return
        center = self.geometry.cell_to_center(position)
        stage_index = self._energy_stage_index(energy_level)
        count = 4 + min(10, stage_index * 2)
        color = self._energy_stage_color(energy_level)
        for _ in range(count):
            angle = random.uniform(0.0, math.tau)
            speed = random.uniform(60.0, 140.0)
            self.energy_particles.append(
                {
                    "pos": [float(center[0]), float(center[1])],
                    "vel": [math.cos(angle) * speed, math.sin(angle) * speed],
                    "life": 0.0,
                    "duration": 0.6,
                    "color": color,
                }
            )

    def _footer_status_text(self) -> Optional[str]:
        now = time.perf_counter()
        if self.status_message and now < self.status_message_until:
            return self.status_message
        if now < self.footer_visible_until:
            return "Lasse jeden Zielknoten genug Energie sammeln, um das Level zu gewinnen."
        return None

    def _rounded_rect(
        self,
        surface: pygame.Surface,
        color: Tuple[int, int, int] | Tuple[int, int, int, int],
        rect: pygame.Rect,
        *,
        width: int = 0,
        radius: int = 0,
    ) -> None:
        if radius > 0:
            try:
                pygame.draw.rect(surface, color, rect, width, border_radius=radius)
                return
            except TypeError:  # pragma: no cover - pygame stub fallback
                pass
        pygame.draw.rect(surface, color, rect, width)

    def _alpha_surface(self, size: Tuple[int, int]) -> pygame.Surface:
        surface = pygame.Surface(size, pygame.SRCALPHA)
        surface.fill((0, 0, 0, 0))
        return surface

    def _get_icon_surface(self, name: str, size: int, extra: str = "") -> pygame.Surface:
        key = (name, size, extra)
        cached = self.icon_cache.get(key)
        if cached is not None:
            return cached.copy()
        builder = getattr(self, f"_build_{name}_icon", None)
        if builder is None:
            raise KeyError(f"Unknown icon '{name}'")
        surface = builder(size, extra)
        self.icon_cache[key] = surface
        return surface.copy()

    def _build_obstacle_icon(self, size: int, extra: str) -> pygame.Surface:
        surface = self._alpha_surface((size, size))
        rect = surface.get_rect()
        margin = size * 0.12
        points = [
            (rect.left + margin, rect.top + size * 0.28),
            (rect.left + size * 0.45, rect.top + margin),
            (rect.right - margin, rect.top + size * 0.34),
            (rect.right - margin * 0.55, rect.bottom - margin),
            (rect.left + size * 0.42, rect.bottom - margin * 0.5),
            (rect.left + margin * 0.4, rect.bottom - size * 0.2),
        ]
        points = [(int(px), int(py)) for px, py in points]
        pygame.draw.polygon(surface, (82, 44, 68), points)
        center_x, center_y = rect.center
        inner = [
            (
                int(center_x + (px - center_x) * 0.7),
                int(center_y + (py - center_y) * 0.7),
            )
            for px, py in points
        ]
        pygame.draw.polygon(surface, (132, 78, 112), inner)
        highlight = [
            (
                int(center_x + (px - center_x) * 0.5),
                int(center_y + (py - center_y) * 0.5 - size * 0.05),
            )
            for px, py in points[:3]
        ]
        highlight.append((int(center_x), int(center_y - size * 0.18)))
        pygame.draw.polygon(surface, (210, 180, 206, 130), highlight)
        crack_color = (38, 20, 32, 220)
        crack_paths = [
            [
                (rect.left + size * 0.3, rect.top + size * 0.35),
                (rect.left + size * 0.42, rect.top + size * 0.48),
                (rect.left + size * 0.38, rect.top + size * 0.62),
                (rect.left + size * 0.46, rect.bottom - size * 0.18),
            ],
            [
                (rect.left + size * 0.62, rect.top + size * 0.28),
                (rect.left + size * 0.68, rect.top + size * 0.46),
                (rect.left + size * 0.58, rect.top + size * 0.58),
            ],
        ]
        for path in crack_paths:
            pygame.draw.lines(
                surface,
                crack_color,
                False,
                [(int(x), int(y)) for x, y in path],
                max(1, size // 20),
            )
        return surface

    def _build_bomb_icon(self, size: int, extra: str) -> pygame.Surface:
        surface = self._alpha_surface((size, size))
        center = (size // 2, size // 2)
        radius = int(size * 0.32)
        step = max(1, size // 18)
        for layer in range(0, radius, step):
            ratio = layer / max(1, radius)
            color = (
                int(248 - 80 * ratio),
                int(210 - 90 * ratio),
                int(130 - 60 * ratio),
                240,
            )
            pygame.draw.circle(surface, color, center, radius - layer)
        pygame.draw.circle(surface, (44, 28, 24), center, radius, max(2, size // 36))
        fuse_start = (center[0], center[1] - radius)
        fuse_mid = (center[0] - int(size * 0.08), fuse_start[1] - int(size * 0.16))
        fuse_end = (center[0] + int(size * 0.12), fuse_mid[1] - int(size * 0.14))
        pygame.draw.lines(
            surface,
            (70, 52, 40),
            False,
            [fuse_start, fuse_mid, fuse_end],
            max(2, size // 20),
        )
        spark_center = (fuse_end[0], fuse_end[1] - int(size * 0.04))
        spark_radius = max(2, size // 12)
        pygame.draw.circle(surface, (255, 230, 140, 220), spark_center, spark_radius)
        pygame.draw.circle(surface, (255, 255, 255, 200), spark_center, max(1, spark_radius // 2))
        return surface

    def _build_target_icon(self, size: int, extra: str) -> pygame.Surface:
        surface = self._alpha_surface((size, size))
        rect = surface.get_rect()
        center = rect.center
        outer = int(size * 0.42)
        pygame.draw.circle(surface, (36, 56, 96), center, outer)
        pygame.draw.circle(surface, (255, 255, 255), center, outer, max(2, size // 28))
        inner = int(outer * 0.68)
        pygame.draw.circle(surface, self.target_color, center, inner)
        pygame.draw.circle(surface, (255, 255, 255, 200), center, inner, max(2, size // 32))
        core = int(inner * 0.45)
        pygame.draw.circle(surface, (255, 255, 230), center, core)
        pygame.draw.circle(surface, (90, 120, 190), center, max(2, core // 3))
        cross_len = int(outer * 0.9)
        pygame.draw.line(
            surface,
            (255, 255, 255, 150),
            (center[0] - cross_len // 2, center[1]),
            (center[0] + cross_len // 2, center[1]),
            max(1, size // 38),
        )
        pygame.draw.line(
            surface,
            (255, 255, 255, 150),
            (center[0], center[1] - cross_len // 2),
            (center[0], center[1] + cross_len // 2),
            max(1, size // 38),
        )
        return surface

    def _build_amplifier_icon(self, size: int, extra: str) -> pygame.Surface:
        surface = self._alpha_surface((size, size))
        rect = surface.get_rect()
        center = rect.center
        radius = int(size * 0.36)
        for layer in range(radius, 0, -max(1, radius // 12)):
            ratio = layer / radius
            color = (
                int(255 - 40 * (1 - ratio)),
                int(210 - 30 * (1 - ratio)),
                int(140 + 50 * ratio),
                int(220 * ratio),
            )
            pygame.draw.circle(surface, color, center, layer)
        pygame.draw.circle(surface, (255, 255, 255, 200), center, radius, max(2, size // 26))
        bar_length = int(size * 0.22)
        bar_width = max(3, size // 16)
        pygame.draw.rect(
            surface,
            (48, 26, 12),
            pygame.Rect(0, 0, bar_length * 2, bar_width).move(center[0] - bar_length, center[1] - bar_width // 2),
        )
        pygame.draw.rect(
            surface,
            (48, 26, 12),
            pygame.Rect(0, 0, bar_width, bar_length * 2).move(center[0] - bar_width // 2, center[1] - bar_length),
        )
        glow = self._alpha_surface((size, size))
        pygame.draw.circle(glow, (255, 200, 120, 110), center, radius + max(2, size // 12))
        surface.blit(glow, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        return surface

    def _build_splitter_icon(self, size: int, extra: str) -> pygame.Surface:
        surface = self._alpha_surface((size, size))
        rect = surface.get_rect()
        pattern = (extra or "dual").lower()
        palette = {
            "dual": (118, 182, 248, 210),
            "splitter": (118, 182, 248, 210),
            "triple": (170, 148, 245, 215),
            "cross": (244, 138, 118, 220),
        }
        body_color = palette.get(pattern, (140, 160, 220, 200))
        body_rect = rect.inflate(-size * 0.22, -size * 0.22)
        pygame.draw.rect(surface, body_color, body_rect, border_radius=int(size * 0.18))
        pygame.draw.rect(
            surface,
            (255, 255, 255, 190),
            body_rect,
            width=max(2, size // 24),
            border_radius=int(size * 0.18),
        )
        center = rect.center
        pygame.draw.circle(surface, (255, 255, 255, 230), center, max(3, size // 12))
        directions = []
        if pattern in {"dual", "splitter"}:
            directions = [(-1, 0), (1, 0)]
        elif pattern == "triple":
            directions = [(-1, 0), (1, 0), (0, -1)]
        elif pattern == "cross":
            directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        else:
            directions = [(1, 0)]
        length = int(size * 0.34)
        width = max(3, size // 18)
        for dx, dy in directions:
            end = (center[0] + dx * length, center[1] + dy * length)
            pygame.draw.line(surface, (255, 255, 255, 220), center, end, width)
            arrow = [
                (end[0] + dx * width, end[1] + dy * width),
                (end[0] - dy * width * 0.8, end[1] + dx * width * 0.8),
                (end[0] + dy * width * 0.8, end[1] - dx * width * 0.8),
            ]
            pygame.draw.polygon(
                surface,
                (255, 255, 255, 210),
                [(int(x), int(y)) for x, y in arrow],
            )
        return surface

    def _build_emitter_icon(self, size: int, extra: str) -> pygame.Surface:
        direction_name = "EAST"
        brightness = 1.0
        if extra:
            parts = extra.split("|")
            if parts[0]:
                direction_name = parts[0].upper()
            if len(parts) > 1 and parts[1]:
                try:
                    brightness = float(parts[1])
                except ValueError:
                    brightness = 1.0
        try:
            direction = Direction.from_name(direction_name)
        except ValueError:
            direction = Direction.EAST
        surface = self._alpha_surface((size, size))
        rect = surface.get_rect()
        center = rect.center
        base_color = self._emitter_color(brightness)
        outer_radius = int(size * 0.42)
        inner_radius = int(size * 0.28)
        for layer in range(outer_radius, inner_radius, -max(1, outer_radius // 18)):
            ratio = (layer - inner_radius) / max(1, outer_radius - inner_radius)
            glow = (
                min(255, int(base_color[0] + (255 - base_color[0]) * (1 - ratio))),
                min(255, int(base_color[1] + (255 - base_color[1]) * (1 - ratio))),
                min(255, int(base_color[2] + (255 - base_color[2]) * (1 - ratio))),
                int(90 * ratio),
            )
            pygame.draw.circle(surface, glow, center, layer)
        pygame.draw.circle(surface, (28, 36, 58), center, outer_radius, max(2, size // 26))
        pygame.draw.circle(surface, base_color, center, inner_radius)
        pygame.draw.circle(surface, (255, 255, 255, 160), center, max(2, inner_radius // 3))
        arrow_length = int(size * 0.36)
        arrow_width = max(3, size // 16)
        start = (center[0] - arrow_length * 0.2, center[1])
        end = (center[0] + arrow_length, center[1])
        pygame.draw.line(surface, (255, 255, 255), start, end, arrow_width)
        head = [
            (end[0], end[1]),
            (end[0] - arrow_width * 2, end[1] - arrow_width),
            (end[0] - arrow_width * 2, end[1] + arrow_width),
        ]
        pygame.draw.polygon(surface, (255, 255, 255), [(int(x), int(y)) for x, y in head])
        if direction != Direction.EAST:
            angle_map = {
                Direction.NORTH: 90,
                Direction.SOUTH: -90,
                Direction.WEST: 180,
            }
            angle = angle_map.get(direction, 0)
            rotated = pygame.transform.rotozoom(surface, angle, 1.0)
            surface = pygame.transform.smoothscale(rotated, (size, size))
        return surface

    def _draw_background(self) -> None:
        width, height = self.screen.get_size()
        gradient = pygame.Surface((width, height))
        for y in range(height):
            ratio = y / max(height - 1, 1)
            color = tuple(
                int(
                    self.background_gradient_top[i] * (1 - ratio)
                    + self.background_gradient_bottom[i] * ratio
                )
                for i in range(3)
            )
            pygame.draw.line(gradient, color, (0, y), (width, y))
        self.screen.blit(gradient, (0, 0))
        halo = self._alpha_surface((width, height))
        pygame.draw.circle(
            halo,
            (120, 160, 255, 80),
            (int(width * 0.35), int(height * 0.3)),
            max(width, height) // 2,
        )
        pygame.draw.circle(
            halo,
            (255, 100, 180, 70),
            (int(width * 0.7), int(height * 0.75)),
            max(width, height) // 2,
        )
        self.screen.blit(halo, (0, 0))

    def _draw_board_container(self, board_rect: pygame.Rect) -> None:
        padding = 24
        container_rect = board_rect.inflate(padding * 2, padding * 2)
        chrome_surface = self._alpha_surface(container_rect.size)
        self._rounded_rect(
            chrome_surface,
            self.chrome_color,
            chrome_surface.get_rect(),
            radius=self.border_radius,
        )
        self._rounded_rect(
            chrome_surface,
            self.chrome_border,
            chrome_surface.get_rect(),
            width=2,
            radius=self.border_radius,
        )
        self.screen.blit(chrome_surface, container_rect.topleft)

    def _draw_sidebar(self, board_rect: pygame.Rect) -> pygame.Rect:
        screen_width, screen_height = self.screen.get_size()
        margin = self.layout_margin
        sidebar_width = self.layout_sidebar_width
        sidebar_height = max(
            screen_height - self.layout_header_height - self.layout_footer_height - margin * 2,
            120,
        )
        sidebar_x = screen_width - sidebar_width - margin
        sidebar_y = self.layout_header_height + margin
        sidebar_rect = pygame.Rect(sidebar_x, sidebar_y, sidebar_width, sidebar_height)

        panel_surface = self._alpha_surface(sidebar_rect.size)
        self._rounded_rect(
            panel_surface,
            self.chrome_color,
            panel_surface.get_rect(),
            radius=self.border_radius,
        )
        self._rounded_rect(
            panel_surface,
            self.chrome_border,
            panel_surface.get_rect(),
            width=2,
            radius=self.border_radius,
        )
        glow_surface = self._alpha_surface(sidebar_rect.size)
        self._rounded_rect(
            glow_surface,
            self.panel_glow,
            glow_surface.get_rect(),
            radius=self.border_radius,
        )
        self.screen.blit(glow_surface, sidebar_rect.topleft)
        self.screen.blit(panel_surface, sidebar_rect.topleft)
        return sidebar_rect

    def _draw_top_banner(self) -> pygame.Rect:
        width, _ = self.screen.get_size()
        margin = self.layout_margin
        banner_rect = pygame.Rect(
            margin,
            margin,
            width - self.layout_sidebar_width - margin * 3,
            self.layout_header_height - margin,
        )
        banner_surface = self._alpha_surface(banner_rect.size)
        self._rounded_rect(
            banner_surface,
            (40, 46, 76, 235),
            banner_surface.get_rect(),
            radius=self.border_radius,
        )
        self._rounded_rect(
            banner_surface,
            self.chrome_border,
            banner_surface.get_rect(),
            width=2,
            radius=self.border_radius,
        )
        self.screen.blit(banner_surface, banner_rect.topleft)
        return banner_rect

    def _draw_footer(self) -> pygame.Rect:
        width, height = self.screen.get_size()
        margin = self.layout_margin
        footer_rect = pygame.Rect(
            margin,
            height - self.layout_footer_height,
            width - margin * 2,
            self.layout_footer_height - margin // 2,
        )
        footer_surface = self._alpha_surface(footer_rect.size)
        self._rounded_rect(
            footer_surface,
            (40, 46, 76, 180),
            footer_surface.get_rect(),
            radius=self.border_radius,
        )
        self._rounded_rect(
            footer_surface,
            (74, 84, 116, 220),
            footer_surface.get_rect(),
            width=1,
            radius=self.border_radius,
        )
        self.screen.blit(footer_surface, footer_rect.topleft)

        button_width = 200
        button_height = 44
        button_rect = pygame.Rect(
            footer_rect.right - button_width - 24,
            footer_rect.y + (footer_rect.height - button_height) // 2,
            button_width,
            button_height,
        )
        self.button_rect = button_rect

        button_surface = self._alpha_surface(button_rect.size)
        button_color = (90, 150, 255, 220)
        label_color = self.text_primary
        if self.active_pulse:
            button_color = (80, 100, 140, 200)
            label_color = self.text_secondary
        self._rounded_rect(button_surface, button_color, button_surface.get_rect(), radius=14)
        self._rounded_rect(
            button_surface,
            (255, 255, 255, 70),
            button_surface.get_rect(),
            width=1,
            radius=14,
        )
        label_text = "Pulse starten" if not self.active_pulse else "Pulse läuft…"
        label_surface = self.font.render(label_text, True, label_color)
        label_rect = label_surface.get_rect(
            center=(button_surface.get_width() // 2, button_surface.get_height() // 2 - 6)
        )
        button_surface.blit(label_surface, label_rect)
        shortcut_surface = self.small_font.render("SPACE", True, self.text_secondary)
        shortcut_rect = shortcut_surface.get_rect(
            center=(button_surface.get_width() // 2, button_surface.get_height() - 12)
        )
        button_surface.blit(shortcut_surface, shortcut_rect)
        self.screen.blit(button_surface, button_rect.topleft)

        status_text = self._footer_status_text()
        if status_text:
            status_surface = self.small_font.render(status_text, True, self.text_primary)
            status_rect = status_surface.get_rect(
                midleft=(footer_rect.x + 24, footer_rect.y + footer_rect.height // 2)
            )
            self.screen.blit(status_surface, status_rect)
        return footer_rect

    def _draw_metadata(
        self,
        banner_rect: pygame.Rect,
        sidebar_rect: pygame.Rect,
        footer_rect: pygame.Rect,
    ) -> None:
        metadata: Dict[str, str] = self.playthrough.get("metadata", {}) if self.playthrough else {}
        level_name = metadata.get("name", "Unbenanntes Level")
        difficulty = metadata.get("difficulty", "???")

        title_surface = self.bold_font.render(level_name, True, self.text_primary)
        subtitle_surface = self.small_font.render(
            f"Schwierigkeit: {difficulty}", True, self.text_secondary
        )
        self.screen.blit(title_surface, (banner_rect.x + 28, banner_rect.y + 16))
        self.screen.blit(
            subtitle_surface,
            (
                banner_rect.x + 28,
                banner_rect.y + 16 + title_surface.get_height() + 4,
            ),
        )

        if self.mode == "play":
            back_rect = pygame.Rect(banner_rect.x + 20, banner_rect.y + 18, 120, 40)
            back_surface = self._alpha_surface(back_rect.size)
            self._rounded_rect(back_surface, (70, 90, 140, 200), back_surface.get_rect(), radius=12)
            self._rounded_rect(back_surface, (255, 255, 255, 110), back_surface.get_rect(), width=2, radius=12)
            back_label = self.font.render("Zur Karte", True, self.text_primary)
            back_surface.blit(back_label, back_label.get_rect(center=(back_rect.width // 2, back_rect.height // 2)))
            self.screen.blit(back_surface, back_rect.topleft)
            self.back_button_rect = back_rect
        else:
            self.back_button_rect = pygame.Rect(0, 0, 0, 0)

        score_text = self.bold_font.render(f"Score {self.score:,}", True, self.text_primary)
        streak_text = self.small_font.render(
            f"Combo x{self.combo + 1}", True, self.text_secondary
        )
        header_right = banner_rect.right - 28
        score_rect = score_text.get_rect(topright=(header_right, banner_rect.y + 16))
        streak_rect = streak_text.get_rect(topright=(header_right, score_rect.bottom + 6))
        self.screen.blit(score_text, score_rect)
        self.screen.blit(streak_text, streak_rect)

        history_y = streak_rect.bottom + 6
        for last_level, points in self.points_history[-3:][::-1]:
            history_surface = self.small_font.render(
                f"+{points} | {last_level}", True, self.text_secondary
            )
            history_rect = history_surface.get_rect(topright=(header_right, history_y))
            self.screen.blit(history_surface, history_rect)
            history_y += history_surface.get_height() + 4

        content_top = sidebar_rect.y + 28
        content_margin = 24
        column_gap = 20
        available_width = sidebar_rect.width - content_margin * 2
        min_tool_width = 140
        min_target_width = 160
        two_column = available_width >= (min_tool_width + min_target_width + column_gap)
        target_x = sidebar_rect.x + content_margin
        tool_x = target_x
        target_width = available_width
        tool_width = available_width
        if two_column:
            target_width = max(min_target_width, int(available_width * 0.55))
            tool_width = available_width - target_width - column_gap
            if tool_width < min_tool_width:
                tool_width = min_tool_width
                target_width = max(min_target_width, available_width - tool_width - column_gap)
            tool_x = target_x + target_width + column_gap
        target_y = content_top
        target_energy = self._current_target_energy()
        total_energy = sum(target_energy.values())
        energy_goal = getattr(self.level, "energy_goal", None) if self.level else None
        heading = self.font.render("Ziele", True, self.text_primary)
        self.screen.blit(heading, (target_x, target_y))
        target_y += heading.get_height() + 12
        bar_width = target_width
        bar_height = 12
        for position, target in sorted(self.level.targets.items()):
            delivered = target_energy.get(position, 0)
            required = max(1, target.required_energy)
            label_text = target.label or f"Ziel {position[0]}, {position[1]}"
            label_surface = self.small_font.render(label_text, True, self.text_primary)
            self.screen.blit(label_surface, (target_x, target_y))
            target_y += label_surface.get_height() + 2
            stage_surface = self.small_font.render(
                f"{self._energy_stage_label(delivered)} / Ziel {self._energy_stage_label(target.required_energy)}",
                True,
                self.text_secondary,
            )
            self.screen.blit(stage_surface, (target_x, target_y))
            target_y += stage_surface.get_height() + 6
            bar_rect = pygame.Rect(target_x, target_y, bar_width, bar_height)
            pygame.draw.rect(self.screen, (34, 46, 70), bar_rect, border_radius=bar_height // 2)
            fill_ratio = 0.0 if required == 0 else min(delivered / required, 1.0)
            fill_width = int(bar_width * fill_ratio)
            if fill_width > 0:
                fill_rect = pygame.Rect(target_x, target_y, fill_width, bar_height)
                color = self._energy_stage_color(delivered)
                pygame.draw.rect(self.screen, color, fill_rect, border_radius=bar_height // 2)
            pygame.draw.rect(self.screen, (255, 255, 255, 90), bar_rect, width=1, border_radius=bar_height // 2)
            target_y += bar_height + 12
        summary_text = f"Gesamtenergie {total_energy}"
        if energy_goal is not None:
            summary_text += f" / Ziel {energy_goal}"
        summary_surface = self.small_font.render(summary_text, True, self.text_primary)
        self.screen.blit(summary_surface, (target_x, target_y))
        target_y += summary_surface.get_height() + 10
        legend_title = self.small_font.render("Energieskala", True, self.text_secondary)
        self.screen.blit(legend_title, (target_x, target_y))
        target_y += legend_title.get_height() + 6
        legend_box = 12
        for idx, name in enumerate(self.energy_stage_names):
            color = self.energy_palette[idx]
            box_rect = pygame.Rect(target_x, target_y + idx * (legend_box + 6), legend_box, legend_box)
            pygame.draw.rect(self.screen, color, box_rect)
            pygame.draw.rect(self.screen, (24, 30, 46), box_rect, width=1)
            label = self.small_font.render(name, True, self.text_secondary)
            self.screen.blit(label, (box_rect.right + 8, box_rect.y - 1))
        target_y += len(self.energy_stage_names) * (legend_box + 6) + 16
        if two_column:
            tool_y = content_top
        else:
            tool_y = target_y + 12
        tool_end = self._draw_tool_palette(tool_x, tool_y, tool_width)
        if two_column:
            content_bottom = max(target_y, tool_end)
        else:
            content_bottom = tool_end
        show_controls = self.show_instructions or time.perf_counter() < self.instructions_visible_until
        controls_y = content_bottom + 12
        controls_x = target_x
        if show_controls:
            controls_heading = self.font.render("Steuerung", True, self.text_primary)
            self.screen.blit(controls_heading, (controls_x, controls_y))
            controls_y += controls_heading.get_height() + 12
            controls = [
                ("Links/Rechts", "Level wechseln"),
                ("N/P", "Naechstes/Vorheriges Level"),
                ("Linksklick", "Spiegel platzieren"),
                ("Rechtsklick", "Spiegel entfernen"),
                ("SPACE", "Pulse starten"),
                ("H", "Hilfetext ein/aus"),
            ]
            for keys, desc in controls:
                keys_surface = self.small_font.render(keys, True, self.text_primary)
                desc_surface = self.small_font.render(desc, True, self.text_secondary)
                self.screen.blit(keys_surface, (controls_x, controls_y))
                self.screen.blit(desc_surface, (controls_x + 110, controls_y))
                controls_y += max(keys_surface.get_height(), desc_surface.get_height()) + 8
        else:
            hint_surface = self.small_font.render("Druecke H fuer Hilfe", True, self.text_secondary)
            self.screen.blit(hint_surface, (controls_x, controls_y))
        
    def _draw_grid(self) -> None:
        assert self.level and self.geometry
        geometry = self.geometry
        for x in range(self.level.width + 1):
            start = (
                geometry.origin[0] + x * geometry.cell_size,
                geometry.origin[1],
            )
            end = (
                start[0],
                geometry.origin[1] + self.level.height * geometry.cell_size,
            )
            pygame.draw.line(self.screen, self.grid_color, start, end, 1)
        for y in range(self.level.height + 1):
            start = (
                geometry.origin[0],
                geometry.origin[1] + y * geometry.cell_size,
            )
            end = (
                geometry.origin[0] + self.level.width * geometry.cell_size,
                start[1],
            )
            pygame.draw.line(self.screen, self.grid_color, start, end, 1)

    def _draw_emitters(self) -> None:
        assert self.level and self.geometry
        size = self.geometry.cell_size
        for emitter in self.level.emitters:
            top_left = self.geometry.cell_to_topleft(emitter.position)
            icon = self._get_icon_surface(
                "emitter",
                size,
                f"{emitter.direction.name}|{emitter.brightness:.2f}",
            )
            self.screen.blit(icon, top_left)

    def _draw_targets(self) -> None:
        assert self.level and self.geometry
        size = self.geometry.cell_size
        target_energy = self._current_target_energy()
        for position, target in self.level.targets.items():
            top_left = self.geometry.cell_to_topleft(position)
            icon = self._get_icon_surface("target", size)
            self.screen.blit(icon, top_left)
            delivered = target_energy.get(position, 0)
            if delivered >= target.required_energy:
                overlay = self._alpha_surface((size, size))
                pygame.draw.circle(
                    overlay,
                    (
                        self.target_color[0],
                        self.target_color[1],
                        self.target_color[2],
                        100,
                    ),
                    (size // 2, size // 2),
                    size // 2,
                )
                self.screen.blit(overlay, top_left, special_flags=pygame.BLEND_RGBA_ADD)
            else:
                progress = delivered / max(1, target.required_energy)
                if progress > 0:
                    ring = self._alpha_surface((size, size))
                    rect = ring.get_rect().inflate(-int(size * 0.22), -int(size * 0.22))
                    pygame.draw.arc(
                        ring,
                        (
                            self.target_color[0],
                            self.target_color[1],
                            self.target_color[2],
                            200,
                        ),
                        rect,
                        -math.pi / 2,
                        -math.pi / 2 + progress * 2 * math.pi,
                        max(2, size // 18),
                    )
                    self.screen.blit(ring, top_left)
            label = self.small_font.render(
                f"L{delivered}/L{target.required_energy}",
                True,
                self.text_primary,
            )
            label_rect = label.get_rect(
                center=(top_left[0] + size // 2, top_left[1] + size - label.get_height() // 2 - 4)
            )
            self.screen.blit(label, label_rect)

    def _build_mirror_icon(self, size: int, extra: str) -> pygame.Surface:
        surface = self._alpha_surface((size, size))
        rect = surface.get_rect()
        body_rect = rect.inflate(-int(size * 0.12), -int(size * 0.12))
        pygame.draw.rect(surface, (62, 78, 112), body_rect, border_radius=int(size * 0.14))
        pygame.draw.rect(
            surface,
            (180, 192, 220, 220),
            body_rect,
            width=max(2, size // 26),
            border_radius=int(size * 0.14),
        )
        gradient = self._alpha_surface(body_rect.size)
        for y in range(body_rect.height):
            ratio = y / max(1, body_rect.height - 1)
            color = (
                int(150 + 40 * (1 - ratio)),
                int(180 + 30 * (1 - ratio)),
                int(210 + 20 * (1 - ratio)),
                200,
            )
            pygame.draw.line(gradient, color, (0, y), (body_rect.width, y))
        surface.blit(gradient, body_rect.topleft, special_flags=pygame.BLEND_RGBA_MIN)
        orientation = extra or "/"
        offset = int(size * 0.18)
        if orientation == "\\":
            start = (body_rect.left + offset, body_rect.top + offset)
            end = (body_rect.right - offset, body_rect.bottom - offset)
        else:
            start = (body_rect.left + offset, body_rect.bottom - offset)
            end = (body_rect.right - offset, body_rect.top + offset)
        pygame.draw.line(surface, (255, 255, 255, 220), start, end, max(3, size // 18))
        pygame.draw.line(surface, (120, 210, 255, 200), start, end, max(1, size // 32))
        return surface

    def _draw_tool_palette(self, x: int, start_y: int, width: int) -> int:
        self.toolbar_buttons = []
        y = start_y
        heading = self.font.render("Werkzeuge", True, self.text_primary)
        self.screen.blit(heading, (x, y))
        y += heading.get_height() + 12
        button_width = width
        button_height = 48
        icon_map = {
            "mirror": ("mirror", "/"),
            "splitter": ("splitter", "dual"),
            "splitter_triple": ("splitter", "triple"),
            "splitter_cross": ("splitter", "cross"),
            "amplifier": ("amplifier", ""),
            "bomb": ("bomb", ""),
        }
        icon_padding = 12
        icon_size = max(24, min(button_height - 12, button_width - 120))
        for tool in self.tool_palette:
            rect = pygame.Rect(x, y, button_width, button_height)
            self.toolbar_buttons.append((rect, tool["id"]))
            surface = self._alpha_surface((button_width, button_height))
            color = (96, 126, 196, 200) if tool["id"] == self.selected_tool else (70, 82, 130, 150)
            self._rounded_rect(surface, color, surface.get_rect(), radius=14)
            border_color = (255, 255, 255, 140) if tool["id"] == self.selected_tool else (110, 124, 178, 120)
            self._rounded_rect(surface, border_color, surface.get_rect(), width=2, radius=14)
            icon_name, variant = icon_map.get(tool["id"], ("mirror", "/"))
            if icon_size > 0:
                icon = self._get_icon_surface(icon_name, icon_size, variant)
                surface.blit(icon, (icon_padding, (button_height - icon_size) // 2))
            text_x = icon_padding + max(icon_size, 24) + 16
            label = self.font.render(tool["label"], True, self.text_primary)
            label_rect = label.get_rect(midleft=(text_x, surface.get_height() // 2 - 8))
            surface.blit(label, label_rect)
            hint = self.small_font.render(tool["hint"], True, self.text_secondary)
            hint_rect = hint.get_rect(topleft=(text_x, label_rect.bottom - 2))
            surface.blit(hint, hint_rect)
            limit_text = self._tool_limit_text(tool["id"])
            if limit_text:
                count_text = self.small_font.render(limit_text, True, self.text_primary)
                count_rect = count_text.get_rect(topright=(surface.get_width() - 14, 10))
                surface.blit(count_text, count_rect)
            self.screen.blit(surface, rect.topleft)
            y += button_height + 10
        return y

    def _normalise_tool_id(self, tool_id: str) -> str:
        if tool_id.startswith("splitter"):
            if tool_id in ("splitter_triple", "splitter_cross"):
                return tool_id
            return "splitter"
        return tool_id

    def _tool_limit_text(self, tool_id: str) -> Optional[str]:
        key = self._normalise_tool_id(tool_id)
        limit = self.base_tool_limits.get(key)
        if limit is None:
            return None
        remaining = self.remaining_tools.get(key, limit)
        return f"{remaining}/{limit}"

    def _draw_mirrors(self) -> None:
        assert self.level and self.geometry
        size = self.geometry.cell_size
        for position, mirror in self.level.mirrors.items():
            icon = self._get_icon_surface("mirror", size, mirror.orientation)
            self.screen.blit(icon, self.geometry.cell_to_topleft(position))

    def _draw_splitters(self) -> None:
        assert self.level and self.geometry
        size = self.geometry.cell_size
        for position, splitter in self.level.splitters.items():
            icon = self._get_icon_surface("splitter", size, splitter.pattern)
            self.screen.blit(icon, self.geometry.cell_to_topleft(position))

    def _draw_amplifiers(self) -> None:
        assert self.level and self.geometry
        size = self.geometry.cell_size
        for position, amplifier in self.level.amplifiers.items():
            top_left = self.geometry.cell_to_topleft(position)
            icon = self._get_icon_surface("amplifier", size)
            self.screen.blit(icon, top_left)
            label = self.small_font.render(
                f"x{amplifier.multiplier:g}", True, (60, 32, 12)
            )
            label_rect = label.get_rect(
                center=(top_left[0] + size // 2, top_left[1] + size - label.get_height() // 2 - 4)
            )
            self.screen.blit(label, label_rect)

    def _draw_obstacles(self) -> None:
        assert self.level and self.geometry
        size = self.geometry.cell_size
        for position, obstacle in self.level.obstacles.items():
            if position in self.hidden_obstacles:
                continue
            top_left = self.geometry.cell_to_topleft(position)
            icon = self._get_icon_surface("obstacle", size)
            if obstacle.durability > 1:
                label = self.small_font.render(str(obstacle.durability), True, self.text_primary)
                icon.blit(label, label.get_rect(center=(size // 2, size // 2)))
            self.screen.blit(icon, top_left)

    def _draw_bombs(self) -> None:
        assert self.level and self.geometry
        size = self.geometry.cell_size
        for position, bomb in self.level.bombs.items():
            top_left = self.geometry.cell_to_topleft(position)
            icon = self._get_icon_surface("bomb", size)
            if bomb.power > 1:
                label = self.small_font.render(str(bomb.power), True, (40, 24, 0))
                icon.blit(label, label.get_rect(center=(size // 2, size // 2)))
            self.screen.blit(icon, top_left)

    def _draw_beam_path(self) -> None:
        if not self.geometry:
            return
        segments: List[BeamSegment] = []
        if self.active_pulse:
            segments = list(self.active_segments)
        tail_length = 0.35
        if self.active_pulse and self.active_segments:
            end_progress = max(0.0, min(1.0, float(self.timeline_progress)))
            start_progress = max(0.0, end_progress - tail_length)
            for segment in self.active_segments:
                if end_progress > 0.0:
                    self._draw_segment(segment, end_progress, start_progress)
                self._draw_pulse_head(segment, end_progress)

    def _draw_segment(
        self, segment: BeamSegment, progress: float, start_progress: float = 0.0
    ) -> None:
        if not self.geometry:
            return
        progress = max(0.0, min(1.0, progress))
        start_progress = max(0.0, min(progress, start_progress))
        if progress <= start_progress:
            return
        start_px = self.geometry.cell_to_center(segment.start)
        end_px = self.geometry.cell_to_center(segment.end)
        delta_x = end_px[0] - start_px[0]
        delta_y = end_px[1] - start_px[1]
        tail_start = (start_px[0] + delta_x * start_progress, start_px[1] + delta_y * start_progress)
        tail_end = (start_px[0] + delta_x * progress, start_px[1] + delta_y * progress)
        base_color = self._beam_color_for_intensity(segment.intensity)
        strength = max(0.2, min(1.0, segment.intensity / 1.6))
        thickness = max(3, int(self.geometry.cell_size * (0.1 + 0.12 * strength)))
        margin = thickness * 2
        min_x = int(min(tail_start[0], tail_end[0]) - margin)
        min_y = int(min(tail_start[1], tail_end[1]) - margin)
        width = int(abs(tail_end[0] - tail_start[0]) + margin * 2) or 2
        height = int(abs(tail_end[1] - tail_start[1]) + margin * 2) or 2
        overlay = self._alpha_surface((width, height))
        local_start = (tail_start[0] - min_x, tail_start[1] - min_y)
        local_end = (tail_end[0] - min_x, tail_end[1] - min_y)
        glow_alpha = int(70 + 120 * strength)
        glow_color = (base_color[0], base_color[1], base_color[2], glow_alpha)
        core_color = (255, 240, 210, 220)
        mid_color = (
            min(255, base_color[0] + 40),
            min(255, base_color[1] + 40),
            min(255, base_color[2] + 40),
            int(120 + 80 * strength),
        )
        pygame.draw.line(overlay, glow_color, local_start, local_end, thickness + thickness // 2)
        pygame.draw.line(overlay, mid_color, local_start, local_end, thickness + 4)
        pygame.draw.line(overlay, core_color, local_start, local_end, thickness)
        self.screen.blit(overlay, (min_x, min_y), special_flags=pygame.BLEND_RGBA_ADD)

    def _draw_pulse_head(self, segment: BeamSegment, progress: float) -> None:
        if not self.geometry:
            return
        start_px = self.geometry.cell_to_center(segment.start)
        end_px = self.geometry.cell_to_center(segment.end)
        point = (
            start_px[0] + (end_px[0] - start_px[0]) * progress,
            start_px[1] + (end_px[1] - start_px[1]) * progress,
        )
        strength = max(0.2, min(1.0, segment.intensity / 1.6))
        color = self._beam_color_for_intensity(segment.intensity)
        radius = max(6, self.geometry.cell_size // 6)
        overlay_size = radius * 4
        overlay = self._alpha_surface((overlay_size, overlay_size))
        center = (overlay_size // 2, overlay_size // 2)
        pygame.draw.circle(overlay, (color[0], color[1], color[2], int(160 + 60 * strength)), center, radius * 2)
        pygame.draw.circle(overlay, (255, 255, 255, 230), center, radius)
        pygame.draw.circle(overlay, (255, 255, 255, 255), center, max(2, radius // 2))
        self.screen.blit(overlay, (point[0] - center[0], point[1] - center[1]), special_flags=pygame.BLEND_RGBA_ADD)

    def _energy_stage_index(self, energy: int) -> int:
        clamped = 0
        try:
            clamped = int(energy)
        except (TypeError, ValueError):
            clamped = 0
        clamped = max(0, min(self.max_energy_level, clamped))
        return clamped

    def _energy_stage_color(self, energy: int) -> Tuple[int, int, int]:
        index = self._energy_stage_index(energy)
        return self.energy_palette[min(index, len(self.energy_palette) - 1)]

    def _energy_stage_label(self, energy: int) -> str:
        index = self._energy_stage_index(energy)
        return self.energy_stage_names[min(index, len(self.energy_stage_names) - 1)]

    def _beam_color_for_intensity(self, intensity: float) -> Tuple[int, int, int]:
        clamped = max(0.3, min(1.6, intensity))
        ratio = (clamped - 0.3) / 1.3
        energy_level = int(round(ratio * self.max_energy_level))
        return self._energy_stage_color(energy_level)

    def _emitter_color(self, brightness: float) -> Tuple[int, int, int]:
        brightness = max(0.3, min(1.6, brightness))
        return tuple(
            min(255, int(channel * (0.5 + 0.5 * brightness))) for channel in self.emitter_color
        )

    def _draw_effects(self) -> None:
        if not self.geometry:
            return
        cell_size = self.geometry.cell_size
        for animation in self.hit_animations:
            progress = min(animation["timer"] / self.hit_animation_duration, 1.0)
            radius = int(cell_size * (0.35 + 0.35 * progress))
            alpha = int(220 * (1 - progress))
            overlay = self._alpha_surface((radius * 2, radius * 2))
            pygame.draw.circle(
                overlay,
                (self.target_color[0], self.target_color[1], self.target_color[2], alpha),
                (radius, radius),
                radius,
            )
            center = self.geometry.cell_to_center(tuple(animation["position"]))
            self.screen.blit(overlay, (center[0] - radius, center[1] - radius))

        for animation in self.explosion_animations:
            progress = min(animation["timer"] / self.explosion_animation_duration, 1.0)
            power = max(1, int(animation.get("power", 1)))
            radius = int(cell_size * (0.5 + progress * 0.8 * power))
            alpha = int(200 * (1 - progress))
            overlay = self._alpha_surface((radius * 2, radius * 2))
            pygame.draw.circle(overlay, (255, 160, 60, alpha), (radius, radius), radius)
            pygame.draw.circle(
                overlay,
                (255, 230, 150, max(80, alpha)),
                (radius, radius),
                max(2, radius // 2),
                width=2,
            )
            center = self.geometry.cell_to_center(tuple(animation["position"]))
            self.screen.blit(overlay, (center[0] - radius, center[1] - radius))

        for particle in self.energy_particles:
            progress = min(particle["life"] / particle["duration"], 1.0)
            alpha = int(180 * (1 - progress))
            if alpha <= 0:
                continue
            radius = max(2, int(self.geometry.cell_size * (0.1 + 0.08 * (1 - progress))))
            overlay = self._alpha_surface((radius * 2, radius * 2))
            color = particle["color"]
            pygame.draw.circle(
                overlay, (color[0], color[1], color[2], alpha), (radius, radius), radius
            )
            self.screen.blit(
                overlay,
                (particle["pos"][0] - radius, particle["pos"][1] - radius),
                special_flags=pygame.BLEND_RGBA_ADD,
            )

        if self.level_complete_time:
            elapsed = time.perf_counter() - self.level_complete_time
            if elapsed < self.level_complete_flash_duration:
                alpha = int(200 * (1 - elapsed / self.level_complete_flash_duration))
                overlay = self._alpha_surface(self.screen.get_size())
                overlay.fill((40, 80, 60, alpha))
                self.screen.blit(overlay, (0, 0))
                message = self.bold_font.render("Level geschafft!", True, self.text_primary)
                rect = message.get_rect(center=(self.screen.get_width() // 2, 100))
                self.screen.blit(message, rect)
            else:
                self.level_complete_time = None

    def _update_pulse_animation(self, delta: float) -> None:
        if not self.active_pulse:
            return
        if not self.timeline:
            self.active_pulse = False
            self.render_segments = []
            return
        if self.timeline_index >= len(self.timeline):
            self.active_pulse = False
            return
        if not self.active_segments and self.timeline_index < len(self.timeline):
            self.active_segments = self.timeline[self.timeline_index]
        distance = self.pulse_speed * delta
        while distance > 0 and self.timeline_index < len(self.timeline):
            remaining = 1.0 - self.timeline_progress
            if distance >= remaining:
                distance -= remaining
                for segment in self.timeline[self.timeline_index]:
                    self._handle_segment_completion(segment)
                self.timeline_index += 1
                self.timeline_progress = 0.0
                if self.timeline_index < len(self.timeline):
                    self.active_segments = self.timeline[self.timeline_index]
                else:
                    self.active_segments = []
            else:
                self.timeline_progress += distance
                distance = 0.0
        if self.timeline_index >= len(self.timeline):
            self.render_segments = []
            self.completed_segments = []
            self.active_pulse = False
            self.active_segments = []
            if self.game and self.game.level_complete():
                self.level_complete_time = time.perf_counter()
                self._on_level_complete()
            else:
                self.combo = 0
            if self.game:
                self.visible_target_energy = dict(self.game.target_energy)

    def _update_effects(self, delta: float) -> None:
        for animation in self.hit_animations:
            animation["timer"] += delta
        self.hit_animations = [
            animation
            for animation in self.hit_animations
            if animation["timer"] < self.hit_animation_duration
        ]

        for animation in self.explosion_animations:
            animation["timer"] += delta
        self.explosion_animations = [
            animation
            for animation in self.explosion_animations
            if animation["timer"] < self.explosion_animation_duration
        ]

        updated_particles = []
        for particle in self.energy_particles:
            particle["life"] += delta
            if particle["life"] >= particle["duration"]:
                continue
            particle["pos"][0] += particle["vel"][0] * delta
            particle["pos"][1] += particle["vel"][1] * delta
            particle["vel"][0] *= 0.78
            particle["vel"][1] *= 0.78
            updated_particles.append(particle)
        self.energy_particles = updated_particles

        if self.show_instructions and time.perf_counter() > self.instructions_visible_until:
            self.show_instructions = False

    def _handle_segment_completion(self, segment: BeamSegment) -> None:
        position = segment.end
        self._consume_hit(position)
        self._consume_explosion(position)
        self._consume_obstacle_removal(position)

    def _consume_hit(self, position: Tuple[int, int]) -> None:
        for index, event in enumerate(self.hit_queue):
            event_position = event.get("position")
            if event_position is None:
                continue
            if tuple(event_position) == position:
                self.hit_animations.append({"position": position, "timer": 0.0})
                delivered = int(event.get("energy", 0))
                current_level = self.visible_target_energy.get(position, 0)
                if delivered > current_level:
                    self.visible_target_energy[position] = delivered
                target = self.level.targets.get(position) if self.level else None
                if target is not None and delivered > 0:
                    self._spawn_energy_particles(position, delivered)
                self.hit_queue.pop(index)
                break

    def _consume_explosion(self, position: Tuple[int, int]) -> None:
        for index, event in enumerate(self.explosion_queue):
            event_position = event.get("position")
            if event_position is None:
                continue
            if tuple(event_position) == position:
                power = int(event.get("power", 1))
                self.explosion_animations.append(
                    {"position": position, "power": power, "timer": 0.0}
                )
                cleared = event.get("cleared") or []
                for cleared_position in cleared:
                    self._apply_obstacle_removal(tuple(cleared_position))
                self.explosion_queue.pop(index)
                break

    def _consume_obstacle_removal(self, position: Tuple[int, int]) -> None:
        for index, event in enumerate(self.obstacle_removal_queue):
            event_position = event.get("position")
            if event_position is None:
                continue
            if tuple(event_position) == position:
                self._apply_obstacle_removal(tuple(event_position))
                self.obstacle_removal_queue.pop(index)
                break

    def _apply_obstacle_removal(self, position: Optional[Tuple[int, int]]) -> None:
        if position is None:
            return
        if self.level and not self.level.inside(position):
            return
        self.hidden_obstacles.add(tuple(position))

    def _on_level_complete(self) -> None:
        if not self.level:
            return
        name = self.level.name
        difficulty = self.level.metadata.get("difficulty", "Unknown")
        base_points = 500 + 80 * len(self.level.targets)
        difficulty_bonus = {
            "Easy": 200,
            "Medium": 350,
            "Hard": 500,
            "Very Hard": 750,
            "Expert": 900,
        }.get(difficulty, 400)
        elapsed = max(0.1, time.perf_counter() - self.level_start_time)
        time_bonus = max(150, int(900 - elapsed * 90))
        streak_bonus = 200 * self.combo
        tool_bonus = sum(self.remaining_tools.values()) * 75
        total = base_points + difficulty_bonus + streak_bonus + time_bonus + tool_bonus
        if not self.completed_levels.get(name):
            total += 250
        self.score += total
        self.combo += 1
        self.completed_levels[name] = True
        self.points_history.append((f"{name} (+{time_bonus} Zeit/+{tool_bonus} Tools)", total))
        if self.game:
            self.visible_target_energy = dict(self.game.target_energy)
        # automatically advance to next level after short celebration
        self.footer_visible_until = time.perf_counter() + 8.0

    def fire_pulse(self) -> None:
        if not self.game or self.active_pulse:
            return
        self.game.apply_pending_placements()
        summary = self.game.playthrough()
        timeline_data = summary.get("timeline", []) if summary else []
        self._clear_pulse_state()
        self.playthrough = summary

        segments_timeline: List[List[BeamSegment]] = []
        flattened_segments: List[BeamSegment] = []

        for frame in timeline_data:
            frame_segments: List[BeamSegment] = []
            tick_value = frame.get("tick")
            for raw_segment in frame.get("segments", []):
                segment = self._coerce_segment(raw_segment)
                if not segment:
                    continue
                if tick_value is not None:
                    try:
                        segment.tick = int(tick_value)
                    except (TypeError, ValueError):
                        segment.tick = segment.tick or 0
                frame_segments.append(segment)
                flattened_segments.append(segment)
            segments_timeline.append(frame_segments)

        if segments_timeline:
            self.timeline = segments_timeline
            self.active_pulse = True
            self.timeline_index = 0
            self.timeline_progress = 0.0
            self.active_segments = self.timeline[0] if self.timeline else []
        else:
            self.timeline = []
            self.active_pulse = False
            self.active_segments = []

        events = summary.get("events", {}) if summary else {}

        self.hit_queue = [
            {
                "position": tuple(event.get("position")),
                "label": event.get("label", ""),
                "energy": int(event.get("energy", 0)),
                "required": int(event.get("required", 0)),
            }
            for event in events.get("hits", [])
            if event.get("position") is not None
        ]
        self.explosion_queue = [
            {
                "position": tuple(event.get("position")),
                "power": event.get("power", 1),
                "cleared": event.get("cleared", []),
            }
            for event in events.get("explosions", [])
            if event.get("position") is not None
        ]
        self.obstacle_removal_queue = [
            {
                "position": tuple(event.get("position")),
                "cause": event.get("cause", "laser"),
            }
            for event in events.get("obstacles_removed", [])
            if event.get("position") is not None
        ]

        if events.get("overflow"):
            self.points_history.append(("Energie-Overload", 0))

        if not self.active_pulse:
            self.render_segments = []
            while self.obstacle_removal_queue:
                removal = self.obstacle_removal_queue.pop(0)
                self._apply_obstacle_removal(removal.get("position"))
            for explosion in self.explosion_queue:
                cleared = explosion.get("cleared") or []
                for position in cleared:
                    self._apply_obstacle_removal(tuple(position))
            self.explosion_queue = []
            if self.game and self.game.level_complete():
                self.level_complete_time = time.perf_counter()
                self._on_level_complete()
            else:
                self.combo = 0
            if self.game:
                self.visible_target_energy = dict(self.game.target_energy)
        else:
            self.render_segments = []

        if summary and summary.get("loop_detected"):
            self.points_history.append(("Loop entdeckt", 0))

        self.footer_visible_until = time.perf_counter() + 5.0
        self.show_instructions = False

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            raise SystemExit
        if self.mode == "intro":
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_RETURN):
                self.start_game()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.start_button_rect.collidepoint(event.pos):
                    self.start_game()
            return
        if self.mode == "map":
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.mode = "intro"
                    return
                if event.key in (pygame.K_RIGHT, pygame.K_n):
                    self._enter_level(self.level_index + 1)
                    return
                if event.key in (pygame.K_LEFT, pygame.K_p):
                    self._enter_level(self.level_index - 1)
                    return
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self._enter_level(self.level_index)
                    return
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for node in self.level_nodes:
                    if node["rect"].collidepoint(event.pos):
                        self._enter_level(node["index"])
                        return
            return
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RIGHT, pygame.K_n):
                self.cycle_level(1)
            elif event.key in (pygame.K_LEFT, pygame.K_p):
                self.cycle_level(-1)
            elif event.key == pygame.K_SPACE:
                self.fire_pulse()
            elif event.key == pygame.K_h:
                self.show_instructions = not self.show_instructions
                if self.show_instructions:
                    self.instructions_visible_until = time.perf_counter() + 12.0
            elif event.key == pygame.K_r:
                if self._recent_placement and self._recent_placement[0] == "mirror":
                    self._place_or_toggle_mirror(self._recent_placement[1])
                else:
                    self._set_status_message("Kein Spiegel ausgewaehlt", 1.2)
            elif event.key == pygame.K_F11:
                self._toggle_fullscreen()
            elif event.key == pygame.K_ESCAPE:
                self._go_to_map()
        if event.type == pygame.MOUSEBUTTONDOWN and self.level:
            if event.button == 1:
                if self.back_button_rect.collidepoint(event.pos):
                    self._go_to_map()
                    return
                if self.button_rect.collidepoint(event.pos):
                    self.fire_pulse()
                    return
                if self._handle_tool_click(event.pos):
                    return
            grid_position = self._position_from_mouse(event.pos)
            if grid_position is not None:
                if event.button == 1:
                    self._place_selected_tool(grid_position)
                elif event.button == 3:
                    self._remove_item(grid_position)
        if event.type == pygame.VIDEORESIZE:
            self._handle_resize(event.size)

    def _position_from_mouse(
        self, position: Tuple[int, int]
    ) -> Optional[Tuple[int, int]]:
        if not self.geometry or not self.level:
            return None
        x, y = position
        origin_x, origin_y = self.geometry.origin
        if not (origin_x <= x < origin_x + self.level.width * self.geometry.cell_size):
            return None
        if not (origin_y <= y < origin_y + self.level.height * self.geometry.cell_size):
            return None
        grid_x = (x - origin_x) // self.geometry.cell_size
        grid_y = (y - origin_y) // self.geometry.cell_size
        return (int(grid_x), int(grid_y))

    def _place_or_toggle_mirror(self, cell: Tuple[int, int]) -> None:
        assert self.level
        self.level.splitters.pop(cell, None)
        self.level.amplifiers.pop(cell, None)
        self.level.bombs.pop(cell, None)
        mirror = self.level.mirrors.get(cell)
        if mirror:
            mirror.orientation = "/" if mirror.orientation == "\\" else "\\"
            self._set_status_message("Spiegel gedreht", 1.2)
        else:
            self.level.mirrors[cell] = Mirror("/")
            self._set_status_message("Spiegel platziert", 1.2)
        self.rotation_locked_cell = None
        self.rotation_lock_expires = 0.0
        self._recent_placement = ("mirror", cell)
        self._needs_update = True
        self._clear_pulse_state(reset_game=True)

    def _remove_mirror(self, cell: Tuple[int, int]) -> None:
        assert self.level
        if cell in self.level.mirrors:
            del self.level.mirrors[cell]
            self._needs_update = True
            self._clear_pulse_state(reset_game=True)

    def _place_selected_tool(self, cell: Tuple[int, int]) -> None:
        assert self.level
        tool = self.selected_tool
        limit_key = self._normalise_tool_id(tool)
        limit = self.remaining_tools.get(limit_key)
        placing_new = True
        if tool == "mirror":
            placing_new = cell not in self.level.mirrors
        if placing_new and limit is not None and limit <= 0:
            self._set_status_message("Keine Werkzeuge dieser Art mehr verfuegbar", 2.5)
            self.footer_visible_until = max(self.footer_visible_until, time.perf_counter() + 2.5)
            return
        if tool == "mirror":
            self._place_or_toggle_mirror(cell)
            if placing_new and limit is not None:
                self.remaining_tools[limit_key] = limit - 1
            return
        self.rotation_locked_cell = None
        self.rotation_lock_expires = 0.0
        self._recent_placement = (tool, cell)
        if tool.startswith("splitter"):
            pattern = "dual"
            if tool == "splitter_triple":
                pattern = "triple"
            elif tool == "splitter_cross":
                pattern = "cross"
            self.level.splitters[cell] = Splitter(pattern=pattern)
            self.level.mirrors.pop(cell, None)
            self.level.prisms.pop(cell, None)
            self.level.amplifiers.pop(cell, None)
        elif tool == "amplifier":
            self.level.amplifiers[cell] = Amplifier(multiplier=2.0, additive=0)
            self.level.mirrors.pop(cell, None)
            self.level.splitters.pop(cell, None)
            self.level.prisms.pop(cell, None)
        elif tool == "bomb":
            self.level.bombs[cell] = Bomb(power=2)
            self.level.mirrors.pop(cell, None)
            self.level.splitters.pop(cell, None)
            self.level.prisms.pop(cell, None)
        else:
            self._place_or_toggle_mirror(cell)
            return
        if limit is not None:
            self.remaining_tools[limit_key] = limit - 1
        tool_name = tool.replace("_", " ").title()
        self._set_status_message(f"{tool_name} platziert", 1.6)
        self._needs_update = True
        self._clear_pulse_state(reset_game=True)

    def _remove_item(self, cell: Tuple[int, int]) -> None:
        assert self.level
        removed = False
        if cell in self.level.mirrors:
            del self.level.mirrors[cell]
            removed = True
            self._increment_tool("mirror")
        if cell in self.level.splitters:
            pattern = self.level.splitters[cell].pattern
            del self.level.splitters[cell]
            removed = True
            tool_id = {
                "triple": "splitter_triple",
                "cross": "splitter_cross",
            }.get(pattern, "splitter")
            self._increment_tool(tool_id)
        if cell in self.level.amplifiers:
            del self.level.amplifiers[cell]
            removed = True
            self._increment_tool("amplifier")
        if cell in self.level.bombs:
            del self.level.bombs[cell]
            removed = True
            self._increment_tool("bomb")
        if removed:
            self.rotation_locked_cell = None
            self.rotation_lock_expires = 0.0
            self._set_status_message("Platz freigegeben", 1.4)
            self._needs_update = True
            self._clear_pulse_state(reset_game=True)

    def _handle_tool_click(self, position: Tuple[int, int]) -> bool:
        for rect, tool_id in self.toolbar_buttons:
            if rect.collidepoint(position):
                self.selected_tool = tool_id
                self.rotation_locked_cell = None
                self.rotation_lock_expires = 0.0
                self._recent_placement = None
                label = next((tool["label"] for tool in self.tool_palette if tool["id"] == tool_id), tool_id.title())
                self._set_status_message(f"{label} aktiv", 1.5)
                self.footer_visible_until = time.perf_counter() + 4.0
                return True
        return False

    def _increment_tool(self, tool_id: str) -> None:
        key = self._normalise_tool_id(tool_id)
        if key in self.remaining_tools:
            self.remaining_tools[key] += 1

    def _toggle_fullscreen(self) -> None:
        if self.fullscreen:
            self.fullscreen = False
            self.screen_flags = pygame.RESIZABLE
            self.screen = pygame.display.set_mode(self.windowed_size, self.screen_flags)
        else:
            self.windowed_size = self.screen.get_size()
            self.fullscreen = True
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self._needs_update = True
        self.geometry = self._compute_geometry()
        if self.mode == "map":
            self._build_level_nodes()

    def _handle_resize(self, size: Tuple[int, int]) -> None:
        if self.fullscreen:
            return
        self.windowed_size = size
        self.screen = pygame.display.set_mode(size, self.screen_flags)
        self._needs_update = True
        self.geometry = self._compute_geometry()
        if self.mode == "map":
            self._build_level_nodes()

    def _go_to_map(self) -> None:
        self.mode = "map"
        self._clear_pulse_state(reset_game=True)
        self._build_level_nodes()
        self.geometry = self._compute_geometry()
        
    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def run(self) -> None:
        while True:
            now = time.perf_counter()
            delta = now - self.last_time
            self.last_time = now
            for event in pygame.event.get():
                try:
                    self.handle_event(event)
                except SystemExit:
                    pygame.quit()
                    return
            if self.mode == "play":
                self.update_playthrough()
                self._update_pulse_animation(delta)
                self._update_effects(delta)
            self.draw()
            self.clock.tick(60)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _coerce_segment(data: object) -> Optional[BeamSegment]:
        if isinstance(data, BeamSegment):
            return data
        if isinstance(data, dict):
            try:
                start = tuple(data["start"])  # type: ignore[arg-type]
                end = tuple(data["end"])  # type: ignore[arg-type]
                direction_value = data.get("direction")
                intensity_value = float(data.get("intensity", 1.0))
            except (KeyError, TypeError):
                return None
            direction: Optional[Direction]
            if isinstance(direction_value, Direction):
                direction = direction_value
            elif isinstance(direction_value, str):
                try:
                    direction = Direction.from_name(direction_value)
                except ValueError:
                    direction = None
            else:
                direction = None
            tick_value = data.get("tick")
            try:
                tick = int(tick_value) if tick_value is not None else 0
            except (TypeError, ValueError):
                tick = 0
            energy_value = int(data.get("energy", 0)) if isinstance(data, dict) else 0
            brightness_value = float(data.get("brightness", 1.0)) if isinstance(data, dict) else 1.0
            lifetime_value = int(data.get("lifetime", 1)) if isinstance(data, dict) else 1
            source_energy_value = int(data.get("source_energy", max(1, energy_value))) if isinstance(data, dict) else max(1, energy_value or 1)
            segment = BeamSegment(
                start=start,
                end=end,
                direction=direction,
                energy=energy_value,
                intensity=max(0.2, float(intensity_value)),
                tick=tick,
                lifetime=max(1, lifetime_value),
                brightness=brightness_value,
                source_energy=max(1, source_energy_value),
            )
            return segment
        return None


def run() -> None:
    """Entry point helper that instantiates and runs the UI."""

    app = LaserGameApp()
    app.run()


def main() -> UIDirectories:
    """Return resolved directories and print a short bootstrap message."""

    directories = resolve_directories()
    message = (
        "Laser Game UI bootstrap\n"
        f"  assets: {directories.asset_root}\n"
        f"  levels: {directories.level_root}\n"
        "Set the environment variables to point to custom directories if needed."
    )
    print(message)
    return directories


if __name__ == "__main__":  # pragma: no cover - manual invocation entry point
    parser = argparse.ArgumentParser(description="Laser Game UI launcher")
    parser.add_argument(
        "--info",
        action="store_true",
        help="Print resolved resource directories and exit without launching the UI.",
    )
    args = parser.parse_args()

    if args.info:
        main()
    else:
        # Print the bootstrap message before showing the interactive window so
        # users can discover how to customise asset/level paths.
        main()
        run()









