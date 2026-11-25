import math
from itertools import islice
from typing import Any

from pacman_otm.algorithms.pathfinding.no_reverse import NoReverseSearch
from pacman_otm.controllers.algorithmic.tours.two_opt import TwoOptController
from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.ghosts import GhostState
from pacman_otm.simulation.state import SimulationState

Position = tuple[int, int]


class TwoOptAvoidController(TwoOptController):
    """
    The 2-opt tour with a simple ghost check (Level 1: danger check + flee).

    At every decision the next HORIZON tiles of the planned path are checked: the
    tile reached after n moves is unsafe if a ghost can reach it, driving without
    reversing, in at most n + MARGIN tiles. If any is unsafe, Pac-Man takes the
    neighbour farthest from the nearest ghost instead, then re-paths to the same
    target at the next decision. A baseline: tiles only (no speeds or pellet
    pauses), no lookahead after fleeing, no trap check.
    """

    HORIZON = 6
    MARGIN = 1

    def __init__(self, maze: Maze) -> None:
        self.ghost_search = NoReverseSearch(maze)
        super().__init__(maze)

    def reset(self) -> None:
        super().reset()
        self.flee_count = 0
        self._plan_stale = False

    def describe(self) -> dict[str, Any]:
        return {
            **super().describe(),
            "avoidance": {
                "horizon": self.HORIZON,
                "margin": self.MARGIN,
                "flee_count": self.flee_count,
            },
        }

    def select_action(self, state: SimulationState) -> Action:

        if self._plan_stale and self.current_target in state.remaining_pellets:
            self._repath(state)

        self._plan_stale = False
        action = super().select_action(state)

        if not state.ghosts:
            return action

        ghost_distances = [self._ghost_distances(ghost) for ghost in state.ghosts]

        if self._path_is_safe(state.pacman_position, action, ghost_distances):
            return action

        self.flee_count += 1
        flee = self._flee_action(state.pacman_position, ghost_distances)
        self._plan_stale = flee != action
        return flee

    def _ghost_distances(self, ghost: GhostState) -> dict[Position, int]:
        """Tiles from the ghost to every tile, counted from the tile it is on or leaving."""

        if ghost.heading is None:
            return self.ghost_search.distances_from(ghost.position, None)

        # It is already on its way to the next tile along its heading.
        next_tile = self.maze.get_destination(ghost.position, ghost.heading)
        distances = {
            position: distance + 1
            for position, distance in self.ghost_search.distances_from(next_tile, ghost.heading).items()
        }
        distances[ghost.position] = 0
        return distances

    def _path_is_safe(
        self,
        start: Position,
        action: Action,
        ghost_distances: list[dict[Position, int]],
    ) -> bool:
        position = start

        for index, move in enumerate([action, *islice(self.current_plan, self.HORIZON - 1)]):
            position = self.maze.get_destination(position, move)

            for distances in ghost_distances:
                if distances.get(position, math.inf) <= index + 1 + self.MARGIN:
                    return False

        return True

    def _flee_action(self, start: Position, ghost_distances: list[dict[Position, int]]) -> Action:
        """The move to the neighbour with the largest distance to the nearest ghost; ties in MOVEMENTS order."""

        def nearest_ghost(neighbour: Position) -> float:
            return min(distances.get(neighbour, math.inf) for distances in ghost_distances)

        # max keeps the first of equal scores; get_valid_movements is in MOVEMENTS order.
        return max(
            self.maze.get_valid_movements(start).items(),
            key=lambda move: nearest_ghost(move[1]),
        )[0]
