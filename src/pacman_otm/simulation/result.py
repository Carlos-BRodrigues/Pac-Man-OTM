
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.state import SimulationState
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.statistics_.metrics import SimulationMetrics
from pacman_otm.controllers.base import ControllerStatus


@dataclass
class SimulationResult:
    states: list[SimulationState]
    actions: list[Action]
    statuses: list[ControllerStatus | None]
    metrics: SimulationMetrics
    maze: Maze | None = None

    @classmethod
    def from_engine(
        cls,
        engine: SimulationEngine,
        metrics: SimulationMetrics,
        statuses: list[ControllerStatus | None] | None = None,
    ) -> SimulationResult:
        return cls(
            states=[state.copy() for state in engine.states],
            actions=list(engine.actions),
            statuses=list(statuses) if statuses is not None else [],
            metrics=metrics,
            maze=engine.maze,
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

    def _maze_to_dict(self) -> dict[str, Any] | None:
        if self.maze is None:
            return None

        return {
            "topography": self.maze.topography.tolist(),
            "pacman_start": list(self.maze.pacman_start),
            "initial_pellets": [
                list(position)
                for position in sorted(self.maze.initial_pellets)
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "maze": self._maze_to_dict(),
            "states": [state.to_dict() for state in self.states],
            "actions": [action.value for action in self.actions],
            "statuses": [
                None if status is None else {
                    "target": (
                        list(status.target)
                        if status.target is not None
                        else None
                    ),
                    "planned_path": [
                        list(position)
                        for position in status.planned_path
                    ],
                    "path_index": status.path_index,
                }
                for status in self.statuses
            ],
            "metrics": self.metrics.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SimulationResult:
        maze_data = data.get("maze")

        if maze_data is None:
            raise ValueError(
                "This result does not contain maze information and "
                "cannot be replayed independently."
            )

        maze = Maze(
            topography=maze_data["topography"],
            pacman_start=tuple(maze_data["pacman_start"]),
            pellets={
                tuple(position)
                for position in maze_data["initial_pellets"]
            },
        )

        states = []

        for state_data in data["states"]:
            state = SimulationState(maze)
            state.pacman_position = tuple(state_data["pacman_position"])
            state.remaining_pellets = {
                tuple(position)
                for position in state_data["remaining_pellets"]
            }
            state.steps = state_data["steps"]
            state.terminated = state_data["terminated"]
            state.termination_reason = state_data["termination_reason"]
            states.append(state)

        actions = [
            Action(action_value)
            for action_value in data["actions"]
        ]

        statuses = []

        for status_data in data.get("statuses", []):
            if status_data is None:
                statuses.append(None)
                continue

            target_data = status_data["target"]

            statuses.append(
                ControllerStatus(
                    target=(
                        tuple(target_data)
                        if target_data is not None
                        else None
                    ),
                    planned_path=tuple(
                        tuple(position)
                        for position in status_data["planned_path"]
                    ),
                    path_index=status_data["path_index"],
                )
            )

        metrics = SimulationMetrics(**data["metrics"])

        return cls(
            states=states,
            actions=actions,
            statuses=statuses,
            metrics=metrics,
            maze=maze,
        )

    def save_json(self, filepath: str | Path) -> None:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=4),
            encoding="utf-8",
        )

    @classmethod
    def load_json(cls, filepath: str | Path) -> SimulationResult:
        path = Path(filepath)

        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        return cls.from_dict(data)

    def save_trajectory_json(self, filepath: str | Path) -> None:
        data = {
            "states": [state.to_dict() for state in self.states],
            "actions": [action.value for action in self.actions],
        }

        Path(filepath).write_text(
            json.dumps(data, indent=4),
            encoding="utf-8",
        )

    def save_metrics_json(self, filepath: str | Path) -> None:
        Path(filepath).write_text(
            json.dumps(self.metrics.to_dict(), indent=4),
            encoding="utf-8",
        )

    def __str__(self) -> str:
        return json.dumps(self.to_dict(), indent=4)
