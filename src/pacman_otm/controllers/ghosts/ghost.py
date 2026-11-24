from abc import abstractmethod
from typing import Any, ClassVar

from pacman_otm.algorithms.pathfinding.no_reverse import NoReverseSearch
from pacman_otm.controllers.controller import Controller
from pacman_otm.controllers.status import GhostStatus
from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.state import SimulationState

Position = tuple[int, int]


class GhostController(Controller):
    """
    The movement every ghost shares. A subclass only says where it wants to go
    (`target`); this class decides how, under the arcade constraints:

    - A ghost moves every step and never reverses, except at a dead end.
    - It always knows the shortest legal path to its target (NoReverseSearch),
      but can only act on it at junctions; in a corridor or a turn there is one move.
    - It decides one tile ahead. When it moves onto tile Y, it already chooses
      the exit it will take out of Y, using Pac-Man's position at that moment,
      and that choice is final. A player who turns after a ghost has committed
      can juke it.

    Memory: `direction`, the move out of the current tile (already committed),
    and `next_direction`, the exit out of the tile it is moving to. At the spawn
    there is no heading, so the first move is free.
    """

    controller_type = "ghost"
    kind: ClassVar[str]

    def __init__(self, maze: Maze, ghost_index: int) -> None:
        super().__init__()
        self.maze = maze
        self.ghost_index = ghost_index
        self.search = NoReverseSearch(maze)
        self.reset()

    @abstractmethod
    def target(self, state: SimulationState) -> Position:
        """The tile this ghost wants to reach, given the current state."""

    def reset(self) -> None:
        self.direction: Action | None = None
        self.next_direction: Action | None = None
        self.clear_status()

    def select_action(self, state: SimulationState) -> Action:
        position = state.ghosts[self.ghost_index].position
        target = self.target(state)

        if self.next_direction is None:
            # At the spawn: no heading, so any first move.
            path = self.search.find_path(position, None, target)
            self.direction = path[0] if path else self.search.legal_moves(position, None)[0]
        else:
            self.direction = self.next_direction

        ahead = self.maze.get_destination(position, self.direction)
        options = self.search.legal_moves(ahead, self.direction)
        decided = len(options) > 1

        # The search runs at every junction, and every step when the overlay needs the path.
        path = (
            self.search.find_path(ahead, self.direction, target)
            if decided or self._status_collection_enabled
            else None
        )

        # A target on the junction itself, or unreachable: the first legal exit.
        self.next_direction = path[0] if decided and path else options[0]

        if self._status_collection_enabled:
            self._update_status(
                GhostStatus(
                    target=target,
                    planned_path=self._positions(ahead, path or [self.next_direction]),
                    decision=self.next_direction,
                    decision_tile=ahead,
                    options=options,
                    decided=decided,
                )
            )

        return self.direction

    def _positions(self, start: Position, path: list[Action]) -> tuple[Position, ...]:
        positions = [start]

        for action in path:
            positions.append(self.maze.get_destination(positions[-1], action))

        return tuple(positions)

    def describe(self) -> dict[str, Any]:
        return {
            **super().describe(),
            "kind": self.kind,
            "ghost_index": self.ghost_index,
        }
