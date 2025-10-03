"""Core game logic for the laser puzzle experience."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


class Direction(Enum):
    """Cardinal directions for the laser beam."""

    NORTH = (0, -1)
    EAST = (1, 0)
    SOUTH = (0, 1)
    WEST = (-1, 0)

    @property
    def vector(self) -> Tuple[int, int]:
        return self.value

    @staticmethod
    def from_name(name: str) -> "Direction":
        name = name.upper()
        try:
            return Direction[name]
        except KeyError as exc:
            raise ValueError(f"Unknown direction: {name}") from exc

    def turn_left(self) -> "Direction":
        mapping = {
            Direction.NORTH: Direction.WEST,
            Direction.WEST: Direction.SOUTH,
            Direction.SOUTH: Direction.EAST,
            Direction.EAST: Direction.NORTH,
        }
        return mapping[self]

    def turn_right(self) -> "Direction":
        mapping = {
            Direction.NORTH: Direction.EAST,
            Direction.EAST: Direction.SOUTH,
            Direction.SOUTH: Direction.WEST,
            Direction.WEST: Direction.NORTH,
        }
        return mapping[self]

    def reverse(self) -> "Direction":
        mapping = {
            Direction.NORTH: Direction.SOUTH,
            Direction.SOUTH: Direction.NORTH,
            Direction.EAST: Direction.WEST,
            Direction.WEST: Direction.EAST,
        }
        return mapping[self]


@dataclass
class Mirror:
    """Reflects the laser depending on its orientation."""

    orientation: str  # '/' or '\\'

    def reflect(self, direction: Direction) -> Optional[Direction]:
        if self.orientation == "/":
            mapping = {
                Direction.NORTH: Direction.EAST,
                Direction.SOUTH: Direction.WEST,
                Direction.EAST: Direction.NORTH,
                Direction.WEST: Direction.SOUTH,
            }
        elif self.orientation == "\\":
            mapping = {
                Direction.NORTH: Direction.WEST,
                Direction.SOUTH: Direction.EAST,
                Direction.EAST: Direction.SOUTH,
                Direction.WEST: Direction.NORTH,
            }
        else:
            raise ValueError(f"Unknown mirror orientation: {self.orientation}")
        return mapping.get(direction)


@dataclass
class Prism:
    """Splits an incoming beam into multiple outputs."""

    spread: int = 1

    def split(self, direction: Direction) -> Sequence[Direction]:
        # The primary beam continues forward, optional spread spawns left/right beams.
        outputs = [direction]
        if self.spread >= 1:
            outputs.append(direction.turn_left())
            outputs.append(direction.turn_right())
        return outputs


@dataclass
class EnergyField:
    """Consumes energy units from the beam that passes through."""

    drain: int
    color: str = "white"


@dataclass
class Target:
    """Target that must receive sufficient energy to clear the level."""

    required_energy: int = 1
    label: str = ""


@dataclass
class LaserEmitter:
    position: Tuple[int, int]
    direction: Direction
    energy: int = 10


@dataclass
class Level:
    """In-memory representation of a level definition."""

    name: str
    difficulty: str
    width: int
    height: int
    emitters: List[LaserEmitter] = field(default_factory=list)
    mirrors: Dict[Tuple[int, int], Mirror] = field(default_factory=dict)
    prisms: Dict[Tuple[int, int], Prism] = field(default_factory=dict)
    energy_fields: Dict[Tuple[int, int], EnergyField] = field(default_factory=dict)
    targets: Dict[Tuple[int, int], Target] = field(default_factory=dict)

    @property
    def metadata(self) -> Dict[str, str]:
        return {
            "name": self.name,
            "difficulty": self.difficulty,
            "dimensions": f"{self.width}x{self.height}",
        }

    def inside(self, position: Tuple[int, int]) -> bool:
        x, y = position
        return 0 <= x < self.width and 0 <= y < self.height


@dataclass
class BeamSegment:
    start: Tuple[int, int]
    end: Tuple[int, int]
    direction: Direction


class LevelLoader:
    """Load level files stored as JSON."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def load(self, name: str) -> Level:
        path = self.root / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(path)
        data = json.loads(path.read_text())
        return self._parse_level(data)

    def _parse_level(self, data: Dict) -> Level:
        level = Level(
            name=data["name"],
            difficulty=data.get("difficulty", "Unknown"),
            width=data["width"],
            height=data["height"],
        )
        for emitter in data.get("emitters", []):
            level.emitters.append(
                LaserEmitter(
                    position=tuple(emitter["position"]),
                    direction=Direction.from_name(emitter["direction"]),
                    energy=emitter.get("energy", 10),
                )
            )
        for mirror in data.get("mirrors", []):
            position = tuple(mirror["position"])
            level.mirrors[position] = Mirror(mirror.get("orientation", "/"))
        for prism in data.get("prisms", []):
            position = tuple(prism["position"])
            level.prisms[position] = Prism(spread=prism.get("spread", 1))
        for field in data.get("energy_fields", []):
            position = tuple(field["position"])
            level.energy_fields[position] = EnergyField(
                drain=field.get("drain", 1),
                color=field.get("color", "white"),
            )
        for target in data.get("targets", []):
            position = tuple(target["position"])
            level.targets[position] = Target(
                required_energy=target.get("required_energy", 1),
                label=target.get("label", ""),
            )
        return level


