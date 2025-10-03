"""Interactive UI for visualising laser levels using pygame."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pygame

from ..game import BeamSegment, Direction, LaserGame, Level, LevelLoader, Mirror


@dataclass
class GridGeometry:
    """Geometry helpers derived from the current level and screen size."""

    origin: Tuple[int, int]
    cell_size: int

    def cell_to_topleft(self, cell: Tuple[int, int]) -> Tuple[int, int]:
        x, y = cell
        return (self.origin[0] + x * self.cell_size, self.origin[1] + y * self.cell_size)

    def cell_to_center(self, cell: Tuple[int, int]) -> Tuple[int, int]:
        top_left = self.cell_to_topleft(cell)
        return (
            top_left[0] + self.cell_size // 2,
            top_left[1] + self.cell_size // 2,
        )


class LaserGameApp:
    """Pygame driven application for the laser puzzle."""

    background_color = (15, 18, 32)
    grid_color = (60, 65, 90)
    beam_color = (255, 90, 20)
    emitter_color = (110, 200, 255)
    target_color = (120, 255, 140)
    mirror_color = (240, 240, 240)

    def __init__(self, screen_size: Tuple[int, int] = (960, 720)) -> None:
        pygame.init()
        pygame.display.set_caption("Laser Game")
        self.screen = pygame.display.set_mode(screen_size)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 18)

        self.level_loader = LevelLoader(Path(__file__).resolve().parents[1] / "levels")
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

        self._needs_update = False

        self.load_level(self.level_names[self.level_index])

    # ------------------------------------------------------------------
    # Level handling
    # ------------------------------------------------------------------
    def load_level(self, name: str) -> None:
        """Load a level and prepare the runtime artefacts."""

        self.level = self.level_loader.load(name)
        self.game = LaserGame(self.level)
        self._needs_update = True
        self.update_playthrough(force=True)

    def cycle_level(self, direction: int) -> None:
        """Advance the level index and load the new level."""

        self.level_index = (self.level_index + direction) % len(self.level_names)
        self.load_level(self.level_names[self.level_index])

    def update_playthrough(self, force: bool = False) -> None:
        if not self.game:
            return
        if not force and not self._needs_update:
            return
        self.playthrough = self.game.playthrough()
        metadata = self.playthrough.get("metadata", {})
        title = "Laser Game"
        if metadata:
            title = f"Laser Game - {metadata.get('name', 'Unknown')} ({metadata.get('difficulty', '???')})"
        pygame.display.set_caption(title)
        self.geometry = self._compute_geometry()
        self._needs_update = False

    def _compute_geometry(self) -> Optional[GridGeometry]:
        if not self.level:
            return None
        width, height = self.screen.get_size()
        padding = 80
        available_w = max(width - padding * 2, 100)
        available_h = max(height - padding * 2, 100)
        cell_size = int(
            min(available_w / max(self.level.width, 1), available_h / max(self.level.height, 1))
        )
        cell_size = max(cell_size, 20)
        total_w = cell_size * self.level.width
        total_h = cell_size * self.level.height
        origin_x = (width - total_w) // 2
        origin_y = (height - total_h) // 2
        return GridGeometry(origin=(origin_x, origin_y), cell_size=cell_size)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def draw(self) -> None:
        if not self.level or not self.geometry:
            return

        self.screen.fill(self.background_color)

        self._draw_grid()
        self._draw_emitters()
        self._draw_targets()
        self._draw_mirrors()
        self._draw_beam_path()
        self._draw_metadata()

        pygame.display.flip()

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
        for emitter in self.level.emitters:
            center = self.geometry.cell_to_center(emitter.position)
            pygame.draw.circle(self.screen, self.emitter_color, center, self.geometry.cell_size // 3)

    def _draw_targets(self) -> None:
        assert self.level and self.geometry
        for position, target in self.level.targets.items():
            rect = pygame.Rect(
                *self.geometry.cell_to_topleft(position),
                self.geometry.cell_size,
                self.geometry.cell_size,
            )
            pygame.draw.rect(self.screen, self.target_color, rect, 2)

    def _draw_mirrors(self) -> None:
        assert self.level and self.geometry
        for position, mirror in self.level.mirrors.items():
            start = self.geometry.cell_to_topleft(position)
            end = (
                start[0] + self.geometry.cell_size,
                start[1] + self.geometry.cell_size,
            )
            if mirror.orientation == "/":
                pygame.draw.line(self.screen, self.mirror_color, (start[0], end[1]), (end[0], start[1]), 3)
            else:
                pygame.draw.line(self.screen, self.mirror_color, start, end, 3)

    def _draw_beam_path(self) -> None:
        if not self.geometry:
            return
        segments = self.playthrough.get("path", []) if self.playthrough else []
        for raw_segment in segments:
            segment = self._coerce_segment(raw_segment)
            if not segment:
                continue
            start = self.geometry.cell_to_center(segment.start)
            end = self.geometry.cell_to_center(segment.end)
            pygame.draw.line(self.screen, self.beam_color, start, end, 4)

    def _draw_metadata(self) -> None:
        metadata: Dict[str, str] = self.playthrough.get("metadata", {}) if self.playthrough else {}
        y = 20
        for key, value in metadata.items():
            surface = self.font.render(f"{key.title()}: {value}", True, (220, 220, 220))
            self.screen.blit(surface, (20, y))
            y += surface.get_height() + 4

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            raise SystemExit
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RIGHT, pygame.K_n):
                self.cycle_level(1)
            elif event.key in (pygame.K_LEFT, pygame.K_p):
                self.cycle_level(-1)
        if event.type == pygame.MOUSEBUTTONDOWN and self.level:
            grid_position = self._position_from_mouse(event.pos)
            if grid_position is not None:
                if event.button == 1:
                    self._place_or_toggle_mirror(grid_position)
                elif event.button == 3:
                    self._remove_mirror(grid_position)

    def _position_from_mouse(self, position: Tuple[int, int]) -> Optional[Tuple[int, int]]:
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
        mirror = self.level.mirrors.get(cell)
        if mirror:
            mirror.orientation = "/" if mirror.orientation == "\\" else "\\"
        else:
            self.level.mirrors[cell] = Mirror("/")
        self._needs_update = True

    def _remove_mirror(self, cell: Tuple[int, int]) -> None:
        assert self.level
        if cell in self.level.mirrors:
            del self.level.mirrors[cell]
            self._needs_update = True

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def run(self) -> None:
        while True:
            for event in pygame.event.get():
                try:
                    self.handle_event(event)
                except SystemExit:
                    pygame.quit()
                    return
            self.update_playthrough()
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
            return BeamSegment(start=start, end=end, direction=direction)
        return None


def run() -> None:
    """Entry point helper that instantiates and runs the UI."""

    app = LaserGameApp()
    app.run()


if __name__ == "__main__":
    run()
"""Entry point helpers for the optional Laser Game UI."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

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
    main()
