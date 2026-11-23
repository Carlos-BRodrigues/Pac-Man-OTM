"""Rules decided by small windows of tiles; each failure has a position."""

from dataclasses import dataclass

import numpy as np

from pacman_otm.mazes.grid import TILE_KINDS, TileKind, positions, tile_mask, walkable_mask, windows
from pacman_otm.mazes.rules.base import Position, Rule, Violation
from pacman_otm.mazes.tiles import Tile


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
class MinWallThickness(Rule):
    """
    Every wall tile lies inside some size x size square with no corridor in it,
    so no wall is thinner than `size` between corridors. size 2 forbids the
    one-tile walls the arcade maze never has.

    Void, the outside of the grid and the decorative ghost-house tiles count
    as part of such a square: a maze's outer border and a ghost-house wall may
    be one tile thick, as in the arcade maze.
    """

    name = "min_wall_thickness"

    size: int

    def __post_init__(self) -> None:
        if self.size < 2:
            raise ValueError(f"size must be >= 2, got {self.size}.")

    def violations(self, grid: np.ndarray) -> list[Violation]:
        thin = (grid == Tile.WALL) & ~self._covered(grid)

        if not thin.any():
            return []

        return [
            self._violation(
                f"{int(thin.sum())} wall tile(s) thinner than {self.size} between corridors",
                positions(thin),
            )
        ]

    def holds_after_change(self, grid: np.ndarray, position: Position) -> bool:
        # A change affects the squares containing it, and so the coverage of wall
        # tiles up to size - 1 away; those squares reach 2 * (size - 1) away.
        reach = self.size - 1
        solid = self._solid(grid)
        row, col = position[0] + reach, position[1] + reach  # in padded coordinates
        top, left = max(row - 2 * reach, 0), max(col - 2 * reach, 0)
        local = solid[top:row + 2 * reach + 1, left:col + 2 * reach + 1]
        covered = self._coverage(local)

        walls = np.pad(grid == Tile.WALL, reach, constant_values=False)
        near = (slice(max(row - reach, 0), row + reach + 1), slice(max(col - reach, 0), col + reach + 1))
        local_near = (
            slice(near[0].start - top, near[0].stop - top),
            slice(near[1].start - left, near[1].stop - left),
        )

        return not (walls[near] & ~covered[local_near]).any()

    def _solid(self, grid: np.ndarray) -> np.ndarray:
        """Everything that is not corridor, with the outside of the grid as solid padding."""
        return np.pad(~walkable_mask(grid), self.size - 1, constant_values=True)

    def _covered(self, grid: np.ndarray) -> np.ndarray:
        reach = self.size - 1
        covered = self._coverage(self._solid(grid))
        return covered[reach:reach + grid.shape[0], reach:reach + grid.shape[1]]

    def _coverage(self, solid: np.ndarray) -> np.ndarray:
        """Cells of `solid` that lie in at least one all-solid size x size square."""

        corners = windows(solid, self.size)
        covered = np.zeros(solid.shape, dtype=bool)

        for d_row in range(self.size):
            for d_col in range(self.size):
                covered[d_row:d_row + corners.shape[0], d_col:d_col + corners.shape[1]] |= corners

        return covered


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
