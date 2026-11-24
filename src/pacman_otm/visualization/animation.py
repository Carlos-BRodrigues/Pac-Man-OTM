"""
Animation derived from recorded states only.

Movers are drawn at their continuous position: tile plus progress along the
heading (see simulation/speeds.py). Between two ticks a mover follows a short
track, from where it was, through the centre of any tile it arrived on, to
where it is, so turns are drawn round the corner, never across it.

The chomp loop advances once per drawn in-between frame while the player moves,
a little more than one loop per tile. When the player does not move (blocked by
a wall) the pose freezes. Facing is the direction of the latest movement.
Nothing here calls a controller or the engine, so live play and replay produce
the same poses.
"""

from dataclasses import dataclass

from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.ghosts import CAUGHT_REASON
from pacman_otm.simulation.state import SimulationState
from pacman_otm.visualization.sprites import GHOST_FRAMES, Mouth

Position = tuple[int, int]
Point = tuple[float, float]

CHOMP_LOOP = (Mouth.CLOSED, Mouth.HALF, Mouth.WIDE, Mouth.HALF)

# In-between frames drawn for each simulation step. Deliberately not a multiple of
# len(CHOMP_LOOP): with 4, every tile centre would land on the same loop position,
# so a player stopped by a wall would always freeze on the closed shape. With 5,
# the shape at a tile centre cycles through the whole loop, and the frozen frame
# is whatever the player had when he stopped.
SUBFRAMES = 5

INITIAL_FACING = Action.LEFT

_DIRECTIONS = {offset: action for action, offset in Maze.MOVEMENTS.items()}


@dataclass(frozen=True)
class PlayerPose:
    facing: Action
    # Position in CHOMP_LOOP, counted since the start of the run
    chomp_step: int = 0

    @property
    def mouth(self) -> Mouth:
        return CHOMP_LOOP[self.chomp_step % len(CHOMP_LOOP)]


INITIAL_POSE = PlayerPose(facing=INITIAL_FACING)


def move_direction(previous: Position, current: Position) -> Action | None:
    """The one-tile move from previous to current, or None if the player did not move."""
    offset = (current[0] - previous[0], current[1] - previous[1])
    return _DIRECTIONS.get(offset)


def track(previous_point: Point, previous_tile: Position, current_tile: Position, current_point: Point) -> list[Point]:
    """The way a mover went in one tick: via the centre of the tile it arrived on, if any."""

    points = [previous_point]

    if current_tile != previous_tile:
        points.append((float(current_tile[0]), float(current_tile[1])))

    points.append(current_point)
    return points


def pacman_track(previous: SimulationState, current: SimulationState) -> list[Point]:
    return track(previous.pacman_point, previous.pacman_position, current.pacman_position, current.pacman_point)


def ghost_track(previous: SimulationState, current: SimulationState, index: int) -> list[Point]:
    if index >= len(previous.ghosts):
        point = current.ghost_point(index)
        return [point, point]

    return track(
        previous.ghost_point(index),
        previous.ghosts[index].position,
        current.ghosts[index].position,
        current.ghost_point(index),
    )


def _length(a: Point, b: Point) -> float:
    return abs(b[0] - a[0]) + abs(b[1] - a[1])


def point_along(points: list[Point], fraction: float) -> tuple[Point, Action | None]:
    """
    The point `fraction` of the way along a track, and the direction of the
    segment it lies on (None when the track has no length).
    """
    total = sum(_length(a, b) for a, b in zip(points, points[1:]))

    if total == 0:
        return points[-1], None

    remaining = min(max(fraction, 0.0), 1.0) * total
    direction = None

    for a, b in zip(points, points[1:]):
        length = _length(a, b)

        if length == 0:
            continue

        direction = _DIRECTIONS[(_sign(b[0] - a[0]), _sign(b[1] - a[1]))]

        if remaining <= length:
            share = remaining / length
            return (a[0] + (b[0] - a[0]) * share, a[1] + (b[1] - a[1]) * share), direction

        remaining -= length

    return points[-1], direction


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


def step_poses(
    pose: PlayerPose,
    points: list[Point],
    subframes: int = SUBFRAMES,
) -> list[PlayerPose]:
    """
    The poses of the in-between frames along one tick's track (see
    pacman_track); the last one is the pose at the new state.
    """
    poses = []
    previous_point = points[0]

    for index in range(1, subframes + 1):
        point, direction = point_along(points, index / subframes)

        if point != previous_point and direction is not None:
            pose = PlayerPose(facing=direction, chomp_step=pose.chomp_step + 1)

        poses.append(pose)
        previous_point = point

    return poses


def poses_for_states(states: list[SimulationState]) -> list[PlayerPose]:
    """The pose at every recorded state, for replay."""

    if not states:
        return []

    poses = [INITIAL_POSE]

    for previous, current in zip(states, states[1:]):
        poses.append(step_poses(poses[-1], pacman_track(previous, current))[-1])

    return poses


# Ghosts swap their hem every GHOST_FRAME_MS of wall-clock time, not per step:
# display only, so they keep moving during READY!, pauses and blocked steps.
GHOST_FRAME_MS = 160


def ghost_frame_at(milliseconds: int) -> int:
    return milliseconds // GHOST_FRAME_MS % GHOST_FRAMES


# A run that ends with CAUGHT_REASON (a ghost caught Pac-Man) plays the death sequence.
DEATH_FPS = 8


def ends_in_death(state: SimulationState) -> bool:
    return state.terminated and state.termination_reason == CAUGHT_REASON
