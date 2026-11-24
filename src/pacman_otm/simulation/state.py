from typing import Any

from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.ghosts import GhostState
from pacman_otm.simulation.speeds import mover_point, occupied_tile

Position = tuple[int, int]


class SimulationState:
    """
    One tick of a run. `steps` counts ticks. Pac-Man and the ghosts are on whole
    tiles plus a progress toward the next one (see simulation/speeds.py):
    pacman_position is the tile he is on or leaving, pacman_heading the move in
    progress (None at a tile centre, waiting for a decision).
    """

    pacman_position: Position
    pacman_heading: Action | None
    # Units of the current move done; negative during a pellet pause.
    pacman_progress: int
    remaining_pellets: set[Position]
    steps: int
    terminated: bool
    termination_reason: str | None
    # Immutable, so copies share it safely. The engine fills it from the maze's spawns.
    ghosts: tuple[GhostState, ...]
    # Units per tile of the run's SpeedRules, to turn progress into a fraction.
    move_cost: int

    def __init__(self, maze: Maze, move_cost: int = 16):

        self.pacman_position = maze.pacman_start
        self.pacman_heading = None
        self.pacman_progress = 0
        self.remaining_pellets = set(maze.initial_pellets)

        self.steps = 0

        self.terminated = False
        self.termination_reason = None

        self.ghosts = ()
        self.move_cost = move_cost

    @property
    def pacman_occupied(self) -> Position:
        """The tile Pac-Man counts as being on (his destination once halfway there)."""
        return occupied_tile(self.pacman_position, self.pacman_heading, self.pacman_progress, self.move_cost)

    @property
    def pacman_point(self) -> tuple[float, float]:
        """Pac-Man's position in fractional tiles, for drawing."""
        return mover_point(self.pacman_position, self.pacman_heading, self.pacman_progress, self.move_cost)

    def ghost_occupied(self, index: int) -> Position:
        ghost = self.ghosts[index]
        return occupied_tile(ghost.position, ghost.heading, ghost.progress, self.move_cost)

    def ghost_point(self, index: int) -> tuple[float, float]:
        ghost = self.ghosts[index]
        return mover_point(ghost.position, ghost.heading, ghost.progress, self.move_cost)

    def collect_pellet(self) -> bool:
        """Eat the pellet on Pac-Man's tile, if any; True when one was eaten."""

        eaten = self.pacman_position in self.remaining_pellets

        if eaten:
            self.remaining_pellets.remove(self.pacman_position)

        if not self.remaining_pellets:
            self.terminated = True
            self.termination_reason = "completed"

        return eaten

    def copy(self) -> "SimulationState":

        new_state = object.__new__(SimulationState)

        new_state.pacman_position = self.pacman_position
        new_state.pacman_heading = self.pacman_heading
        new_state.pacman_progress = self.pacman_progress
        new_state.remaining_pellets = set(self.remaining_pellets)
        new_state.steps = self.steps
        new_state.terminated = self.terminated
        new_state.termination_reason = self.termination_reason
        new_state.ghosts = self.ghosts
        new_state.move_cost = self.move_cost

        return new_state

    def to_dict(self) -> dict[str, Any]:
        return {
            "pacman_position": self.pacman_position,
            "pacman_heading": self.pacman_heading.value if self.pacman_heading is not None else None,
            "pacman_progress": self.pacman_progress,
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
