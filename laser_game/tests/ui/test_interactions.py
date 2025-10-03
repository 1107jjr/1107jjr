"""Headless interaction tests for the pygame based UI wrapper.

To keep rendering deterministic the tests rely on the fixtures in
``conftest.py`` which force the SDL dummy drivers and initialise pygame's
default font.  Scaling issues are avoided by using a fixed ``cell_size``.
"""

from __future__ import annotations

from typing import List

from laser_game.game import Direction, LaserEmitter, LaserGame, Level
from laser_game.ui import LaserGameUI


def make_game() -> LaserGame:
    level = Level(name="UI Test", difficulty="N/A", width=4, height=3)
    level.emitters.append(
        LaserEmitter(position=(0, 1), direction=Direction.EAST, energy=6)
    )
    return LaserGame(level)


def placements_without_order(placements: List[dict]) -> List[dict]:
    return [dict(item) for item in placements]


def test_mirror_click_generates_pending(pygame_module):
    pygame = pygame_module
    game = make_game()
    ui = LaserGameUI(
        game,
        cell_size=32,
        surface=pygame.Surface((game.level.width * 32, game.level.height * 32)),
    )
    ui.select_tool("mirror", orientation="\\")

    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(48, 32))
    ui.process_events([event])

    assert placements_without_order(ui.pending_placements) == [
        {"type": "mirror", "position": (1, 1), "orientation": "\\"}
    ]

    ui.flush_pending_to_game()
    assert placements_without_order(game.pending_placements) == [
        {"type": "mirror", "position": (1, 1), "orientation": "\\"}
    ]

    game.apply_pending_placements()
    assert (1, 1) in game.level.mirrors
    assert game.level.mirrors[(1, 1)].orientation == "\\"


def test_prism_click_queued_and_applied(pygame_module):
    pygame = pygame_module
    game = make_game()
    ui = LaserGameUI(
        game,
        cell_size=32,
        surface=pygame.Surface((game.level.width * 32, game.level.height * 32)),
    )
    ui.select_tool("prism", spread=2)

    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(96, 32))
    ui.process_events([event])

    ui.flush_pending_to_game()
    assert placements_without_order(game.pending_placements) == [
        {"type": "prism", "position": (3, 1), "spread": 2}
    ]

    game.apply_pending_placements()
    assert (3, 1) in game.level.prisms
    assert game.level.prisms[(3, 1)].spread == 2

