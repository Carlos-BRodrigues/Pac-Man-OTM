"""
The tile set. Tile values are stored in saved results, so they never change;
behaviour comes from TILE_RULES, never from comparing against raw numbers.
"""

from dataclasses import dataclass
from enum import IntEnum


class Tile(IntEnum):
    CORRIDOR = 0
    WALL = 1
    # Padding that makes a non-rectangular maze rectangular; drawn as background.
    VOID = 2
    # Decorative only: no gate logic.
    GHOST_HOUSE = 3
    GHOST_GATE = 4
    # 5 is reserved for TUNNEL.


@dataclass(frozen=True)
class TileRules:
    pacman_walkable: bool
    pellet_allowed: bool


TILE_RULES: frozendict[Tile, TileRules] = frozendict(
    {
        Tile.CORRIDOR: TileRules(pacman_walkable=True, pellet_allowed=True),
        Tile.WALL: TileRules(pacman_walkable=False, pellet_allowed=False),
        Tile.VOID: TileRules(pacman_walkable=False, pellet_allowed=False),
        Tile.GHOST_HOUSE: TileRules(pacman_walkable=False, pellet_allowed=False),
        Tile.GHOST_GATE: TileRules(pacman_walkable=False, pellet_allowed=False),
    }
)
