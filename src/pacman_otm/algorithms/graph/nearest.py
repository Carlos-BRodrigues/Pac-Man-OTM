"""Projecting a point that is not a corridor (a wall, the void, off the grid) onto the closest corridor tile."""

import numpy as np

from pacman_otm.mazes.maze import Maze

Position = tuple[int, int]


class NearestTile:
    """
    The walkable (corridor) tile with the smallest squared Euclidean distance to
    any integer point, on or off the grid; ties go to the first tile in reading
    order. A corridor tile projects onto itself.

    Corridor tiles, not every tile a ghost may walk: a ghost outside the house
    can never go back in, so a target inside it would be unreachable.
    Results are cached per point (targets repeat from tick to tick).
    """

    def __init__(self, maze: Maze) -> None:
        self.maze = maze
        # np.nonzero walks the grid row by row: index order is reading order, which argmin keeps on ties.
        rows, cols = np.nonzero(maze.walkable_mask)
        self._rows = rows.astype(np.int64)
        self._cols = cols.astype(np.int64)
        self._cache: dict[Position, Position] = {}

    def __call__(self, point: Position) -> Position:
        cached = self._cache.get(point)

        if cached is None:
            if self.maze.is_walkable(point):
                cached = point
            else:
                row, col = point
                distances = (self._rows - row) ** 2 + (self._cols - col) ** 2
                index = int(np.argmin(distances))
                cached = (int(self._rows[index]), int(self._cols[index]))

            self._cache[point] = cached

        return cached
