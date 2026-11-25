"""
Fastest routes for Pac-Man that never step onto a tile a ghost can reach first.

Dijkstra over tiles, costed in progress units: a move costs move_cost, plus the
pellet pause on every tile with a pellet that Pac-Man leaves (he eats it on
arrival). A neighbour is entered only if Pac-Man would occupy it more than
`margin` ticks before the earliest ghost can (algorithms/safety/arrival.py).
Occupancy times only grow with cost, so the cheapest arrival at a tile is also
its safest: plain Dijkstra over the safe tiles finds every safely reachable
tile and the fastest safe route to it.

A tool, not a player: it answers "where can Pac-Man safely get, and how
fast", never where he should go.
"""

import heapq
from dataclasses import dataclass, field

from pacman_otm.algorithms.safety.arrival import is_safe, pacman_occupancy_tick
from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.speeds import SpeedRules

Position = tuple[int, int]


@dataclass(frozen=True)
class SafeRoutes:
    start: Position
    # Units of moves and pauses to reach each safely reachable tile's centre (start: 0).
    units: dict[Position, int] = field(default_factory=dict)
    # The tick at which Pac-Man first occupies each tile on its route (start: 0).
    occupancy: dict[Position, int] = field(default_factory=dict)
    # Tile -> (previous tile, move from it) on its fastest safe route.
    parents: dict[Position, tuple[Position, Action]] = field(default_factory=dict)

    def reachable(self, tile: Position) -> bool:
        return tile in self.units

    def route_to(self, goal: Position) -> list[Action] | None:
        """The moves of the fastest safe route to `goal`; [] at the start, None if unsafe or unreachable."""

        if goal not in self.units:
            return None

        moves = []
        tile = goal

        while tile != self.start:
            tile, move = self.parents[tile]
            moves.append(move)

        moves.reverse()
        return moves

    def first_tiles(self, goal: Position) -> list[Position]:
        """The tiles of the route to `goal`, after the start."""
        tiles = []
        tile = goal

        while tile != self.start:
            tiles.append(tile)
            tile = self.parents[tile][0]

        tiles.reverse()
        return tiles


def safe_routes(
    maze: Maze,
    start: Position,
    progress: int,
    pellets: set[Position] | frozenset[Position],
    speeds: SpeedRules,
    ghost_ticks: dict[Position, int],
    margin: int,
) -> SafeRoutes:
    """
    Every tile Pac-Man (at the centre of `start` with `progress` units) can reach
    without ever entering a tile unsafely, by its fastest such route. Ties go to
    the move first in MOVEMENTS order, so results are deterministic.
    """
    routes = SafeRoutes(start=start, units={start: 0}, occupancy={start: 0})
    frontier = [(0, 0, start)]
    order = 0
    done: set[Position] = set()

    while frontier:
        units, _, tile = heapq.heappop(frontier)

        if tile in done:
            continue

        done.add(tile)
        # The pause on a pellet he arrives on is paid before he leaves; at the start it is in `progress`.
        pause = speeds.pellet_pause if tile != start and tile in pellets else 0
        tick = pacman_occupancy_tick(units, pause, progress, speeds)
        next_units = units + pause + speeds.move_cost

        for move, neighbour in maze.get_valid_movements(tile).items():
            if neighbour in done or next_units >= routes.units.get(neighbour, next_units + 1):
                continue

            if not is_safe(tick, ghost_ticks.get(neighbour), margin):
                continue

            routes.units[neighbour] = next_units
            routes.occupancy[neighbour] = tick
            routes.parents[neighbour] = (tile, move)
            order += 1
            heapq.heappush(frontier, (next_units, order, neighbour))

    return routes
