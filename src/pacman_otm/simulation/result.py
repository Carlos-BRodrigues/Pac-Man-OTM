
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pacman_otm.mazes.maze import Maze
from pacman_otm.mazes.serialization import maze_from_dict, maze_to_dict
from pacman_otm.simulation.state import SimulationState
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.statistics_.metrics import SimulationMetrics
from pacman_otm.statistics_.serialization import pretty_json
from pacman_otm.controllers.controller import ControllerStatus
from pacman_otm.controllers.status import GhostStatus
from pacman_otm.simulation.encoding import (
    decode_arrivals,
    decode_move,
    decode_moves,
    decode_optional_moves,
    decode_path,
    encode_arrivals,
    encode_move,
    encode_moves,
    encode_optional_moves,
    encode_path,
)
from pacman_otm.simulation.ghosts import GhostState
from pacman_otm.simulation.speeds import EQUAL, SpeedRules

# Bumped whenever the saved layout changes. 2: maze.origin, maze.dimensions.
# 3: maze.metrics. 4: ghosts, and the compact layout described in to_dict.
# 5: ticks and speeds: headings, progress and arrivals per tick, repeated statuses.
FORMAT_VERSION = 5

# A status that is the same as the previous tick's (the controller was not asked).
SAME = "="

Position = tuple[int, int]

STATUS_FIELDS = ("target_row", "target_col", "path", "path_index")
GHOST_STATUS_FIELDS = (
    "target_row",
    "target_col",
    "path",
    "decision",
    "decision_row",
    "decision_col",
    "options",
    "decided",
)


def _encode_statuses(statuses: list[ControllerStatus | None]) -> list[list[Any] | None]:
    encoded: list[Any] = []
    previous_path: tuple[Position, ...] | None = None
    previous: ControllerStatus | None = None

    for status in statuses:
        if status is not None and status is previous:
            encoded.append(SAME)
            continue

        previous = status

        if status is None:
            encoded.append(None)
            previous_path = None
            continue

        target = status.target if status.target is not None else (None, None)
        path = None if status.planned_path == previous_path else encode_path(status.planned_path)
        encoded.append([*target, path, status.path_index])
        previous_path = status.planned_path

    return encoded


def _decode_statuses(encoded: list[list[Any] | None]) -> list[ControllerStatus | None]:
    statuses: list[ControllerStatus | None] = []
    previous_path: tuple[Position, ...] = ()

    for item in encoded:
        if item == SAME:
            statuses.append(statuses[-1])
            continue

        if item is None:
            statuses.append(None)
            continue

        target_row, target_col, path, path_index = item
        previous_path = previous_path if path is None else decode_path(path)
        statuses.append(
            ControllerStatus(
                target=(target_row, target_col) if target_row is not None else None,
                planned_path=previous_path,
                path_index=path_index,
            )
        )

    return statuses


def _encode_ghost_status(status: GhostStatus | None) -> list[Any] | None:
    if status is None:
        return None

    target = status.target if status.target is not None else (None, None)
    tile = status.decision_tile if status.decision_tile is not None else (None, None)

    return [
        *target,
        encode_path(status.planned_path),
        encode_move(status.decision),
        *tile,
        encode_moves(status.options),
        status.decided,
    ]


def _decode_ghost_status(item: list[Any] | None) -> GhostStatus | None:
    if item is None:
        return None

    target_row, target_col, path, decision, tile_row, tile_col, options, decided = item

    return GhostStatus(
        target=(target_row, target_col) if target_row is not None else None,
        planned_path=decode_path(path),
        decision=decode_move(decision),
        decision_tile=(tile_row, tile_col) if tile_row is not None else None,
        options=tuple(decode_moves(options)),
        decided=decided,
    )


def _encode_ghost_statuses(steps: list[tuple[GhostStatus | None, ...]]) -> list[list[Any]]:
    encoded = []
    previous: tuple[GhostStatus | None, ...] = ()

    for step in steps:
        encoded.append(
            [
                SAME if index < len(previous) and status is not None and status is previous[index]
                else _encode_ghost_status(status)
                for index, status in enumerate(step)
            ]
        )
        previous = step

    return encoded


def _decode_ghost_statuses(encoded: list[list[Any]]) -> list[tuple[GhostStatus | None, ...]]:
    steps: list[tuple[GhostStatus | None, ...]] = []

    for step in encoded:
        steps.append(
            tuple(
                steps[-1][index] if item == SAME else _decode_ghost_status(item)
                for index, item in enumerate(step)
            )
        )

    return steps


