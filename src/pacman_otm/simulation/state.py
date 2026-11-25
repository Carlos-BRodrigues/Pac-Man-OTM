from typing import Any

from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.ghosts import GhostState
from pacman_otm.simulation.speeds import ARCADE, SpeedRules, mover_point, occupied_tile

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
    # The last move Pac-Man started (LEFT before his first): which way he faces, kept while he waits or is blocked.
    pacman_facing: Action
    # Units of the current move done; negative during a pellet pause.
    pacman_progress: int
    remaining_pellets: set[Position]
    steps: int
    terminated: bool
    termination_reason: str | None
    # Immutable, so copies share it safely. The engine fills it from the maze's spawns.
    ghosts: tuple[GhostState, ...]
    # The run's speed rules: game rules like the maze, so controllers can time moves. Frozen, shared by copies.
    speeds: SpeedRules

    def __init__(self, maze: Maze, speeds: SpeedRules = ARCADE):

        # Immutable and shared by copies: occupied tiles wrap through its tunnels.
        self._maze = maze
        self.pacman_position = maze.pacman_start
        self.pacman_heading = None
        self.pacman_facing = Action.LEFT
        self.pacman_progress = 0
        self.remaining_pellets = set(maze.initial_pellets)

        self.steps = 0

        self.terminated = False
        self.termination_reason = None

        self.ghosts = ()
        self.speeds = speeds

    @property
    def maze(self) -> Maze:
        """The maze of the run (read-only, shared)."""
        return self._maze

    @property
    def move_cost(self) -> int:
        """Units per tile, to turn progress into a fraction."""
        return self.speeds.move_cost

    @property
    def pacman_occupied(self) -> Position:
        """The tile Pac-Man counts as being on (his destination once halfway there)."""
        return occupied_tile(
            self.pacman_position, self.pacman_heading, self.pacman_progress, self.move_cost, self._maze
        )

    @property
    def pacman_point(self) -> tuple[float, float]:
        """Pac-Man's position in fractional tiles, for drawing."""
        return mover_point(self.pacman_position, self.pacman_heading, self.pacman_progress, self.move_cost)

    def ghost_occupied(self, index: int) -> Position:
        ghost = self.ghosts[index]
        return occupied_tile(ghost.position, ghost.heading, ghost.progress, self.move_cost, self._maze)

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

        new_state._maze = self._maze
        new_state.pacman_position = self.pacman_position
        new_state.pacman_heading = self.pacman_heading
        new_state.pacman_facing = self.pacman_facing
        new_state.pacman_progress = self.pacman_progress
        new_state.remaining_pellets = set(self.remaining_pellets)
        new_state.steps = self.steps
        new_state.terminated = self.terminated
        new_state.termination_reason = self.termination_reason
        new_state.ghosts = self.ghosts
        new_state.speeds = self.speeds

        return new_state

    def to_dict(self) -> dict[str, Any]:
        return {
            "pacman_position": self.pacman_position,
            "pacman_heading": self.pacman_heading.value if self.pacman_heading is not None else None,
            "pacman_facing": self.pacman_facing.value,
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
