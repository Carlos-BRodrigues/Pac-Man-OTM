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
    # Ghosts only: they start in the house and leave through the gate, one way.
    GHOST_HOUSE = 3
    GHOST_GATE = 4
    # 5 is reserved for TUNNEL.


@dataclass(frozen=True)
class TileRules:
    pacman_walkable: bool
    pellet_allowed: bool
    # None: ghosts cannot walk here. Otherwise a ghost may step onto a tile of equal or higher
    # rank only: the house (0) leads out through the gate (1) to the corridors (2), never back.
    ghost_rank: int | None = None

    @property
    def ghost_walkable(self) -> bool:
        return self.ghost_rank is not None


TILE_RULES: frozendict[Tile, TileRules] = frozendict(
    {
        Tile.CORRIDOR: TileRules(pacman_walkable=True, pellet_allowed=True, ghost_rank=2),
        Tile.WALL: TileRules(pacman_walkable=False, pellet_allowed=False),
        Tile.VOID: TileRules(pacman_walkable=False, pellet_allowed=False),
        Tile.GHOST_HOUSE: TileRules(pacman_walkable=False, pellet_allowed=False, ghost_rank=0),
        Tile.GHOST_GATE: TileRules(pacman_walkable=False, pellet_allowed=False, ghost_rank=1),
    }
)
