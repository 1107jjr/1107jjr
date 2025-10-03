"""Snapshot style tests for the deterministic pygame rendering.

Rendering artefacts are compared via an MD5 checksum over the surface buffer
to avoid storing large binary fixtures.  The baseline snapshots were generated
using pygame's default font and a fixed ``cell_size`` to ensure deterministic
output across CI and developer machines.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from laser_game.game import LaserGame, Level, Mirror, Prism
from laser_game.ui import LaserGameUI


SNAPSHOT_DIR = Path(__file__).resolve().parent / "snapshots"


def test_initial_board_snapshot(pygame_module):
    pygame = pygame_module
    level = Level(name="Snapshot", difficulty="N/A", width=3, height=2)
    level.mirrors[(0, 0)] = Mirror("/")
    level.prisms[(2, 1)] = Prism(spread=2)
    game = LaserGame(level)

    surface = pygame.Surface((game.level.width * 24, game.level.height * 24))
    ui = LaserGameUI(game, cell_size=24, surface=surface)
    rendered = ui.render()

    digest = hashlib.md5(pygame.image.tostring(rendered, "RGB")).hexdigest()
    expected = (SNAPSHOT_DIR / "initial_board.md5").read_text().strip()
    assert digest == expected

