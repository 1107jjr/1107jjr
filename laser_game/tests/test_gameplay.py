import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from laser_game.game import (
    Direction,
    EnergyField,
    Bomb,
    LaserEmitter,
    LaserGame,
    Level,
    LevelLoader,
    Mirror,
    Obstacle,
    Amplifier,
    Splitter,
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
    expected_targets = {
        tuple(int(v) for v in key.strip("() ").split(",")): value
        for key, value in solution_data.get("expected_targets", {}).items()
    }
    for position, expected in expected_targets.items():
        assert game.target_energy.get(position, 0) >= expected


@pytest.mark.parametrize(
    "level_name",
    [
        "level_prismatics",
        "level_dual_reflectors",
        "level_resonant_loop",
        "level_solar_crucible",
        "level_endless_resonator",
        "level_cataclysm_chain",
    ],
)
def test_solution_validator_detects_expected_targets(level_name: str):
    loader = LevelLoader(fixture_path("levels"))
    validator = SolutionValidator(loader, fixture_path("solutions"))

    assert validator.validate(level_name)


@pytest.mark.parametrize(
    "level_name",
    [
        "level_prismatics",
        "level_dual_reflectors",
        "level_resonant_loop",
        "level_solar_crucible",
        "level_endless_resonator",
        "level_cataclysm_chain",
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
        assert game.target_energy.get(position, 0) >= expected


def test_bomb_explosion_clears_obstacles_and_records_event():
    level = Level(name="Bomb Test", difficulty="Medium", width=6, height=5)
    level.emitters.append(
        LaserEmitter(position=(0, 2), direction=Direction.EAST, energy=6, brightness=1.0)
    )
    level.bombs[(1, 2)] = Bomb(power=1)
    level.obstacles[(2, 2)] = Obstacle(durability=1, destructible=True)
    level.targets[(3, 2)] = Target(required_energy=1)

    game = LaserGame(level)
    game.propagate()

    assert game.level_complete()
    assert game.last_events["explosions"]
    explosion = game.last_events["explosions"][0]
    assert tuple(explosion["position"]) == (1, 2)
    assert (2, 2) in explosion["cleared"]


def test_beam_segment_intensity_scales_with_energy():
    level = Level(name="Intensity", difficulty="Medium", width=6, height=5)
    level.emitters.append(
        LaserEmitter(position=(0, 2), direction=Direction.EAST, energy=6, brightness=1.2)
    )
    level.energy_fields[(3, 2)] = EnergyField(drain=2, color="violet")
    level.targets[(4, 2)] = Target(required_energy=1)

    game = LaserGame(level)
    game.propagate()

    assert any(segment.intensity < 1.0 for segment in game.path)


def test_amplifier_boosts_energy_and_brightness():
    level = Level(name="Amplify", difficulty="Hard", width=6, height=3)
    level.emitters.append(
        LaserEmitter(position=(0, 1), direction=Direction.EAST, energy=4, brightness=1.0)
    )
    level.amplifiers[(2, 1)] = Amplifier(multiplier=2.0, additive=1)
    level.targets[(5, 1)] = Target(required_energy=1)

    game = LaserGame(level)
    game.propagate()

    assert any(segment.intensity > 1.0 for segment in game.path)
    assert game.target_energy[(5, 1)] >= 1


def test_splitter_generates_additional_paths():
    level = Level(name="Split", difficulty="Hard", width=6, height=5)
    level.emitters.append(LaserEmitter(position=(0, 2), direction=Direction.EAST, energy=12))
    level.splitters[(2, 2)] = Splitter(pattern="triple")
    level.targets[(5, 1)] = Target(required_energy=1)
    level.targets[(5, 2)] = Target(required_energy=1)
    level.targets[(5, 3)] = Target(required_energy=1)

    game = LaserGame(level)
    game.propagate()

    assert len(game.path) > 0
    assert game.target_energy[(5, 2)] >= 1


def test_playthrough_includes_events_metadata():
    loader = LevelLoader(fixture_path("levels"))
    level = loader.load("level_cataclysm_chain")
    validator = SolutionValidator(loader, fixture_path("solutions"))
    solution = validator.load_solution("level_cataclysm_chain")
    level = validator.apply_solution(level, solution)

    game = LaserGame(level)
    summary = game.playthrough()

    assert "events" in summary
    assert "metadata" in summary
    assert summary.get("loop_detected") is True
    assert any(event.get("position") == [4, 5] for event in summary.get("events", {}).get("explosions", []))
