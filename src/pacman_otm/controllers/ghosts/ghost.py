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

    - A ghost moves all the time and never reverses, except at a dead end.
    - It always knows the shortest legal path to its target (NoReverseSearch),
      but can only act on it at junctions; in a corridor or a turn there is one move.
    - It decides one tile ahead: while moving from its tile onto the next, it
      already chooses the exit it will take out of that next tile, using where
      Pac-Man is at that moment, and that choice is final. A player who turns
      after a ghost has committed can juke it.

    The engine asks once per tile, and keeps the commitment in the ghost's state
    (GhostState.next_heading), so this controller has no memory of its own. At
    the spawn there is no heading yet: it is asked for a free first move, then
    for the exit of the tile that move leads to.
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
        self.clear_status()

    def select_action(self, state: SimulationState) -> Action:
        ghost = state.ghosts[self.ghost_index]
        target = self.target(state)

        # At the spawn: any first move. Otherwise: the exit of the tile ahead.
        tile, heading = (
            (ghost.position, None)
            if ghost.heading is None
            else (self.maze.get_destination(ghost.position, ghost.heading), ghost.heading)
        )

        options = self.search.legal_moves(tile, heading)
        decided = len(options) > 1

        # The search runs at every junction, and every tile when the overlay needs the path.
        path = (
            self.search.find_path(tile, heading, target)
            if decided or self._status_collection_enabled
            else None
        )

        # A target on that tile itself, or unreachable: the first legal exit.
        choice = path[0] if decided and path else options[0]

        if self._status_collection_enabled:
            start = (ghost.position,) if tile != ghost.position else ()
            self._update_status(
                GhostStatus(
                    target=target,
                    planned_path=start + self._positions(tile, path or [choice]),
                    decision=choice,
                    decision_tile=tile,
                    options=options,
                    decided=decided,
                )
            )

        return choice

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
