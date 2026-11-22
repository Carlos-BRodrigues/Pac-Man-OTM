"""
Player animation derived from recorded positions only.

The chomp loop advances once per drawn in-between frame while the player moves,
a little more than one loop per tile. When the player does not
move (blocked by a wall) the pose freezes. Facing is the direction of the last
successful move. Nothing here calls a controller or the engine, so live play and
replay produce the same poses.
"""

from dataclasses import dataclass

from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.state import SimulationState
from pacman_otm.visualization.sprites import Mouth

Position = tuple[int, int]

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


def step_poses(
    pose: PlayerPose,
    previous: Position,
    current: Position,
    subframes: int = SUBFRAMES,
) -> list[PlayerPose]:
    """
    The poses of the in-between frames from one state to the next; the last
    one is the pose at the new state.
    """
    direction = move_direction(previous, current)

    if direction is None:
        return [pose] * subframes

    return [
        PlayerPose(facing=direction, chomp_step=pose.chomp_step + index)
        for index in range(1, subframes + 1)
    ]


def poses_for_states(states: list[SimulationState]) -> list[PlayerPose]:
    """The pose at every recorded state, for replay."""

    if not states:
        return []

    poses = [INITIAL_POSE]

    for previous, current in zip(states, states[1:]):
        poses.append(
            step_poses(poses[-1], previous.pacman_position, current.pacman_position)[-1]
        )

    return poses


# A run that ends this way plays the death sequence. No rule produces it yet;
# it is reserved for ghosts.
CAUGHT_REASON = "caught"

DEATH_FPS = 8


def ends_in_death(state: SimulationState) -> bool:
    return state.terminated and state.termination_reason == CAUGHT_REASON
