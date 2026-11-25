"""
When movers can reach tiles, in ticks: the measuring tool behind ghost avoidance.

A mover "occupies" the tile it is on until it is halfway to the next one, then
that next tile (simulation/speeds.occupied_tile); a catch happens on occupied
tiles. So these functions answer "from now, after how many ticks does this mover
first occupy tile x?", with the engine's exact integer arithmetic: a move costs
move_cost units, a mover gains its speed every tick, leftover progress carries.
Tick 0 is now (before the next advance); tick t is the state after t advances.

Tools only: which tiles are dangerous enough to avoid is the controller's call.
"""

from collections.abc import Iterable, Mapping, Sequence

from pacman_otm.algorithms.pathfinding.no_reverse import NoReverseSearch
from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.ghosts import GhostState
from pacman_otm.simulation.speeds import SpeedRules

Position = tuple[int, int]


def _ceil_div(numerator: int, denominator: int) -> int:
    return -(-numerator // denominator)


def ticks_to_occupy(units_before: int, progress: int, speed: int, move_cost: int) -> int:
    """
    Ticks until a mover that still has `units_before` units of whole moves ahead
    of the move into a tile, and has done `progress` units so far, is halfway into it.
    """
    needed = units_before + _ceil_div(move_cost, 2) - progress
    return max(0, _ceil_div(needed, speed))


def ghost_occupancy_ticks(
    search: NoReverseSearch,
    maze: Maze,
    ghost: GhostState,
    speeds: SpeedRules,
) -> dict[Position, int]:
    """
    The earliest tick at which the ghost can occupy each tile it can reach,
    driving without reversing. Its committed moves (heading, and next_heading
    once chosen) are followed exactly; after that every legal route counts, so
    this is a lower bound for any ghost strategy. Paths through Pac-Man's tile
    are not blocked: a ghost can really pass him there (only a catch stops it).
    """
    move_cost = speeds.move_cost

    if ghost.heading is None:
        # At the spawn: it decides its first move and moves in the same tick.
        distances = search.distances_from(ghost.position, None)
        ticks = {
            tile: ticks_to_occupy(move_cost * (distance - 1), 0, speeds.ghost, move_cost)
            for tile, distance in distances.items()
            if distance > 0
        }
        ticks[ghost.position] = 0
        return ticks

    # The tiles ahead along its commitment: distance 1, then 2 if the exit is chosen.
    first = maze.get_destination(ghost.position, ghost.heading)
    committed = [(first, 1)]

    if ghost.next_heading is None:
        distances = search.distances_from(first, ghost.heading)
        offset = 1
    else:
        second = maze.get_destination(first, ghost.next_heading)
        committed.append((second, 2))
        distances = search.distances_from(second, ghost.next_heading)
        offset = 2

    ticks: dict[Position, int] = {}

    for tile, distance in distances.items():
        ticks[tile] = ticks_to_occupy(move_cost * (distance + offset - 1), ghost.progress, speeds.ghost, move_cost)

    for tile, distance in committed:
        tick = ticks_to_occupy(move_cost * (distance - 1), ghost.progress, speeds.ghost, move_cost)
        ticks[tile] = min(tick, ticks.get(tile, tick))

    # Its own tile, until it is halfway out of it.
    if 2 * ghost.progress < move_cost:
        ticks[ghost.position] = 0

    return ticks


def earliest_ghost_ticks(per_ghost: Iterable[Mapping[Position, int]]) -> dict[Position, int]:
    """For every tile, the earliest tick any ghost can occupy it."""
    earliest: dict[Position, int] = {}

    for ticks in per_ghost:
        for tile, tick in ticks.items():
            if tick < earliest.get(tile, tick + 1):
                earliest[tile] = tick

    return earliest


def pacman_occupancy_ticks(
    maze: Maze,
    start: Position,
    progress: int,
    moves: Sequence[Action],
    pellets: set[Position] | frozenset[Position],
    speeds: SpeedRules,
) -> list[int]:
    """
    The tick at which Pac-Man, at the centre of `start` with `progress` units
    (leftover from his last move, negative during a pellet pause), first occupies
    each tile of `moves`. Every pellet he arrives on before a tile costs him
    pellet_pause units on the way there.
    """
    ticks = []
    units = 0
    pause = 0
    position = start

    for move in moves:
        ticks.append(pacman_occupancy_tick(units, pause, progress, speeds))
        position = maze.get_destination(position, move)
        units += pause + speeds.move_cost
        pause = speeds.pellet_pause if position in pellets else 0

    return ticks


def pacman_arrival_tick(units: int, progress: int, speeds: SpeedRules) -> int:
    """
    The tick at which Pac-Man reaches the centre of a tile `units` of moves (and
    pellet pauses) away; 0 for the tile he is on.
    """
    return 0 if units == 0 else max(1, _ceil_div(units - progress, speeds.pacman))


def pacman_occupancy_tick(units: int, pause: int, progress: int, speeds: SpeedRules) -> int:
    """
    The tick at which Pac-Man first occupies the tile after one he reaches
    `units` away (`pause`: the pellet pause he pays on that tile).

    He is halfway once his progress covers units + pause + half a move. But at
    the tick he arrives on a tile he stops at its centre to be asked again (any
    leftover is kept for the next move), so he never occupies the next tile
    before the tick after his arrival. Ghosts drive through centres instead,
    which is why their formula has no such floor.
    """
    halfway = _ceil_div(units + pause + _ceil_div(speeds.move_cost, 2) - progress, speeds.pacman)
    return max(pacman_arrival_tick(units, progress, speeds) + 1, halfway)


def is_safe(pacman_tick: int, ghost_tick: int | None, margin: int) -> bool:
    """Pac-Man gets onto the tile at least `margin` + 1 ticks before any ghost can (None: no ghost can)."""
    return ghost_tick is None or pacman_tick + margin < ghost_tick
