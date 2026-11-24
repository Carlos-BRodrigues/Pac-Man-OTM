from typing import Any

from pacman_otm.mazes.maze import Maze


class SimulationState:

    pacman_position: tuple[int, int]
    ghost_positions: tuple[tuple[int, int], ...]
    ghost_directions: tuple[tuple[int, int], ...]
    ghost_period: int
    remaining_pellets: set[tuple[int, int]]
    steps: int
    terminated: bool
    termination_reason: str | None

    def __init__(self, maze: Maze):

        self.pacman_position = maze.pacman_start
        self.ghost_positions = tuple(maze.ghost_starts)
        self.ghost_directions = tuple((0, 0) for _ in maze.ghost_starts)
        self.ghost_period = maze.ghost_period
        self.remaining_pellets = set(maze.initial_pellets)

        self.steps = 0

        self.terminated = False
        self.termination_reason = None

    @property
    def ghost_position(self) -> tuple[int, int] | None:
        return self.ghost_positions[0] if self.ghost_positions else None

    @ghost_position.setter
    def ghost_position(self, value: tuple[int, int] | None) -> None:
        if value is None:
            self.ghost_positions = ()
        elif not self.ghost_positions:
            self.ghost_positions = (tuple(value),)
        else:
            self.ghost_positions = (tuple(value),) + self.ghost_positions[1:]

    @property
    def ghost_direction(self) -> tuple[int, int]:
        return self.ghost_directions[0] if self.ghost_directions else (0, 0)

    @ghost_direction.setter
    def ghost_direction(self, value: tuple[int, int]) -> None:
        if not self.ghost_directions:
            self.ghost_directions = (tuple(value),)
        else:
            self.ghost_directions = (tuple(value),) + self.ghost_directions[1:]

    def collect_pellet(self) -> None:

        if self.pacman_position in self.remaining_pellets:
            self.remaining_pellets.remove(self.pacman_position)

        if not self.remaining_pellets:
            self.terminated = True
            self.termination_reason = "completed"

    def copy(self) -> "SimulationState":

        new_state = object.__new__(SimulationState)

        new_state.pacman_position = self.pacman_position
        new_state.ghost_positions = self.ghost_positions
        new_state.ghost_directions = self.ghost_directions
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
        if self.ghost_positions:
            data["ghost_positions"] = [list(p) for p in self.ghost_positions]
            data["ghost_directions"] = [list(d) for d in self.ghost_directions]
            data["ghost_position"] = self.ghost_positions[0]
            data["ghost_direction"] = self.ghost_directions[0]
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
        if self.ghost_positions:
            data["ghost_positions"] = list(self.ghost_positions)
        return data

    def __str__(self) -> str:
        from pacman_otm.statistics_.serialization import pretty_json
        return pretty_json(self.to_dict())