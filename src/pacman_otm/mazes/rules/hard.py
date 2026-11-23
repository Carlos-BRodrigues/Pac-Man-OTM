"""Rules every generated maze must meet."""

from dataclasses import dataclass

import numpy as np

from pacman_otm.mazes.grid import (
    MAX_MAZE_SIZE,
    MIN_MAZE_SIZE,
    components,
    positions,
    walkable_mask,
)
from pacman_otm.mazes.rules.base import Rule, RuleSet, Violation
from pacman_otm.mazes.tiles import Tile


@dataclass(frozen=True)
class SizeBounds(Rule):
    name = "size_bounds"

    def violations(self, grid: np.ndarray) -> list[Violation]:
        height, width = grid.shape

        if MIN_MAZE_SIZE <= height <= MAX_MAZE_SIZE and MIN_MAZE_SIZE <= width <= MAX_MAZE_SIZE:
            return []

        return [
            self._violation(
                f"size {height}x{width} is outside {MIN_MAZE_SIZE}..{MAX_MAZE_SIZE} "
                f"for rows and columns"
            )
        ]


@dataclass(frozen=True)
class Connected(Rule):
    """One walkable region. Positions are the tiles outside the largest one."""

    name = "connected"

    def violations(self, grid: np.ndarray) -> list[Violation]:
        labels, count = components(walkable_mask(grid))

        if count == 0:
            return [self._violation("no walkable tiles")]

        if count == 1:
            return []

        sizes = np.bincount(labels.ravel())[1:]
        largest = int(np.argmax(sizes)) + 1
        stray = (labels != 0) & (labels != largest)

        return [
            self._violation(
                f"{count} separate walkable regions; {int(stray.sum())} tile(s) "
                f"outside the largest",
                positions(stray),
            )
        ]


@dataclass(frozen=True)
class Enclosed(Rule):
    """No walkable tile 8-adjacent to void or the grid edge: every maze has wall borders."""

    name = "enclosed"

    def violations(self, grid: np.ndarray) -> list[Violation]:
        # Outside the grid counts as void.
        outside = np.pad(grid == Tile.VOID, 1, constant_values=True)
        height, width = grid.shape
        near_outside = np.zeros(grid.shape, dtype=bool)

        for d_row in (-1, 0, 1):
            for d_col in (-1, 0, 1):
                near_outside |= outside[
                    1 + d_row:1 + d_row + height,
                    1 + d_col:1 + d_col + width,
                ]

        exposed = walkable_mask(grid) & near_outside

        if not exposed.any():
            return []

        return [
            self._violation(
                f"{int(exposed.sum())} walkable tile(s) touch void or the grid edge",
                positions(exposed),
            )
        ]


HARD_RULES = RuleSet([SizeBounds(), Connected(), Enclosed()])
