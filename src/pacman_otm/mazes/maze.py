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
    walkable by ghosts, distinct, never the start, and a pellet may lie on one.
    Each spawn may be marked for a ghost kind (a plain name such as "pinky";
    None = any ghost). Spawns may lie in the ghost house.

    Two movement graphs, both in MOVEMENTS order:
    - Pac-Man's (`get_valid_movements`): corridors only.
    - The ghosts' (`ghost_moves`): corridors plus the house and its gate, with
      one-way edges (TileRules.ghost_rank): out of the house, never back in.
    Portals: a corridor tile on the grid edge whose tile on the opposite edge (same
    row or column) is a corridor too is a tunnel mouth; moving off the edge there
    arrives on the other side (`get_destination`), in both graphs.

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
        ghost_spawn_kinds: Iterable[str | None] | None = None,
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
        self.ghost_spawn_kinds: tuple[str | None, ...] = (
            tuple(ghost_spawn_kinds) if ghost_spawn_kinds is not None else (None,) * len(self.ghost_spawns)
        )
        self.origin = origin

        if len(self.ghost_spawn_kinds) != len(self.ghost_spawns):
            raise ValueError(
                f"{len(self.ghost_spawn_kinds)} ghost spawn kind(s) for {len(self.ghost_spawns)} spawn(s)."
            )

        self._walkable = self._mask(lambda rules: rules.pacman_walkable)
        self._ghost_walkable = self._mask(lambda rules: rules.ghost_walkable)
        self._pellet_allowed = self._mask(lambda rules: rules.pellet_allowed)
        self._ghost_rank = np.full(self.topography.shape, -1, dtype=np.int8)

        for tile, rules in TILE_RULES.items():
            if rules.ghost_rank is not None:
                self._ghost_rank[self.topography == tile] = rules.ghost_rank

        self.portals: frozendict[tuple[Position, Action], Position] = self._find_portals()

        self._validate_positions()

        # Built once: movement queries happen on every step and every BFS expansion.
        self._neighbours = self._build_neighbours(self._walkable, ghosts=False)
        self._ghost_neighbours = self._build_neighbours(self._ghost_walkable, ghosts=True)

        self._validate_gates()
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
        """The tile one move away; through a tunnel mouth, the tile on the opposite edge."""

        row, col = position
        d_row, d_col = self.MOVEMENTS[action]
        destination = row + d_row, col + d_col

        if self.portals and not self.in_bounds(destination):
            return self.portals.get((position, action), destination)

        return destination

    def is_ghost_walkable(self, position: Position) -> bool:
        return self.in_bounds(position) and bool(self._ghost_walkable[position])

    def validate_ghost_position(self, position: Position) -> None:
        if not self.is_ghost_walkable(position):
            raise ValueError(f"Position {position} is not walkable for ghosts.")

    def ghost_moves(self, position: Position) -> frozendict[Action, Position]:
        """A ghost's moves from a tile it can walk, in MOVEMENTS order (one way out of the house)."""

        self.validate_ghost_position(position)
        return self._ghost_neighbours[position]

    def ghost_positions(self) -> list[Position]:
        return list(self._ghost_neighbours)

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
            if not self.is_ghost_walkable(spawn):
                raise ValueError(f"Ghost spawn {spawn} must be on a tile ghosts can walk.")

            if spawn == self.pacman_start:
                raise ValueError(f"Ghost spawn {spawn} is Pac-Man's start.")

        if len(set(self.ghost_spawns)) != len(self.ghost_spawns):
            raise ValueError(f"Ghost spawns must be distinct tiles, got {list(self.ghost_spawns)}.")

    def _find_portals(self) -> frozendict[tuple[Position, Action], Position]:
        portals = {}
        last_row, last_col = self.height - 1, self.width - 1

        for row in range(self.height):
            if self._walkable[row, 0] and self._walkable[row, last_col]:
                portals[((row, 0), Action.LEFT)] = (row, last_col)
                portals[((row, last_col), Action.RIGHT)] = (row, 0)

        for col in range(self.width):
            if self._walkable[0, col] and self._walkable[last_row, col]:
                portals[((0, col), Action.UP)] = (last_row, col)
                portals[((last_row, col), Action.DOWN)] = (0, col)

        return frozendict(portals)

    def _build_neighbours(self, walkable: np.ndarray, ghosts: bool) -> dict[Position, frozendict[Action, Position]]:
        neighbours = {}
        rank = self._ghost_rank

        for row, col in zip(*np.nonzero(walkable)):
            position = (int(row), int(col))
            moves = {}

            for action in self.MOVEMENTS:
                destination = self.get_destination(position, action)

                if not (self.in_bounds(destination) and walkable[destination]):
                    continue

                # The one-way gate: never onto a lower rank (corridor -> gate -> house).
                if ghosts and rank[destination] < rank[position]:
                    continue

                moves[action] = destination

            neighbours[position] = frozendict(moves)

        return neighbours

    def _validate_gates(self) -> None:
        """A gate leads out of a house: it borders a house tile and a corridor (directly or along the gate)."""

        for row, col in zip(*np.nonzero(self.topography == Tile.GHOST_GATE)):
            position = (int(row), int(col))
            around = {
                Tile(int(self.topography[destination]))
                for action in self.MOVEMENTS
                if self.in_bounds(destination := self.get_destination(position, action))
            }

            if Tile.GHOST_HOUSE not in around or not {Tile.CORRIDOR, Tile.GHOST_GATE} & around:
                raise ValueError(f"Ghost gate {position} must border the ghost house and lead to a corridor.")

    def _validate_reachability(self) -> None:
        """Every pellet must be collectable, or no run could ever complete; every ghost must reach Pac-Man."""

        reached = {self.pacman_start}
        frontier = deque([self.pacman_start])

        while frontier:
            for neighbour in self._neighbours[frontier.popleft()].values():
                if neighbour not in reached:
                    reached.add(neighbour)
                    frontier.append(neighbour)

        unreachable_spawns = [spawn for spawn in self.ghost_spawns if not self._ghost_reaches(spawn, reached)]

        if unreachable_spawns:
            raise ValueError(
                f"Ghost spawn(s) {unreachable_spawns} cannot reach the start {self.pacman_start}."
            )

        unreachable = sorted(self.initial_pellets - reached)

        if unreachable:
            raise ValueError(
                f"{len(unreachable)} pellet(s) cannot be reached from the start "
                f"{self.pacman_start}, e.g. {unreachable[:5]}."
            )

    def _ghost_reaches(self, spawn: Position, corridors: set[Position]) -> bool:
        """A ghost from this spawn gets onto Pac-Man's corridors (from a house spawn: out through the gate)."""

        if spawn in corridors:
            return True

        seen = {spawn}
        frontier = deque([spawn])

        while frontier:
            for neighbour in self._ghost_neighbours[frontier.popleft()].values():
                if neighbour in corridors:
                    return True

                if neighbour not in seen:
                    seen.add(neighbour)
                    frontier.append(neighbour)

        return False
