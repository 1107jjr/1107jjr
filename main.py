"""Interactive viewer for the laser game prototype."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Tuple

import pygame

from laser_game.game import LaserGame, LevelLoader
from laser_game.ui import assets as ui_assets
from laser_game.ui import layout


def draw_board(
    surface: pygame.Surface,
    game: LaserGame,
    board_rect: pygame.Rect,
    tile_surface: pygame.Surface,
    mirror_surface: pygame.Surface,
    goal_surface: pygame.Surface,
    small_font: pygame.font.Font,
) -> None:
    """Render the play field grid and placed objects."""

    pygame.draw.rect(surface, layout.BOARD_BACKGROUND_COLOR, board_rect)

    tile_width = tile_surface.get_width()
    origin_x, origin_y = board_rect.topleft

    for grid_y in range(game.level.height):
        for grid_x in range(game.level.width):
            dest = (origin_x + grid_x * tile_width, origin_y + grid_y * tile_width)
            surface.blit(tile_surface, dest)

    for x in range(game.level.width + 1):
        start = (origin_x + x * layout.TILE_SIZE, origin_y)
        end = (start[0], origin_y + board_rect.height)
        pygame.draw.line(surface, layout.GRID_LINE_COLOR, start, end, 1)
    for y in range(game.level.height + 1):
        start = (origin_x, origin_y + y * layout.TILE_SIZE)
        end = (origin_x + board_rect.width, start[1])
        pygame.draw.line(surface, layout.GRID_LINE_COLOR, start, end, 1)

    for position, _mirror in game.level.mirrors.items():
        dest = (origin_x + position[0] * layout.TILE_SIZE, origin_y + position[1] * layout.TILE_SIZE)
        surface.blit(mirror_surface, dest)

    for position, target in game.level.targets.items():
        dest = (origin_x + position[0] * layout.TILE_SIZE, origin_y + position[1] * layout.TILE_SIZE)
        surface.blit(goal_surface, dest)
        label = target.label or f"{position[0]}, {position[1]}"
        text_surface = small_font.render(label, True, layout.TEXT_COLOR)
        text_rect = text_surface.get_rect()
        text_rect.midbottom = (
            dest[0] + goal_surface.get_width() // 2,
            dest[1] + goal_surface.get_height() - 6,
        )
        surface.blit(text_surface, text_rect)

    for segment in game.path:
        start = (
            origin_x + segment.start[0] * layout.TILE_SIZE + layout.TILE_SIZE // 2,
            origin_y + segment.start[1] * layout.TILE_SIZE + layout.TILE_SIZE // 2,
        )
        end = (
            origin_x + segment.end[0] * layout.TILE_SIZE + layout.TILE_SIZE // 2,
            origin_y + segment.end[1] * layout.TILE_SIZE + layout.TILE_SIZE // 2,
        )
        pygame.draw.line(surface, layout.ACCENT_COLOR, start, end, 3)


def draw_available_objects(
    surface: pygame.Surface,
    panel_rect: pygame.Rect,
    items: Iterable[Tuple[str, pygame.Surface]],
    font: pygame.font.Font,
) -> int:
    """Render the set of placeable objects inside the UI panel."""

    x, y, _, _ = panel_rect
    current_y = y + layout.UI_PANEL_PADDING
    icon_x = x + layout.UI_PANEL_PADDING

    header = font.render("Werkzeuge", True, layout.TEXT_COLOR)
    surface.blit(header, (icon_x, current_y))
    current_y += layout.UI_PANEL_HEADER_HEIGHT

    for label, icon in items:
        icon_rect = icon.get_rect()
        icon_rect.topleft = (icon_x, current_y)
        surface.blit(icon, icon_rect)

        text_surface = font.render(label, True, layout.TEXT_COLOR)
        text_rect = text_surface.get_rect()
        text_rect.midleft = (icon_rect.right + 18, icon_rect.centery)
        surface.blit(text_surface, text_rect)

        current_y = icon_rect.bottom + layout.UI_PANEL_SPACING

    return current_y


def draw_status(
    surface: pygame.Surface,
    game: LaserGame,
    panel_rect: pygame.Rect,
    start_y: int,
    font: pygame.font.Font,
    small_font: pygame.font.Font,
) -> None:
    """Render target energy status in the UI panel."""

    x = panel_rect.x + layout.UI_PANEL_PADDING
    heading = font.render("Zielenergie", True, layout.TEXT_COLOR)
    surface.blit(heading, (x, start_y))
    start_y += font.get_linesize() + 8

    for position, target in sorted(game.level.targets.items()):
        delivered = game.target_energy.get(position, 0)
        label = target.label or f"Ziel {position[0]}, {position[1]}"
        status = f"{delivered}/{target.required_energy} Einheiten"
        line_surface = small_font.render(label, True, layout.TEXT_COLOR)
        surface.blit(line_surface, (x, start_y))
        start_y += line_surface.get_height() + 2
        status_surface = small_font.render(status, True, layout.ACCENT_COLOR)
        surface.blit(status_surface, (x + 12, start_y))
        start_y += status_surface.get_height() + layout.UI_PANEL_SPACING


def draw_tooltip(surface: pygame.Surface, tooltip_rect: pygame.Rect, text: str, font: pygame.font.Font) -> None:
    pygame.draw.rect(surface, layout.TOOLTIP_BACKGROUND_COLOR, tooltip_rect, border_radius=12)
    pygame.draw.rect(surface, layout.GRID_LINE_COLOR, tooltip_rect, 2, border_radius=12)
    text_surface = font.render(text, True, layout.TEXT_COLOR)
    text_rect = text_surface.get_rect()
    text_rect.center = tooltip_rect.center
    surface.blit(text_surface, text_rect)


def draw_scene(
    surface: pygame.Surface,
    game: LaserGame,
    assets: ui_assets.AssetLibrary,
    geometry: layout.BoardGeometry,
    *,
    font: pygame.font.Font,
    small_font: pygame.font.Font,
    available_items: Iterable[Tuple[str, pygame.Surface]],
    tooltip_text: str,
) -> None:
    """Draw a full frame including the board, UI panel and tooltip."""

    surface.fill(layout.BACKGROUND_COLOR)

    board_rect = pygame.Rect(*geometry.board)
    panel_rect = pygame.Rect(*geometry.panel)
    tooltip_rect = pygame.Rect(*geometry.tooltip)

    pygame.draw.rect(surface, layout.PANEL_BACKGROUND_COLOR, panel_rect, border_radius=18)

    for layer in layout.DRAW_ORDER:
        if layer == "board":
            draw_board(
                surface,
                game,
                board_rect,
                assets["board_tile"],
                assets["mirror"],
                assets["goal"],
                small_font,
            )
        elif layer == "ui_panel":
            next_y = draw_available_objects(surface, panel_rect, available_items, font)
            draw_status(surface, game, panel_rect, next_y, font, small_font)
        elif layer == "tooltips":
            draw_tooltip(surface, tooltip_rect, tooltip_text, font)


def main() -> None:
    pygame.init()
    pygame.font.init()

    package_root = Path(__file__).resolve().parent / "laser_game"

    level_loader = LevelLoader(package_root / "levels")
    level = level_loader.load("level_intro")

    game = LaserGame(level)
    game.propagate()

    assets = ui_assets.load_svg_assets()
    geometry = layout.compute_geometry(level.width, level.height)

    screen = pygame.display.set_mode(geometry.window)
    pygame.display.set_caption("Laser Game Prototype")

    font = pygame.font.Font(None, 28)
    small_font = pygame.font.Font(None, 22)

    available_items = (
        ("Spiegel", assets["mirror"]),
        ("Ziel", assets["goal"]),
        ("Aktion", assets["ui_button"]),
    )

    tooltip_text = "Linksklick auf das Raster, um ein Objekt zu platzieren."

    clock = pygame.time.Clock()
    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        draw_scene(
            screen,
            game,
            assets,
            geometry,
            font=font,
            small_font=small_font,
            available_items=available_items,
            tooltip_text=tooltip_text,
        )

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
