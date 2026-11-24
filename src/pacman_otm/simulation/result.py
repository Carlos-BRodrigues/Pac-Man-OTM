
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
    decode_move,
    decode_moves,
    decode_path,
    encode_move,
    encode_moves,
    encode_path,
)
from pacman_otm.simulation.ghosts import GhostState

# Bumped whenever the saved layout changes. 2: maze.origin, maze.dimensions.
# 3: maze.metrics. 4: ghosts, and the compact layout described in to_dict.
FORMAT_VERSION = 4

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
    encoded = []
    previous_path: tuple[Position, ...] | None = None

    for status in statuses:
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


def _ghost_track(maze: Maze, ghost: dict[str, Any], steps: int) -> list[GhostState]:
    """A ghost's state at every step, from its spawn and move string."""

    moves = decode_moves(ghost["moves"])

    if len(moves) != steps:
        raise ValueError(f"Ghost '{ghost['kind']}' has {len(moves)} moves for {steps} steps.")

    track = [GhostState(kind=ghost["kind"], position=tuple(ghost["spawn"]))]

    for move in moves:
        track.append(
            GhostState(
                kind=ghost["kind"],
                position=maze.get_destination(track[-1].position, move),
                direction=move,
            )
        )

    return track


@dataclass
class SimulationResult:
    states: list[SimulationState]
    actions: list[Action]
    statuses: list[ControllerStatus | None]
    metrics: SimulationMetrics
    maze: Maze | None = None
    # Controller.describe() of the player; None for results saved before it was recorded
    controller: dict[str, Any] | None = None
    # Per step, one status per ghost (the decision made before that step)
    ghost_statuses: list[tuple[GhostStatus | None, ...]] = field(default_factory=list)
    # describe() of each ghost's controller, in ghost order
    ghosts: list[dict[str, Any]] = field(default_factory=list)

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

    def get_action(self, index: int) -> Action:
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
        The saved form: every state, action and status, stored compactly and
        rebuilt exactly by from_dict.

        - States: Pac-Man's position per state, the pellets eaten (step, row,
          col) and how the run ended. The step count is the state's index, the
          remaining pellets follow from the eaten ones, and only the last state
          can be terminated.
        - Actions and ghost tracks are move strings ("ULLD...", one move per step).
        - Ghosts: kind, spawn, controller and moves.
        - Paths are "row,col:MOVES" (see simulation/encoding.py).
        - Pac-Man statuses: fields in "status_fields"; the path is null when
          unchanged since the previous step's status.
        - Ghost statuses: per step, one entry per ghost (fields in "ghost_status_fields").
        """
        self._check_history()

        return {
            "format_version": FORMAT_VERSION,
            "controller": self.controller,
            "maze": maze_to_dict(self.maze) if self.maze is not None else None,
            "terminated": self.states[-1].terminated,
            "termination_reason": self.states[-1].termination_reason,
            "pacman_positions": [list(state.pacman_position) for state in self.states],
            "pellets_eaten": [
                [index, *position]
                for index, (before, after) in enumerate(zip(self.states, self.states[1:]), start=1)
                for position in sorted(before.remaining_pellets - after.remaining_pellets)
            ],
            "actions": encode_moves(self.actions),
            "ghosts": [
                {
                    "kind": ghost.kind,
                    "spawn": list(ghost.position),
                    "controller": self.ghosts[index] if index < len(self.ghosts) else None,
                    "moves": encode_moves([state.ghosts[index].direction for state in self.states[1:]]),
                }
                for index, ghost in enumerate(self.states[0].ghosts)
            ],
            "status_fields": list(STATUS_FIELDS),
            "statuses": _encode_statuses(self.statuses),
            "ghost_status_fields": list(GHOST_STATUS_FIELDS),
            "ghost_statuses": [
                [_encode_ghost_status(status) for status in step]
                for step in self.ghost_statuses
            ],
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
                raise ValueError(f"State {index} breaks the recorded-history layout (steps, termination).")

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
        actions = decode_moves(data["actions"])
        positions = [tuple(position) for position in data["pacman_positions"]]

        if len(positions) != len(actions) + 1:
            raise ValueError("The result has a different number of states and actions.")

        eaten: dict[int, list[Position]] = {}

        for step, row, col in data["pellets_eaten"]:
            eaten.setdefault(step, []).append((row, col))

        ghost_tracks = [_ghost_track(maze, ghost, len(actions)) for ghost in data["ghosts"]]

        states = []
        remaining = set(maze.initial_pellets)

        for index, position in enumerate(positions):
            remaining -= set(eaten.get(index, ()))

            state = SimulationState(maze)
            state.pacman_position = position
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
            ghost_statuses=[
                tuple(_decode_ghost_status(status) for status in step)
                for step in data["ghost_statuses"]
            ],
            ghosts=[ghost["controller"] for ghost in data["ghosts"] if ghost["controller"] is not None],
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
            "actions": [action.value for action in self.actions],
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
