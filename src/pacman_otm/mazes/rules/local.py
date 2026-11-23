"""Rules decided by small windows of tiles; each failure has a position."""

from dataclasses import dataclass

import numpy as np

from pacman_otm.mazes.grid import TILE_KINDS, TileKind, positions, tile_mask, walkable_mask, windows
from pacman_otm.mazes.rules.base import Position, Rule, Violation


def _neighbourhood(grid: np.ndarray, position: Position, radius: int) -> np.ndarray:
    """The part of the grid within `radius` of position (clipped at the edges)."""
    row, col = position
    return grid[max(row - radius, 0):row + radius + 1, max(col - radius, 0):col + radius + 1]


@dataclass(frozen=True)
class MaxBlock(Rule):
    """
    No size x size window made entirely of one tile kind.
    max_block(corridor, 2) means one-tile-wide corridors; max_block(wall, k)
    keeps every wall thinner than k.
    """

    name = "max_block"

    tile: TileKind
    size: int

    def __post_init__(self) -> None:
        if self.tile not in TILE_KINDS:
            raise ValueError(f"tile must be one of {', '.join(TILE_KINDS)}, got '{self.tile}'.")

        if self.size < 2:
            raise ValueError(f"size must be >= 2, got {self.size}.")

    def violations(self, grid: np.ndarray) -> list[Violation]:
        corners = windows(tile_mask(grid, self.tile), self.size)

        if not corners.any():
            return []

        return [
            self._violation(
                f"{int(corners.sum())} {self.size}x{self.size} block(s) of {self.tile} "
                f"(positions are top-left corners)",
                positions(corners),
            )
        ]

    def holds_after_change(self, grid: np.ndarray, position: Position) -> bool:
        # Only windows containing the changed tile can have changed.
        local = _neighbourhood(grid, position, self.size - 1)
        return not windows(tile_mask(local, self.tile), self.size).any()


@dataclass(frozen=True)
class NoDiagonalContact(Rule):
    """No two walkable tiles that touch only at a corner (a checkerboard 2x2 window)."""

    name = "no_diagonal_contact"

    def violations(self, grid: np.ndarray) -> list[Violation]:
        corners = self._checkerboards(walkable_mask(grid))

        if not corners.any():
            return []

        return [
            self._violation(
                f"{int(corners.sum())} diagonal-only contact(s) "
                f"(positions are top-left corners of the 2x2 window)",
                positions(corners),
            )
        ]

    def holds_after_change(self, grid: np.ndarray, position: Position) -> bool:
        return not self._checkerboards(walkable_mask(_neighbourhood(grid, position, 1))).any()

    @staticmethod
    def _checkerboards(mask: np.ndarray) -> np.ndarray:
        top_left, top_right = mask[:-1, :-1], mask[:-1, 1:]
        bottom_left, bottom_right = mask[1:, :-1], mask[1:, 1:]

        main = top_left & bottom_right & ~top_right & ~bottom_left
        anti = top_right & bottom_left & ~top_left & ~bottom_right

        return main | anti
