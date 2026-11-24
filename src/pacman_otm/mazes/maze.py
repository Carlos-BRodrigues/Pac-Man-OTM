from collections import deque
from collections.abc import Callable, Iterable

import numpy as np

from pacman_otm.mazes.grid import MAX_MAZE_SIZE, MIN_MAZE_SIZE
from pacman_otm.mazes.origin import MazeOrigin
from pacman_otm.mazes.tiles import TILE_RULES, Tile, TileRules
from pacman_otm.simulation.actions import Action

Position = tuple[int, int]


class Maze:
    """
    The static map: tiles, Pac-Man's start, the initial pellets and the ghost
    spawns. Spawns are content like pellets: ordered (ghost i starts on spawn i),
    walkable, distinct, never the start, and a pellet may lie on one.

    Immutable after construction (read-only array, frozenset of pellets), so
    one Maze can be shared by many runs and by every state that refers to it.
    """

    # Order matters: it is the tie-break for BFS and the draw order for
    # random controllers. UP, LEFT, DOWN, RIGHT.
    MOVEMENTS = frozendict(
        {
            Action.UP: (-1, 0),
            Action.LEFT: (0, -1),
            Action.DOWN: (1, 0),
            Action.RIGHT: (0, 1),
        }
    )

    def __init__(
        self,
        topography: Iterable[Iterable[int]] | np.ndarray,
        pacman_start: Position,
        pellets: Iterable[Position],
        origin: MazeOrigin | None = None,
        ghost_spawns: Iterable[Position] = (),
    ) -> None:

        self.topography = self._build_topography(topography)
        self.topography.flags.writeable = False

        self.pacman_start: Position = tuple(pacman_start)
        self.initial_pellets: frozenset[Position] = frozenset(
            tuple(position) for position in pellets
        )
        self.ghost_spawns: tuple[Position, ...] = tuple(
            tuple(position) for position in ghost_spawns
        )
        self.origin = origin

        self._walkable = self._mask(lambda rules: rules.pacman_walkable)
        self._pellet_allowed = self._mask(lambda rules: rules.pellet_allowed)

        self._validate_positions()

        # Built once: movement queries happen on every step and every BFS expansion.
        self._neighbours = self._build_neighbours()

        self._validate_reachability()

    @property
    def height(self) -> int:
        return self.topography.shape[0]

    @property
    def width(self) -> int:
        return self.topography.shape[1]

    @property
    def walkable_mask(self) -> np.ndarray:
        """Read-only boolean grid of walkable tiles."""
        return self._walkable

    @property
    def name(self) -> str:
        return self.origin.name if self.origin is not None else "unnamed"

    def in_bounds(self, position: Position) -> bool:
        row, col = position
        return 0 <= row < self.height and 0 <= col < self.width

    def is_walkable(self, position: Position) -> bool:
        return self.in_bounds(position) and bool(self._walkable[position])

    def validate_position(self, position: Position) -> None:
        if not self.is_walkable(position):
            raise ValueError(f"Position {position} is not walkable.")

    def get_destination(self, position: Position, action: Action) -> Position:
        row, col = position
        d_row, d_col = self.MOVEMENTS[action]
        return row + d_row, col + d_col

    def get_valid_movements(self, position: Position) -> frozendict[Action, Position]:
        """Walkable moves from a walkable position, in MOVEMENTS order."""

        self.validate_position(position)
        return self._neighbours[position]

    def walkable_positions(self) -> list[Position]:
        return list(self._neighbours)

    def debug_print(self) -> None:
        print(f"MAZE {self.name}")
        print("-" * 25)
        print(self.topography)
        print(f"Dimensions: {self.height} x {self.width}")
        print(f"Initial pellets: {len(self.initial_pellets)}")

    # Construction and validation

    @staticmethod
    def _build_topography(topography) -> np.ndarray:
        try:
            # int64 first so out-of-range values are reported, not wrapped.
            grid = np.array(topography, dtype=np.int64)
        except ValueError as error:
            raise ValueError(
                "Maze topography must be a rectangular grid of integers."
            ) from error

        if grid.ndim != 2:
            raise ValueError("Maze topography must be a two-dimensional grid.")

        if grid.size == 0:
            raise ValueError("Maze cannot be empty.")

        known = sorted(int(tile) for tile in Tile)
        unknown = sorted(set(np.unique(grid).tolist()) - set(known))

        if unknown:
            raise ValueError(
                f"Topography contains unknown tile values {unknown}; "
                f"known tiles are {known}."
            )

        height, width = grid.shape

        if not (
            MIN_MAZE_SIZE <= height <= MAX_MAZE_SIZE
            and MIN_MAZE_SIZE <= width <= MAX_MAZE_SIZE
        ):
            raise ValueError(
                f"Maze size {height}x{width} is out of bounds: rows and columns "
                f"must be between {MIN_MAZE_SIZE} and {MAX_MAZE_SIZE}."
            )

        return grid.astype(np.uint8)

    def _mask(self, rule: Callable[[TileRules], bool]) -> np.ndarray:
        mask = np.zeros(self.topography.shape, dtype=bool)

        for tile, rules in TILE_RULES.items():
            if rule(rules):
                mask |= self.topography == tile

        mask.flags.writeable = False
        return mask

    def _validate_positions(self) -> None:

        if not self.is_walkable(self.pacman_start):
            raise ValueError(
                f"Pac-Man start {self.pacman_start} must be on a walkable tile."
            )

        misplaced = sorted(
            pellet
            for pellet in self.initial_pellets
            if not (self.in_bounds(pellet) and self._pellet_allowed[pellet])
        )

        if misplaced:
            raise ValueError(
                f"{len(misplaced)} pellet(s) on tiles that do not allow pellets, "
                f"e.g. {misplaced[:5]}."
            )

        for spawn in self.ghost_spawns:
            if not self.is_walkable(spawn):
                raise ValueError(f"Ghost spawn {spawn} must be on a walkable tile.")

            if spawn == self.pacman_start:
                raise ValueError(f"Ghost spawn {spawn} is Pac-Man's start.")

        if len(set(self.ghost_spawns)) != len(self.ghost_spawns):
            raise ValueError(f"Ghost spawns must be distinct tiles, got {list(self.ghost_spawns)}.")

    def _build_neighbours(self) -> dict[Position, frozendict[Action, Position]]:
        neighbours = {}

        for row, col in zip(*np.nonzero(self._walkable)):
            position = (int(row), int(col))
            moves = {}

            for action in self.MOVEMENTS:
                destination = self.get_destination(position, action)

                if self.is_walkable(destination):
                    moves[action] = destination

            neighbours[position] = frozendict(moves)

        return neighbours

    def _validate_reachability(self) -> None:
        """Every pellet must be collectable, or no run could ever complete; every ghost must reach Pac-Man."""

        reached = {self.pacman_start}
        frontier = deque([self.pacman_start])

        while frontier:
            for neighbour in self._neighbours[frontier.popleft()].values():
                if neighbour not in reached:
                    reached.add(neighbour)
                    frontier.append(neighbour)

        unreachable_spawns = [spawn for spawn in self.ghost_spawns if spawn not in reached]

        if unreachable_spawns:
            raise ValueError(
                f"Ghost spawn(s) {unreachable_spawns} cannot be reached from the start {self.pacman_start}."
            )

        unreachable = sorted(self.initial_pellets - reached)

        if unreachable:
            raise ValueError(
                f"{len(unreachable)} pellet(s) cannot be reached from the start "
                f"{self.pacman_start}, e.g. {unreachable[:5]}."
            )
