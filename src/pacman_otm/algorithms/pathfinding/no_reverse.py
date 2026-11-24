from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.actions import Action

Position = tuple[int, int]

# Headings are indices into Maze.MOVEMENTS (UP, LEFT, DOWN, RIGHT); the reverse of
# heading h is (h + 2) % 4.
_ACTIONS: tuple[Action, ...] = tuple(Maze.MOVEMENTS)
_HEADING = {action: index for index, action in enumerate(_ACTIONS)}


def reverse(action: Action) -> Action:
    return action.reverse


class NoReverseSearch:
    """
    Shortest paths for a mover that may never reverse: at every tile it takes
    any exit except the way it came, and only at a dead end (no other exit)
    does it turn back. This is how ghosts move.

    A plain shortest path often runs back through the tile just left, which such
    a mover cannot follow; this search returns the shortest path it can actually
    drive. Ties go to the first move in Maze.MOVEMENTS order (UP, LEFT, DOWN,
    RIGHT): breadth-first search with ordered expansion finds, among the
    shortest paths, the one whose moves come first in that order.

    It is a tool, not a player: it answers "how to get from A to B", never which B.
    """

    def __init__(self, maze: Maze) -> None:
        self.maze = maze
        self._positions: list[Position] = maze.walkable_positions()
        self._index = {position: index for index, position in enumerate(self._positions)}

        # State = tile index * 4 + heading (the move that arrived there).
        # _successors[state] = [(heading, next state), ...] for the legal moves.
        self._successors: list[list[tuple[int, int]]] = []
        # Moves from a tile without a heading (a ghost at its spawn): every exit.
        self._exits: list[list[tuple[int, int]]] = []

        for position in self._positions:
            moves = [
                (_HEADING[action], self._index[destination] * 4 + _HEADING[action])
                for action, destination in maze.get_valid_movements(position).items()
            ]
            self._exits.append(moves)

            for heading in range(4):
                back = (heading + 2) % 4
                forward = [move for move in moves if move[0] != back]
                self._successors.append(forward or [move for move in moves if move[0] == back])

    def legal_moves(self, position: Position, heading: Action | None) -> tuple[Action, ...]:
        """The moves allowed from `position` when it was entered moving `heading`, in MOVEMENTS order."""

        tile = self._index[position]
        moves = self._exits[tile] if heading is None else self._successors[tile * 4 + _HEADING[heading]]
        return tuple(_ACTIONS[move] for move, _ in moves)

    def find_path(
        self,
        start: Position,
        heading: Action | None,
        goal: Position,
    ) -> list[Action] | None:
        """
        The shortest legal path from `start`, entered moving `heading` (None: no
        constraint on the first move), to `goal`; [] when already there, None if
        the goal cannot be reached.
        """
        self.maze.validate_position(start)
        self.maze.validate_position(goal)

        if start == goal:
            return []

        start_tile = self._index[start]
        goal_tile = self._index[goal]
        successors = self._successors

        # parent[state] = previous state, or -1 for a first move; -2 = not reached.
        parent = [-2] * len(successors)
        first_moves = self._exits[start_tile] if heading is None else successors[start_tile * 4 + _HEADING[heading]]
        frontier: list[int] = []

        for _, state in first_moves:
            if parent[state] == -2:
                parent[state] = -1

                if state >> 2 == goal_tile:
                    return self._path(parent, state)

                frontier.append(state)

        while frontier:
            next_frontier = []

            for state in frontier:
                for _, following in successors[state]:
                    if parent[following] != -2:
                        continue

                    parent[following] = state

                    if following >> 2 == goal_tile:
                        return self._path(parent, following)

                    next_frontier.append(following)

            frontier = next_frontier

        return None

    @staticmethod
    def _path(parent: list[int], state: int) -> list[Action]:
        actions = []

        while state >= 0:
            actions.append(_ACTIONS[state & 3])
            state = parent[state]

        actions.reverse()
        return actions
