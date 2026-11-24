from typing import Any

from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.ghosts import GhostState


class SimulationState:

    pacman_position: tuple[int, int]
    remaining_pellets: set[tuple[int, int]]
    steps: int
    terminated: bool
    termination_reason: str | None
    # Immutable, so copies share it safely. The engine fills it from the maze's spawns.
    ghosts: tuple[GhostState, ...]

    def __init__(self, maze: Maze):

        self.pacman_position = maze.pacman_start
        self.remaining_pellets = set(maze.initial_pellets)

        self.steps = 0

        self.terminated = False
        self.termination_reason = None

        self.ghosts = ()

    def collect_pellet(self) -> None:

        if self.pacman_position in self.remaining_pellets:
            self.remaining_pellets.remove(self.pacman_position)

        if not self.remaining_pellets:
            self.terminated = True
            self.termination_reason = "completed"

    def copy(self) -> "SimulationState":

        new_state = object.__new__(SimulationState)

        new_state.pacman_position = self.pacman_position
        new_state.remaining_pellets = set(self.remaining_pellets)
        new_state.steps = self.steps
        new_state.terminated = self.terminated
        new_state.termination_reason = self.termination_reason
        new_state.ghosts = self.ghosts

        return new_state

    def to_dict(self) -> dict[str, Any]:
        return {
            "pacman_position": self.pacman_position,
            "remaining_pellets": sorted(self.remaining_pellets),
            "steps": self.steps,
            "terminated": self.terminated,
            "termination_reason": self.termination_reason,
            "ghosts": [ghost.to_dict() for ghost in self.ghosts],
        }

    def summary(self) -> dict[str, Any]:
        return {
            "pacman_position": self.pacman_position,
            "remaining_pellets_count": len(self.remaining_pellets),
            "steps": self.steps,
            "terminated": self.terminated,
            "termination_reason": self.termination_reason,
            "ghost_positions": [ghost.position for ghost in self.ghosts],
        }

    def __str__(self) -> str:
        from pacman_otm.statistics_.serialization import pretty_json
        return pretty_json(self.to_dict())
