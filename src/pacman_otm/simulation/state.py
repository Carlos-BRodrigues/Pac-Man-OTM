from typing import Any

from pacman_otm.mazes.maze import Maze


class SimulationState:

    pacman_position: tuple[int, int]
    ghost_position: tuple[int, int] | None
    ghost_direction: tuple[int, int]
    ghost_period: int
    remaining_pellets: set[tuple[int, int]]
    steps: int
    terminated: bool
    termination_reason: str | None

    def __init__(self, maze: Maze):

        self.pacman_position = maze.pacman_start
        self.ghost_position = maze.ghost_start
        self.ghost_direction = (0, 0)
        self.ghost_period = maze.ghost_period
        self.remaining_pellets = set(maze.initial_pellets)

        self.steps = 0

        self.terminated = False
        self.termination_reason = None

    def collect_pellet(self) -> None:

        if self.pacman_position in self.remaining_pellets:
            self.remaining_pellets.remove(self.pacman_position)

        if not self.remaining_pellets:
            self.terminated = True
            self.termination_reason = "completed"

    def copy(self) -> "SimulationState":

        new_state = object.__new__(SimulationState)

        new_state.pacman_position = self.pacman_position
        new_state.ghost_position = self.ghost_position
        new_state.ghost_direction = self.ghost_direction
        new_state.ghost_period = self.ghost_period
        new_state.remaining_pellets = set(self.remaining_pellets)
        new_state.steps = self.steps
        new_state.terminated = self.terminated
        new_state.termination_reason = self.termination_reason

        return new_state

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "pacman_position": self.pacman_position,
            "remaining_pellets": sorted(self.remaining_pellets),
            "steps": self.steps,
            "terminated": self.terminated,
            "termination_reason": self.termination_reason,
        }
        if self.ghost_position is not None:
            data["ghost_position"] = self.ghost_position
            data["ghost_direction"] = self.ghost_direction
            data["ghost_period"] = self.ghost_period
        return data

    def summary(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "pacman_position": self.pacman_position,
            "remaining_pellets_count": len(self.remaining_pellets),
            "steps": self.steps,
            "terminated": self.terminated,
            "termination_reason": self.termination_reason,
        }
        if self.ghost_position is not None:
            data["ghost_position"] = self.ghost_position
        return data

    def __str__(self) -> str:
        from pacman_otm.statistics_.serialization import pretty_json
        return pretty_json(self.to_dict())