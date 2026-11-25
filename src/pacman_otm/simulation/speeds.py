"""
Movement speeds. Time runs in ticks; a move from one tile to the next costs
`move_cost` units of progress, and every tick a moving mover gains its speed.
The leftover after arriving carries into the next tile, so fractional speeds
average out exactly, in whole numbers (deterministic, no float drift).

With the defaults Pac-Man moves one tile per tick, a ghost 15/16 of that, and
every pellet Pac-Man eats costs him `pellet_pause` units (2/16 of a tile), so in
a corridor full of dots he moves at 16/18 of his speed, slower than a ghost.
"""

from dataclasses import asdict, dataclass
from typing import Any

from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.actions import Action

Position = tuple[int, int]


@dataclass(frozen=True)
class SpeedRules:
    move_cost: int = 16
    pacman: int = 16
    ghost: int = 15
    pellet_pause: int = 2

    def __post_init__(self) -> None:
        if self.move_cost < 2:
            raise ValueError(f"move_cost must be at least 2, got {self.move_cost}.")

        for name in ("pacman", "ghost"):
            speed = getattr(self, name)

            # One decision per tile: no mover may cross two tiles in one tick.
            if not 1 <= speed <= self.move_cost:
                raise ValueError(f"Speed '{name}' must be between 1 and move_cost ({self.move_cost}), got {speed}.")

        if self.pellet_pause < 0:
            raise ValueError(f"pellet_pause must be >= 0, got {self.pellet_pause}.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SpeedRules":
        return cls(**data)


# The arcade's level-1 ratios: ghosts at 15/16 of Pac-Man, Pac-Man slowed by dots.
ARCADE = SpeedRules()
# Everyone at one tile per tick and no pellet pause: the game before speeds existed.
EQUAL = SpeedRules(ghost=16, pellet_pause=0)
# Ghosts at 15/16 as in the arcade, but eating costs nothing: Pac-Man always outruns a ghost.
EASY = SpeedRules(pellet_pause=0)

SPEED_PRESETS: frozendict[str, SpeedRules] = frozendict({"easy": EASY, "arcade": ARCADE, "equal": EQUAL})
# What the CLI uses without --speeds. The engine and experiment runner keep ARCADE as their own default.
DEFAULT_SPEEDS = "easy"


def mover_point(
    position: Position,
    heading: Action | None,
    progress: int,
    move_cost: int,
) -> tuple[float, float]:
    """
    Where a mover is, in fractional tiles: its tile, moved `progress` along its
    heading. Negative progress (a pellet pause) and no heading mean the tile centre.
    Never wrapped: in a tunnel mouth the point runs off the grid (e.g. column -0.4),
    which is what drawing needs.
    """
    if heading is None or progress <= 0:
        return float(position[0]), float(position[1])

    d_row, d_col = Maze.MOVEMENTS[heading]
    fraction = progress / move_cost
    return position[0] + d_row * fraction, position[1] + d_col * fraction


def occupied_tile(
    position: Position,
    heading: Action | None,
    progress: int,
    move_cost: int,
    maze: Maze | None = None,
) -> Position:
    """
    The tile a mover counts as being on: its destination once it is halfway there.
    With the maze, a destination through a tunnel is the tile on the other side.
    """

    if heading is None or 2 * progress < move_cost:
        return position

    if maze is not None:
        return maze.get_destination(position, heading)

    d_row, d_col = Maze.MOVEMENTS[heading]
    return position[0] + d_row, position[1] + d_col
