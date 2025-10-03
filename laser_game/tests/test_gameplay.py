import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from laser_game.game import (
    Direction,
    LaserEmitter,
    LaserGame,
    Level,
    LevelLoader,
    Mirror,
    SolutionValidator,
    Target,
)


def fixture_path(*parts: str) -> Path:
    return Path(__file__).resolve().parents[1].joinpath(*parts)


def test_mirror_reflection_turns_beam():
    level = Level(name="Reflection", difficulty="Easy", width=5, height=5)
    level.emitters.append(LaserEmitter(position=(0, 2), direction=Direction.EAST, energy=8))
    level.mirrors[(2, 2)] = Mirror("/")
    level.targets[(2, 0)] = Target(required_energy=1)

    game = LaserGame(level)
    game.propagate()

    assert game.target_energy[(2, 0)] == 1
    assert game.required_targets_met()


def test_level_intro_solution_completes():
    level_root = fixture_path("levels")
    loader = LevelLoader(level_root)
    level = loader.load("level_intro")

    solution_path = fixture_path("solutions", "level_intro.json")
    solution_data = json.loads(solution_path.read_text())

    validator = SolutionValidator(loader, fixture_path("solutions"))
    level = validator.apply_solution(level, solution_data)

    game = LaserGame(level)
    game.propagate()

    assert game.level_complete()
    assert game.target_energy[(4, 1)] == 1


@pytest.mark.parametrize(
    "level_name",
    [
        "level_prismatics",
        "level_dual_reflectors",
        "level_prism_conflux",
        "level_resonant_loop",
    ],
)
def test_solution_validator_detects_expected_targets(level_name: str):
    loader = LevelLoader(fixture_path("levels"))
    validator = SolutionValidator(loader, fixture_path("solutions"))

    assert validator.validate(level_name)


@pytest.mark.parametrize(
    "level_name",
    [
        "level_dual_reflectors",
        "level_prism_conflux",
        "level_resonant_loop",
    ],
)
def test_new_levels_complete_with_solutions(level_name: str):
    loader = LevelLoader(fixture_path("levels"))
    validator = SolutionValidator(loader, fixture_path("solutions"))

    level = loader.load(level_name)
    solution_data = validator.load_solution(level_name)
    level = validator.apply_solution(level, solution_data)

    game = LaserGame(level)
    game.propagate()

    assert game.level_complete()

    for key, expected in solution_data.get("expected_targets", {}).items():
        position = tuple(int(v) for v in key.strip("() ").split(","))
        assert game.target_energy.get(position) == expected
