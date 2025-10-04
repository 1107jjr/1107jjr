"""Core game logic for the laser puzzle experience."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


MAX_ENERGY_LEVEL = 8
DEFAULT_ENERGY_LEVEL = 4


def clamp_energy(value: int, *, allow_zero: bool = True) -> int:
    minimum = 0 if allow_zero else 1
    try:
        level = int(value)
    except (TypeError, ValueError):
        level = minimum
    return max(minimum, min(MAX_ENERGY_LEVEL, level))


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
    energy: int = DEFAULT_ENERGY_LEVEL
    brightness: float = 1.0
    emission_interval: int = 0
    burst_length: int = 1
    burst_cooldown: int = 0


@dataclass
class Obstacle:
    """Blocks laser pulses until destroyed."""

    durability: int = 1
    destructible: bool = True


@dataclass
class Bomb:
    """Explosive device that removes nearby obstacles when triggered."""

    power: int = 1  # Manhattan radius affected


@dataclass
class Splitter:
    """Splits laser pulses into predefined direction patterns."""

    pattern: str = "dual"  # dual, triple, cross


@dataclass
class Amplifier:
    """Boosts the energy/brightness of the passing laser pulse."""

    multiplier: float = 2.0
    additive: int = 0
    cap: Optional[int] = None


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
    obstacles: Dict[Tuple[int, int], Obstacle] = field(default_factory=dict)
    bombs: Dict[Tuple[int, int], Bomb] = field(default_factory=dict)
    splitters: Dict[Tuple[int, int], Splitter] = field(default_factory=dict)
    amplifiers: Dict[Tuple[int, int], Amplifier] = field(default_factory=dict)
    tool_limits: Dict[str, int] = field(default_factory=dict)
    loop_required: bool = False
    min_loop_ticks: int = 0
    energy_goal: Optional[int] = None

    @property
    def metadata(self) -> Dict[str, object]:
        metadata: Dict[str, object] = {
            "name": self.name,
            "difficulty": self.difficulty,
            "dimensions": f"{self.width}x{self.height}",
        }
        if self.loop_required:
            metadata["loop_required"] = True
        if self.min_loop_ticks:
            metadata["min_loop_ticks"] = self.min_loop_ticks
        if self.energy_goal is not None:
            metadata["energy_goal"] = self.energy_goal
        return metadata

    def inside(self, position: Tuple[int, int]) -> bool:
        x, y = position
        return 0 <= x < self.width and 0 <= y < self.height


@dataclass
class PulseSegment:
    """Single directed segment of a pulse during one tick."""

    start: Tuple[int, int]
    end: Tuple[int, int]
    direction: Direction
    energy: int
    intensity: float
    tick: int
    lifetime: int = 1
    brightness: float = 1.0
    source_energy: int = 1


# Backwards compatibility alias for legacy naming.
BeamSegment = PulseSegment


@dataclass
class PulseFrame:
    """Timeline frame representing a single simulation tick."""

    tick: int
    segments: List[PulseSegment] = field(default_factory=list)
    events: Dict[str, List[Dict[str, object]]] = field(default_factory=dict)


@dataclass
class PulseHead:
    """Internal state for an advancing pulse head."""

    position: Tuple[int, int]
    direction: Direction
    energy: int
    brightness: float
    source_energy: int
    phase: int = 0
    emitter_index: Optional[int] = None
    lifetime: Optional[int] = None


@dataclass
class PulseState:
    """Mutable runtime state for the pulse simulation."""

    tick: int = 0
    active_heads: List[PulseHead] = field(default_factory=list)
    visited_states: Dict[Tuple[Tuple[int, int], Direction, int], int] = field(
        default_factory=dict
    )
    loop_detected: bool = False
    loop_tick: Optional[int] = None


@dataclass
class EmitterRuntime:
    """Scheduler that orchestrates emitter pulse emission."""

    emitter: LaserEmitter
    next_emission_tick: int = 0
    emission_ticks_remaining: int = 0
    current_pulse_start: Optional[int] = None
    has_fired: bool = False

    def _cycle_interval(self) -> int:
        base = max(1, self.emitter.burst_length + max(0, self.emitter.burst_cooldown))
        interval = self.emitter.emission_interval
        if interval is None or interval <= 0:
            return base
        return max(base, interval)

    def has_future_activity(self, tick: int) -> bool:
        if self.emission_ticks_remaining > 0:
            return True
        if self.emitter.emission_interval <= 0 and self.has_fired:
            return False
        return tick <= self.next_emission_tick

    def generate_heads(self, tick: int, index: int) -> List[PulseHead]:
        heads: List[PulseHead] = []
        if self.emission_ticks_remaining <= 0:
            if self.emitter.emission_interval <= 0 and self.has_fired:
                return heads
            if tick < self.next_emission_tick:
                return heads
            self.emission_ticks_remaining = max(1, self.emitter.burst_length)
            self.current_pulse_start = tick
        phase_origin = self.current_pulse_start if self.current_pulse_start is not None else tick
        phase = tick - phase_origin
        energy_level = clamp_energy(self.emitter.energy, allow_zero=False)
        head = PulseHead(
            position=self.emitter.position,
            direction=self.emitter.direction,
            energy=energy_level,
            brightness=float(max(self.emitter.brightness, 0.1)),
            source_energy=max(1, energy_level),
            phase=phase,
            emitter_index=index,
        )
        heads.append(head)
        self.has_fired = True
        self.emission_ticks_remaining -= 1
        if self.emission_ticks_remaining <= 0:
            interval = self._cycle_interval()
            self.next_emission_tick = phase_origin + interval
            self.current_pulse_start = None
        return heads


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
            loop_required=bool(data.get("loop_required", False)),
            min_loop_ticks=int(data.get("min_loop_ticks", 0) or 0),
            energy_goal=(
                int(data["energy_goal"])
                if data.get("energy_goal") is not None
                else None
            ),
        )
        for emitter in data.get("emitters", []):
            level.emitters.append(
                LaserEmitter(
                    position=tuple(emitter["position"]),
                    direction=Direction.from_name(emitter["direction"]),
                    energy=int(emitter.get("energy", 10)),
                    brightness=float(emitter.get("brightness", 1.0)),
                    emission_interval=int(emitter.get("emission_interval", 0) or 0),
                    burst_length=int(emitter.get("burst_length", 1) or 1),
                    burst_cooldown=int(emitter.get("burst_cooldown", 0) or 0),
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
        for obstacle in data.get("obstacles", []):
            position = tuple(obstacle["position"])
            level.obstacles[position] = Obstacle(
                durability=int(obstacle.get("durability", 1)),
                destructible=bool(obstacle.get("destructible", True)),
            )
        for bomb in data.get("bombs", []):
            position = tuple(bomb["position"])
            level.bombs[position] = Bomb(power=int(bomb.get("power", 1)))
        for splitter in data.get("splitters", []):
            position = tuple(splitter["position"])
            level.splitters[position] = Splitter(
                pattern=str(splitter.get("pattern", "dual")).lower()
            )
        for amplifier in data.get("amplifiers", []):
            position = tuple(amplifier["position"])
            level.amplifiers[position] = Amplifier(
                multiplier=float(amplifier.get("multiplier", 2.0)),
                additive=int(amplifier.get("additive", 0)),
                cap=int(amplifier["cap"]) if amplifier.get("cap") is not None else None,
            )
        level.tool_limits = {
            str(key): int(value)
            for key, value in data.get("tool_limits", {}).items()
        }
        return level


def apply_placement_to_level(level: Level, placement: Dict[str, object]) -> None:
    position = tuple(placement["position"])
    item_type = placement["type"]
    if item_type == "mirror":
        orientation = placement.get("orientation", "/")
        level.mirrors[position] = Mirror(str(orientation))
        level.prisms.pop(position, None)
    elif item_type == "prism":
        spread = int(placement.get("spread", 1))
        level.prisms[position] = Prism(spread=spread)
        level.mirrors.pop(position, None)
    elif item_type == "energy_field":
        drain = int(placement.get("drain", 1))
        color = placement.get("color", "white")
        level.energy_fields[position] = EnergyField(drain=drain, color=str(color))
    elif item_type == "bomb":
        power = int(placement.get("power", 1))
        level.bombs[position] = Bomb(power=power)
    elif item_type == "splitter":
        pattern = str(placement.get("pattern", "dual")).lower()
        level.splitters[position] = Splitter(pattern=pattern)
        level.mirrors.pop(position, None)
        level.prisms.pop(position, None)
        level.amplifiers.pop(position, None)
    elif item_type == "splitter_triple":
        level.splitters[position] = Splitter(pattern="triple")
        level.mirrors.pop(position, None)
        level.prisms.pop(position, None)
        level.amplifiers.pop(position, None)
    elif item_type == "splitter_cross":
        level.splitters[position] = Splitter(pattern="cross")
        level.mirrors.pop(position, None)
        level.prisms.pop(position, None)
        level.amplifiers.pop(position, None)
    elif item_type == "amplifier":
        multiplier = float(placement.get("multiplier", 2.0))
        additive = int(placement.get("additive", 0))
        cap_value = placement.get("cap")
        cap = int(cap_value) if cap_value is not None else None
        level.amplifiers[position] = Amplifier(
            multiplier=multiplier, additive=additive, cap=cap
        )
        level.mirrors.pop(position, None)
        level.splitters.pop(position, None)
        level.prisms.pop(position, None)
    else:
        raise ValueError(f"Unknown placement type: {item_type}")



class LaserGame:
    """High level game manager handling pulse propagation and win conditions."""

    def __init__(self, level: Level):
        self.level = level
        self.pending_placements: List[Dict[str, object]] = []
        self.reset()

    def queue_pending_placements(
        self, placements: Iterable[Dict[str, object]]
    ) -> None:
        for placement in placements:
            normalized = dict(placement)
            normalized["position"] = tuple(normalized["position"])
            self.pending_placements.append(normalized)

    def apply_pending_placements(self) -> None:
        while self.pending_placements:
            placement = self.pending_placements.pop(0)
            apply_placement_to_level(self.level, placement)

    def reset(self) -> None:
        self.target_energy: Dict[Tuple[int, int], int] = {
            position: 0 for position in self.level.targets
        }
        self.path: List[PulseSegment] = []
        self.timeline: List[PulseFrame] = []
        self.state = PulseState()
        self.accumulated_events: Dict[str, List[Dict[str, object]]] = defaultdict(list)
        self.explosion_events: List[Dict[str, object]] = []
        self.newly_hit_targets: List[Dict[str, object]] = []
        self.destroyed_obstacles: Set[Tuple[int, int]] = set()
        self.obstacle_removals: List[Dict[str, object]] = []
        self.last_events: Dict[str, List[Dict[str, object]]] = {
            "explosions": [],
            "hits": [],
        }
        self.loop_overflow = False
        self.active_obstacles: Dict[Tuple[int, int], Obstacle] = {
            pos: Obstacle(durability=ob.durability, destructible=ob.destructible)
            for pos, ob in self.level.obstacles.items()
        }
        self.active_bombs: Dict[Tuple[int, int], Bomb] = {
            pos: Bomb(power=bomb.power) for pos, bomb in self.level.bombs.items()
        }
        self.emitter_runtimes: List[EmitterRuntime] = [
            EmitterRuntime(emitter) for emitter in self.level.emitters
        ]

    def _default_max_ticks(self) -> int:
        return max(600, self.level.width * self.level.height * 24)

    def _has_pending_activity(self) -> bool:
        if self.state.active_heads:
            return True
        return any(runtime.has_future_activity(self.state.tick) for runtime in self.emitter_runtimes)

    @staticmethod
    def _split_energy(energy: int, outputs: int) -> int:
        if outputs <= 0:
            return clamp_energy(energy)
        if energy <= 0:
            return 0
        portion = int(energy) // outputs
        if portion <= 0:
            return 0
        return min(MAX_ENERGY_LEVEL, portion)


    def _loop_signature(self, head: PulseHead) -> Tuple[Tuple[int, int], Direction, int]:
        return head.position, head.direction, head.phase

    def _record_loop(
        self,
        head: PulseHead,
        events: Dict[str, List[Dict[str, object]]],
    ) -> None:
        signature = self._loop_signature(head)
        previous_energy = self.state.visited_states.get(signature)
        if previous_energy is not None and head.energy >= previous_energy:
            if not self.state.loop_detected:
                self.state.loop_detected = True
                self.state.loop_tick = self.state.tick
            loop_event = {
                "position": head.position,
                "direction": head.direction.name,
                "energy": head.energy,
                "phase": head.phase,
                "tick": self.state.tick,
            }
            events["loop_detected"].append(loop_event)
        self.state.visited_states[signature] = max(previous_energy or 0, clamp_energy(head.energy))

    def step(self) -> PulseFrame:
        frame = PulseFrame(tick=self.state.tick)
        events: Dict[str, List[Dict[str, object]]] = defaultdict(list)
        segments: List[PulseSegment] = []
        new_heads: List[PulseHead] = []

        spawned_heads: List[PulseHead] = []
        for index, runtime in enumerate(self.emitter_runtimes):
            for head in runtime.generate_heads(self.state.tick, index):
                spawned_heads.append(head)
                events["emission"].append(
                    {
                        "emitter": index,
                        "tick": self.state.tick,
                        "phase": head.phase,
                        "energy": head.energy,
                        "direction": head.direction.name,
                    }
                )

        active_heads = list(self.state.active_heads)
        active_heads.extend(spawned_heads)

        for head in active_heads:
            if head.energy <= 0:
                continue

            current_pos = head.position
            direction = head.direction
            next_pos = (
                current_pos[0] + direction.vector[0],
                current_pos[1] + direction.vector[1],
            )

            if not self.level.inside(next_pos):
                continue

            energy_level = clamp_energy(head.energy)

            intensity_ratio = energy_level / max(head.source_energy, 1)
            segment_intensity = max(0.2, min(1.8, head.brightness * intensity_ratio))
            segment = PulseSegment(
                start=current_pos,
                end=next_pos,
                direction=direction,
                energy=energy_level,
                intensity=float(segment_intensity),
                tick=self.state.tick,
                lifetime=head.lifetime or 1,
                brightness=head.brightness,
                source_energy=head.source_energy,
            )
            segments.append(segment)
            self.path.append(segment)

            field = self.level.energy_fields.get(next_pos)
            if field:
                head.energy = max(0, head.energy - field.drain)
                events["energy_drop"].append(
                    {
                        "position": next_pos,
                        "drain": field.drain,
                        "remaining": max(head.energy, 0),
                        "tick": self.state.tick,
                    }
                )
                if head.energy <= 0:
                    continue

            target = self.level.targets.get(next_pos)
            if target:
                delivered_energy = clamp_energy(head.energy)
                previous_energy = self.target_energy.get(next_pos, 0)
                if delivered_energy > previous_energy:
                    self.target_energy[next_pos] = delivered_energy
                hit_event = {
                    "position": next_pos,
                    "label": target.label,
                    "delivered": self.target_energy[next_pos],
                    "required": target.required_energy,
                    "energy": delivered_energy,
                    "previous": previous_energy,
                    "tick": self.state.tick,
                }
                events["hits"].append(hit_event)
                if previous_energy < target.required_energy <= self.target_energy[next_pos]:
                    self.newly_hit_targets.append(hit_event)

            bomb = self.active_bombs.get(next_pos)
            if bomb:
                bomb_event, cleared_events = self._trigger_bomb(
                    next_pos, bomb, self.active_obstacles, tick=self.state.tick
                )
                self.active_bombs.pop(next_pos, None)
                events["explosions"].append(bomb_event)
                if cleared_events:
                    events["obstacles_removed"].extend(cleared_events)

            obstacle = self.active_obstacles.get(next_pos)
            if obstacle:
                if obstacle.destructible:
                    obstacle.durability -= 1
                    hit_info = {
                        "position": next_pos,
                        "durability": obstacle.durability,
                        "tick": self.state.tick,
                    }
                    events["obstacles_hit"].append(hit_info)
                    if obstacle.durability <= 0:
                        self.active_obstacles.pop(next_pos, None)
                        if next_pos not in self.destroyed_obstacles:
                            self.destroyed_obstacles.add(next_pos)
                            removal_event = {
                                "position": next_pos,
                                "cause": "laser",
                                "tick": self.state.tick,
                            }
                            self.obstacle_removals.append(removal_event)
                            events["obstacles_removed"].append(removal_event)
                continue

            amplifier = self.level.amplifiers.get(next_pos)
            if amplifier and head.energy > 0:
                boosted = int(round(head.energy * amplifier.multiplier)) + amplifier.additive
                if amplifier.cap is not None:
                    boosted = min(boosted, amplifier.cap)
                head.energy = clamp_energy(boosted)
                head.brightness = max(0.1, head.brightness * max(amplifier.multiplier, 0.1))
                head.source_energy = max(head.source_energy, head.energy)
                amp_event = {
                    "position": next_pos,
                    "multiplier": amplifier.multiplier,
                    "additive": amplifier.additive,
                    "result": head.energy,
                    "tick": self.state.tick,
                }
                events["amplified"].append(amp_event)

            mirror = self.level.mirrors.get(next_pos)
            if mirror:
                reflected = mirror.reflect(direction)
                if reflected is None:
                    continue
                direction = reflected
                head.brightness = max(0.1, head.brightness * 0.92)

            prism = self.level.prisms.get(next_pos)
            if prism and head.energy > 0:
                outputs = list(prism.split(direction))
                if outputs:
                    branch_energy = self._split_energy(head.energy, len(outputs))
                    if branch_energy <= 0:
                        continue
                    branch_brightness = max(0.1, head.brightness * 0.85)
                    split_event = {
                        "type": "prism",
                        "position": next_pos,
                        "outputs": [out.name for out in outputs],
                        "tick": self.state.tick,
                    }
                    events["split"].append(split_event)
                    for out_dir in outputs:
                        new_heads.append(
                            PulseHead(
                                position=next_pos,
                                direction=out_dir,
                                energy=branch_energy,
                                brightness=branch_brightness,
                                source_energy=max(head.source_energy, branch_energy),
                                phase=head.phase,
                                emitter_index=head.emitter_index,
                            )
                        )
                    head.energy = 0
                    continue

            splitter = self.level.splitters.get(next_pos)
            if splitter and head.energy > 0:
                outputs = self._splitter_outputs(splitter.pattern, direction)
                if outputs:
                    branch_energy = self._split_energy(head.energy, len(outputs))
                    if branch_energy <= 0:
                        continue
                    branch_brightness = max(0.1, head.brightness * 0.88)
                    split_event = {
                        "type": "splitter",
                        "pattern": splitter.pattern,
                        "position": next_pos,
                        "outputs": [out.name for out in outputs],
                        "tick": self.state.tick,
                    }
                    events["split"].append(split_event)
                    for out_dir in outputs:
                        new_heads.append(
                            PulseHead(
                                position=next_pos,
                                direction=out_dir,
                                energy=branch_energy,
                                brightness=branch_brightness,
                                source_energy=max(head.source_energy, branch_energy),
                                phase=head.phase,
                                emitter_index=head.emitter_index,
                            )
                        )
                    head.energy = 0
                    continue

            if head.energy <= 0:
                continue

            updated_head = PulseHead(
                position=next_pos,
                direction=direction,
                energy=head.energy,
                brightness=head.brightness,
                source_energy=max(head.source_energy, head.energy),
                phase=head.phase,
                emitter_index=head.emitter_index,
            )
            self._record_loop(updated_head, events)
            new_heads.append(updated_head)

        if segments:
            tick_event = {
                "tick": self.state.tick,
                "segment_count": len(segments),
            }
            events["pulse_tick"].append(tick_event)

        frame.segments = segments
        frame.events = {key: list(value) for key, value in events.items() if value}
        for key, value in frame.events.items():
            self.accumulated_events[key].extend(value)
        self.timeline.append(frame)
        self.state.active_heads = new_heads
        self.state.tick += 1
        return frame

    def propagate(self, max_ticks: Optional[int] = None) -> None:
        if self.pending_placements:
            self.apply_pending_placements()
        self.reset()
        max_ticks = max_ticks or self._default_max_ticks()
        while self.state.tick < max_ticks and self._has_pending_activity():
            frame = self.step()
            if (
                not frame.segments
                and not frame.events
                and not self._has_pending_activity()
            ):
                break
            if self.level.loop_required and self.state.loop_detected:
                if not self.level.min_loop_ticks or (
                    self.state.loop_tick is not None
                    and self.state.loop_tick >= self.level.min_loop_ticks
                ):
                    break
            elif self.required_targets_met():
                if self.level.energy_goal is None:
                    break
                if sum(self.target_energy.values()) >= self.level.energy_goal:
                    break
        if self.state.tick >= max_ticks and self._has_pending_activity():
            self.loop_overflow = True
            overflow_event = {"reason": "max_ticks", "tick": self.state.tick}
            self.accumulated_events["overflow"].append(overflow_event)
        self.last_events = {
            key: list(value) for key, value in self.accumulated_events.items()
        }
        for key in ("explosions", "hits", "obstacles_removed"):
            self.last_events.setdefault(key, [])

    def level_complete(self) -> bool:
        if self.level.loop_required and not self.state.loop_detected:
            return False
        if self.level.energy_goal is not None:
            total_energy = sum(self.target_energy.values())
            if total_energy < self.level.energy_goal:
                return False
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
        timeline_payload: List[Dict[str, object]] = []
        for frame in self.timeline:
            timeline_payload.append(
                {
                    "tick": frame.tick,
                    "segments": [self._segment_payload(segment) for segment in frame.segments],
                    "events": {
                        key: [self._normalise_event(event) for event in value]
                        for key, value in frame.events.items()
                    },
                }
            )
        events_payload = {
            key: [self._normalise_event(event) for event in value]
            for key, value in self.last_events.items()
        }
        summary = {
            "timeline": timeline_payload,
            "path": [self._segment_payload(segment) for segment in self.path],
            "targets": {
                str(position): energy for position, energy in self.target_energy.items()
            },
            "metadata": self.level.metadata,
            "events": events_payload,
            "loop_detected": self.state.loop_detected,
        }
        if self.state.loop_tick is not None:
            summary["loop_tick"] = self.state.loop_tick
        return summary

    def _segment_payload(self, segment: PulseSegment) -> Dict[str, object]:
        return {
            "start": list(segment.start),
            "end": list(segment.end),
            "direction": segment.direction.name,
            "energy": segment.energy,
            "intensity": segment.intensity,
            "tick": segment.tick,
            "lifetime": segment.lifetime,
            "brightness": segment.brightness,
            "source_energy": segment.source_energy,
        }

    @staticmethod
    def _normalise_event(event: Dict[str, object]) -> Dict[str, object]:
        normalised: Dict[str, object] = {}
        for key, value in event.items():
            if (
                isinstance(value, tuple)
                and len(value) == 2
                and all(isinstance(v, int) for v in value)
            ):
                normalised[key] = [value[0], value[1]]
            elif isinstance(value, list):
                normalised[key] = [
                    [item[0], item[1]]
                    if isinstance(item, tuple) and len(item) == 2
                    else item
                    for item in value
                ]
            else:
                normalised[key] = value
        return normalised

    def _trigger_bomb(
        self,
        position: Tuple[int, int],
        bomb: Bomb,
        obstacles_map: Dict[Tuple[int, int], Obstacle],
        *,
        tick: int,
    ) -> Tuple[Dict[str, object], List[Dict[str, object]]]:
        affected: List[Tuple[int, int]] = []
        for obstacle_pos in list(obstacles_map.keys()):
            distance = abs(obstacle_pos[0] - position[0]) + abs(obstacle_pos[1] - position[1])
            if distance <= bomb.power:
                affected.append(obstacle_pos)
                obstacles_map.pop(obstacle_pos, None)
        removal_events: List[Dict[str, object]] = []
        for obstacle_pos in affected:
            if obstacle_pos not in self.destroyed_obstacles:
                self.destroyed_obstacles.add(obstacle_pos)
                removal_event = {
                    "position": obstacle_pos,
                    "cause": "bomb",
                    "tick": tick,
                }
                self.obstacle_removals.append(removal_event)
                removal_events.append(removal_event)
        event = {
            "position": position,
            "power": bomb.power,
            "cleared": affected,
            "tick": tick,
        }
        self.explosion_events.append(event)
        return event, removal_events

    @staticmethod
    def _splitter_outputs(pattern: str, direction: Direction) -> List[Direction]:
        pattern = pattern.lower()
        if pattern in {"dual", "splitter"}:
            return [direction.turn_left(), direction.turn_right()]
        if pattern in {"triple", "tri", "three"}:
            return [direction, direction.turn_left(), direction.turn_right()]
        if pattern in {"cross", "quad"}:
            return [
                direction,
                direction.reverse(),
                direction.turn_left(),
                direction.turn_right(),
            ]
        return [direction]
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
            apply_placement_to_level(level, placement)
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
            if game.target_energy.get(position, 0) < expected:
                return False
        expected_loop = solution_data.get("expected_loop")
        if expected_loop:
            detected = bool(expected_loop.get("detected", True))
            if bool(game.state.loop_detected) != detected:
                return False
            expected_tick = expected_loop.get("tick")
            if expected_tick is not None and game.state.loop_tick != expected_tick:
                return False
        expected_total_energy = solution_data.get("expected_total_energy")
        if expected_total_energy is not None:
            if sum(game.target_energy.values()) < expected_total_energy:
                return False
        expected_explosions = solution_data.get("expected_explosions") or []
        if expected_explosions:
            seen = {tuple(event.get("position")) for event in game.last_events.get("explosions", []) if event.get("position") is not None}
            for entry in expected_explosions:
                if isinstance(entry, (list, tuple)):
                    position = tuple(int(v) for v in entry)
                elif isinstance(entry, str):
                    tokens = [token.strip() for token in entry.strip("()[]").split(",") if token.strip()]
                    position = tuple(int(token) for token in tokens)
                else:
                    continue
                if position not in seen:
                    return False
        return game.required_targets_met()