def _ghost_track(ghost: dict[str, Any], states: int) -> list[GhostState]:
    """A ghost's state at every tick, from its spawn and per-tick strings."""

    positions = decode_arrivals(tuple(ghost["spawn"]), ghost["moves"])
    headings = decode_optional_moves(ghost["headings"])
    next_headings = decode_optional_moves(ghost["next_headings"])
    progress = ghost["progress"]

    if not len(positions) == len(headings) == len(next_headings) == len(progress) == states:
        raise ValueError(f"Ghost '{ghost['kind']}' does not have one entry per tick.")

    return [
        GhostState(
            kind=ghost["kind"],
            position=position,
            heading=heading,
            next_heading=next_heading,
            progress=amount,
        )
        for position, heading, next_heading, amount in zip(positions, headings, next_headings, progress)
    ]


@dataclass
class SimulationResult:
    states: list[SimulationState]
    # Pac-Man's decision in each tick; None in ticks where he was moving and not asked.
    actions: list[Action | None]
    # Per tick, the latest status (the same object again while the controller is not asked)
    statuses: list[ControllerStatus | None]
    metrics: SimulationMetrics
    maze: Maze | None = None
    # Controller.describe() of the player; None for results saved before it was recorded
    controller: dict[str, Any] | None = None
    # Per step, one status per ghost (the decision made before that step)
    ghost_statuses: list[tuple[GhostStatus | None, ...]] = field(default_factory=list)
    # describe() of each ghost's controller, in ghost order
    ghosts: list[dict[str, Any]] = field(default_factory=list)
    # The movement speeds of the run
    speeds: SpeedRules = EQUAL

    @classmethod
    def from_engine(
        cls,
        engine: SimulationEngine,
        metrics: SimulationMetrics,
        statuses: list[ControllerStatus | None] | None = None,
        controller: dict[str, Any] | None = None,
        ghost_statuses: list[tuple[GhostStatus | None, ...]] | None = None,
        ghosts: list[dict[str, Any]] | None = None,
    ) -> SimulationResult:
        return cls(
            states=[state.copy() for state in engine.states],
            actions=list(engine.actions),
            statuses=list(statuses) if statuses is not None else [],
            metrics=metrics,
            maze=engine.maze,
            controller=dict(controller) if controller is not None else None,
            ghost_statuses=list(ghost_statuses) if ghost_statuses is not None else [],
            ghosts=[dict(ghost) for ghost in ghosts or []],
            speeds=engine.speeds,
        )

    @property
    def final_state(self) -> SimulationState:
        return self.get_state(-1)

    def get_state(self, index: int) -> SimulationState:
        return self.states[index].copy()

    def get_state_at_step(self, step: int) -> SimulationState:
        if not 0 <= step < len(self.states):
            raise IndexError(f"Step {step} is outside the recorded history.")
        return self.get_state(step)

    def get_action(self, index: int) -> Action | None:
        return self.actions[index]

    def history_summary(self) -> list[dict[str, Any]]:
        history = []

        for index, state in enumerate(self.states):
            next_action = (
                self.actions[index]
                if index < len(self.actions)
                else None
            )

            history.append({
                "step": state.steps,
                "pacman_position": state.pacman_position,
                "remaining_pellets": len(state.remaining_pellets),
                "next_action": (
                    next_action.value if next_action is not None else None
                ),
            })

        return history

    def to_dict(self) -> dict[str, Any]:
        """
        The saved form: every tick, action and status, stored compactly and
        rebuilt exactly by from_dict.

        - Time runs in ticks; the tick count is the state's index, and only the
          last state can be terminated.
        - Per mover, strings with one character per state or tick: "moves" (the
          tile it arrived on in that tick, "." when none), "headings" (the move in
          progress, "." for none), and a list of "progress" values. Ghosts also
          have "next_headings" (the exit chosen one tile ahead).
        - Pellets: the eaten ones as (tick, row, col); the remaining pellets follow.
        - "actions": Pac-Man's decision per tick ("." when he was not asked).
        - Paths are "row,col:MOVES" (see simulation/encoding.py).
        - Pac-Man statuses: fields in "status_fields"; the path is null when
          unchanged since the previous status. Ghost statuses: per tick, one entry
          per ghost (fields in "ghost_status_fields"). "=" in either: the same
          status as the previous tick (the controller was not asked).
        """
        self._check_history()

        return {
            "format_version": FORMAT_VERSION,
            "controller": self.controller,
            "speeds": self.speeds.to_dict(),
            "maze": maze_to_dict(self.maze) if self.maze is not None else None,
            "terminated": self.states[-1].terminated,
            "termination_reason": self.states[-1].termination_reason,
            "pacman": {
                "start": list(self.states[0].pacman_position),
                "moves": encode_arrivals([state.pacman_position for state in self.states]),
                "headings": encode_optional_moves([state.pacman_heading for state in self.states]),
                "progress": [state.pacman_progress for state in self.states],
            },
            "pellets_eaten": [
                [index, *position]
                for index, (before, after) in enumerate(zip(self.states, self.states[1:]), start=1)
                for position in sorted(before.remaining_pellets - after.remaining_pellets)
            ],
            "actions": encode_optional_moves(self.actions),
            "ghosts": [
                {
                    "kind": ghost.kind,
                    "spawn": list(ghost.position),
                    "controller": self.ghosts[index] if index < len(self.ghosts) else None,
                    "moves": encode_arrivals([state.ghosts[index].position for state in self.states]),
                    "headings": encode_optional_moves([state.ghosts[index].heading for state in self.states]),
                    "next_headings": encode_optional_moves(
                        [state.ghosts[index].next_heading for state in self.states]
                    ),
                    "progress": [state.ghosts[index].progress for state in self.states],
                }
                for index, ghost in enumerate(self.states[0].ghosts)
            ],
            "status_fields": list(STATUS_FIELDS),
            "statuses": _encode_statuses(self.statuses),
            "ghost_status_fields": list(GHOST_STATUS_FIELDS),
            "ghost_statuses": _encode_ghost_statuses(self.ghost_statuses),
            "metrics": self.metrics.to_dict(),
        }

    def _check_history(self) -> None:
        """What the compact form relies on; the engine always records histories like this."""

        if not self.states or len(self.states) != len(self.actions) + 1:
            raise ValueError("A result needs one more state than actions.")

        if self.maze is not None and self.states[0].remaining_pellets != self.maze.initial_pellets:
            raise ValueError("The first state must hold the maze's initial pellets.")

        for index, state in enumerate(self.states):
            if state.steps != index or (state.terminated and index != len(self.states) - 1):
                raise ValueError(f"State {index} breaks the recorded-history layout (ticks, termination).")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SimulationResult:
        version = data.get("format_version")

        if version != FORMAT_VERSION:
            raise ValueError(
                f"Unsupported result format version {version!r}; this version of "
                f"pacman_otm reads version {FORMAT_VERSION}. Re-run the simulation."
            )

        maze_data = data.get("maze")

        if maze_data is None:
            raise ValueError(
                "This result does not contain maze information and "
                "cannot be replayed independently."
            )

        maze = maze_from_dict(maze_data)
        speeds = SpeedRules.from_dict(data["speeds"])
        actions = decode_optional_moves(data["actions"])

        pacman = data["pacman"]
        positions = decode_arrivals(tuple(pacman["start"]), pacman["moves"])
        headings = decode_optional_moves(pacman["headings"])
        progress = pacman["progress"]

        if not len(positions) == len(headings) == len(progress) == len(actions) + 1:
            raise ValueError("The result does not have one Pac-Man entry per tick.")

        eaten: dict[int, list[Position]] = {}

        for step, row, col in data["pellets_eaten"]:
            eaten.setdefault(step, []).append((row, col))

        ghost_tracks = [_ghost_track(ghost, len(positions)) for ghost in data["ghosts"]]

        states = []
        remaining = set(maze.initial_pellets)

        for index, position in enumerate(positions):
            remaining -= set(eaten.get(index, ()))

            state = SimulationState(maze, speeds.move_cost)
            state.pacman_position = position
            state.pacman_heading = headings[index]
            state.pacman_progress = progress[index]
            state.remaining_pellets = set(remaining)
            state.steps = index
            state.ghosts = tuple(track[index] for track in ghost_tracks)
            states.append(state)

        states[-1].terminated = data["terminated"]
        states[-1].termination_reason = data["termination_reason"]

        return cls(
            states=states,
            actions=actions,
            statuses=_decode_statuses(data["statuses"]),
            metrics=SimulationMetrics(**data["metrics"]),
            maze=maze,
            controller=data.get("controller"),
            ghost_statuses=_decode_ghost_statuses(data["ghost_statuses"]),
            ghosts=[ghost["controller"] for ghost in data["ghosts"] if ghost["controller"] is not None],
            speeds=speeds,
        )

    def save_json(self, filepath: str | Path) -> None:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            pretty_json(self.to_dict()),
            encoding="utf-8",
        )

    @classmethod
    def load_json(cls, filepath: str | Path) -> SimulationResult:
        path = Path(filepath)

        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        return cls.from_dict(data)

    def save_trajectory_json(self, filepath: str | Path) -> None:
        """Every state in full (pellets and ghosts included): large, for reading by eye."""
        data = {
            "states": [state.to_dict() for state in self.states],
            "actions": [action.value if action is not None else None for action in self.actions],
        }

        Path(filepath).write_text(
            pretty_json(data),
            encoding="utf-8",
        )

    def save_metrics_json(self, filepath: str | Path) -> None:
        Path(filepath).write_text(
            pretty_json(self.metrics.to_dict()),
            encoding="utf-8",
        )

    def __str__(self) -> str:
        return pretty_json(self.to_dict())