class LaserGame:
    """High level game manager handling laser propagation and win conditions."""

    def __init__(self, level: Level):
        self.level = level
        self.reset()

    def reset(self) -> None:
        self.target_energy: Dict[Tuple[int, int], int] = {
            position: 0 for position in self.level.targets
        }
        self.path: List[BeamSegment] = []

    def propagate(self) -> None:
        self.reset()
        visited: Dict[Tuple[Tuple[int, int], Direction], int] = {}
        queue: List[Tuple[Tuple[int, int], Direction, int]] = []
        for emitter in self.level.emitters:
            queue.append((emitter.position, emitter.direction, emitter.energy))

        while queue:
            position, direction, energy = queue.pop(0)
            state_key = (position, direction)
            if visited.get(state_key, -1) >= energy:
                continue
            visited[state_key] = energy

            current = position
            current_direction = direction
            current_energy = energy

            while current_energy > 0:
                next_pos = (
                    current[0] + current_direction.vector[0],
                    current[1] + current_direction.vector[1],
                )
                if not self.level.inside(next_pos):
                    break

                # Base cost for moving into the next cell.
                current_energy -= 1
                if current_energy < 0:
                    break

                self.path.append(
                    BeamSegment(start=current, end=next_pos, direction=current_direction)
                )

                field = self.level.energy_fields.get(next_pos)
                if field:
                    current_energy -= field.drain
                    if current_energy <= 0:
                        break

                target = self.level.targets.get(next_pos)
                if target:
                    self.target_energy[next_pos] += 1

                mirror = self.level.mirrors.get(next_pos)
                prism = self.level.prisms.get(next_pos)

                if mirror:
                    reflected = mirror.reflect(current_direction)
                    if reflected is None:
                        break
                    current = next_pos
                    current_direction = reflected
                    continue

                if prism and current_energy > 0:
                    outputs = list(prism.split(current_direction))
                    # Continue with the first output and enqueue the others.
                    primary = outputs[0]
                    for extra_direction in outputs[1:]:
                        queue.append((next_pos, extra_direction, current_energy))
                    current = next_pos
                    current_direction = primary
                    continue

                current = next_pos

    def level_complete(self) -> bool:
        return all(
            self.target_energy.get(position, 0) >= target.required_energy
            for position, target in self.level.targets.items()
        )

    def required_targets_met(self) -> bool:
        for position, target in self.level.targets.items():
            if self.target_energy.get(position, 0) < target.required_energy:
                return False
        return True

    def playthrough(self) -> Dict[str, object]:
        self.propagate()
        return {
            "path": [segment.__dict__ for segment in self.path],
            "targets": {
                str(position): energy for position, energy in self.target_energy.items()
            },
            "metadata": self.level.metadata,
        }


class SolutionValidator:
    """Validate that a solution file produces the expected completion state."""

    def __init__(self, level_loader: LevelLoader, solutions_root: Path):
        self.level_loader = level_loader
        self.solutions_root = Path(solutions_root)

    def load_solution(self, name: str) -> Dict:
        path = self.solutions_root / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(path)
        return json.loads(path.read_text())

    def apply_solution(self, level: Level, solution: Dict) -> Level:
        placements = solution.get("placements", [])
        for placement in placements:
            position = tuple(placement["position"])
            if placement["type"] == "mirror":
                level.mirrors[position] = Mirror(placement.get("orientation", "/"))
            elif placement["type"] == "prism":
                level.prisms[position] = Prism(spread=placement.get("spread", 1))
            elif placement["type"] == "energy_field":
                level.energy_fields[position] = EnergyField(drain=placement.get("drain", 1))
            else:
                raise ValueError(f"Unknown placement type: {placement['type']}")
        return level

    def validate(self, level_name: str, solution_name: Optional[str] = None) -> bool:
        level = self.level_loader.load(level_name)
        solution_data = self.load_solution(solution_name or level_name)
        level = self.apply_solution(level, solution_data)
        game = LaserGame(level)
        game.propagate()
        expected_targets = solution_data.get("expected_targets", {})
        for key, expected in expected_targets.items():
            position = tuple(int(v) for v in key.strip("() ").split(","))
            if game.target_energy.get(position, 0) != expected:
                return False
        return game.required_targets_met()
