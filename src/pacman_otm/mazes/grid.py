"""
Pure numpy helpers on a tile grid. Rules, analysis and generators share these;
nothing here knows about Maze, pellets or the start.
"""

from collections import deque
from typing import Literal

import numpy as np

from pacman_otm.mazes.tiles import TILE_RULES, Tile

Position = tuple[int, int]

# Bounds for both rows and columns, enforced for every maze.
MIN_MAZE_SIZE = 5
MAX_MAZE_SIZE = 101

TileKind = Literal["corridor", "wall", "void"]
TILE_KINDS: tuple[TileKind, ...] = ("corridor", "wall", "void")

_WALKABLE_TILES = tuple(
    int(tile) for tile, rules in TILE_RULES.items() if rules.pacman_walkable
)


def walkable_mask(grid: np.ndarray) -> np.ndarray:
    """Tiles Pac-Man can walk on, decided by TILE_RULES."""
    return np.isin(grid, _WALKABLE_TILES)


def tile_mask(grid: np.ndarray, kind: TileKind) -> np.ndarray:
    """'corridor' means walkable; 'wall' and 'void' are those exact tiles."""

    if kind == "corridor":
        return walkable_mask(grid)

    if kind == "wall":
        return grid == Tile.WALL

    if kind == "void":
        return grid == Tile.VOID

    raise ValueError(f"Unknown tile kind '{kind}'; expected one of {', '.join(TILE_KINDS)}.")


def neighbour_counts(mask: np.ndarray) -> np.ndarray:
    """For every cell, how many of its 4 neighbours are set. Outside the grid counts as unset."""

    padded = np.pad(mask, 1, constant_values=False).astype(np.int8)

    return (
        padded[:-2, 1:-1]
        + padded[2:, 1:-1]
        + padded[1:-1, :-2]
        + padded[1:-1, 2:]
    )


def windows(mask: np.ndarray, size: int) -> np.ndarray:
    """
    Boolean array of top-left corners whose size x size window is entirely set.
    Shape (H - size + 1, W - size + 1); empty if the window does not fit.
    A summed-area table makes this O(H*W) for any size.
    """
    if size < 1:
        raise ValueError(f"Window size must be >= 1, got {size}.")

    height, width = mask.shape

    if size > height or size > width:
        return np.zeros((0, 0), dtype=bool)

    table = np.zeros((height + 1, width + 1), dtype=np.int32)
    table[1:, 1:] = mask.astype(np.int32).cumsum(axis=0).cumsum(axis=1)

    total = (
        table[size:, size:]
        - table[:-size, size:]
        - table[size:, :-size]
        + table[:-size, :-size]
    )

    return total == size * size


def components(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """
    4-connected components of the set cells. Returns (labels, count): labels
    are 1..count for set cells, 0 elsewhere, numbered in row-major order of
    each component's first cell.
    """
    labels = np.zeros(mask.shape, dtype=np.int32)
    height, width = mask.shape
    count = 0

    for row, col in zip(*np.nonzero(mask)):
        if labels[row, col]:
            continue

        count += 1
        labels[row, col] = count
        frontier = deque([(int(row), int(col))])

        while frontier:
            r, c = frontier.popleft()

            for nr, nc in ((r - 1, c), (r, c - 1), (r + 1, c), (r, c + 1)):
                if 0 <= nr < height and 0 <= nc < width and mask[nr, nc] and not labels[nr, nc]:
                    labels[nr, nc] = count
                    frontier.append((nr, nc))

    return labels, count


def edge_count(mask: np.ndarray) -> int:
    """Number of 4-adjacent pairs of set cells."""

    horizontal = mask[:, :-1] & mask[:, 1:]
    vertical = mask[:-1, :] & mask[1:, :]

    return int(horizontal.sum() + vertical.sum())


def positions(mask: np.ndarray) -> tuple[Position, ...]:
    """Set cells as (row, col) tuples in row-major order."""
    return tuple((int(row), int(col)) for row, col in zip(*np.nonzero(mask)))


def dead_end_mask(mask: np.ndarray) -> np.ndarray:
    """Set cells with exactly one set neighbour."""
    return mask & (neighbour_counts(mask) == 1)


def junction_mask(mask: np.ndarray) -> np.ndarray:
    """Set cells with three or more set neighbours: places where there is a choice."""
    return mask & (neighbour_counts(mask) >= 3)


def straight_runs(mask: np.ndarray) -> list[tuple[Position, ...]]:
    """
    Straight stretches with no choice: maximal row and column segments of set
    cells, split at junctions. A junction ends one run and starts the next, so
    it belongs to both. Runs of a single cell are left out.
    """
    junctions = junction_mask(mask)
    runs: list[tuple[Position, ...]] = []

    for transposed in (False, True):
        lines = mask.T if transposed else mask
        line_junctions = junctions.T if transposed else junctions

        for index in range(lines.shape[0]):
            line = lines[index]
            is_junction = line_junctions[index]
            current: list[int] = []

            # A trailing False flushes the last segment.
            for offset, is_set in enumerate([*line.tolist(), False]):
                if not is_set:
                    if len(current) >= 2:
                        runs.append(_line_positions(index, current, transposed))
                    current = []
                    continue

                current.append(offset)

                if is_junction[offset] and len(current) >= 2:
                    runs.append(_line_positions(index, current, transposed))
                    current = [offset]

    return runs


def _line_positions(index: int, offsets: list[int], transposed: bool) -> tuple[Position, ...]:
    if transposed:
        return tuple((offset, index) for offset in offsets)
    return tuple((index, offset) for offset in offsets)


def corridor_chains(mask: np.ndarray) -> list[tuple[Position, ...]]:
    """
    Choice-free corridors, turns included: connected groups of cells with
    exactly two set neighbours, each extended by the junction or dead end at
    either end. A ring with no junction is returned whole. Cells are listed in
    no particular order.
    """
    counts = neighbour_counts(mask)
    chain = mask & (counts == 2)
    labels, count = components(chain)
    height, width = mask.shape

    groups: list[list[Position]] = [[] for _ in range(count)]

    for row, col in zip(*np.nonzero(chain)):
        groups[labels[row, col] - 1].append((int(row), int(col)))

    chains = []

    for group in groups:
        ends: list[Position] = []

        for row, col in group:
            for neighbour in ((row - 1, col), (row, col - 1), (row + 1, col), (row, col + 1)):
                n_row, n_col = neighbour
                if (
                    0 <= n_row < height
                    and 0 <= n_col < width
                    and mask[neighbour]
                    and not chain[neighbour]
                ):
                    # A loop from a junction back to itself walks that junction twice.
                    ends.append(neighbour)

        chains.append(tuple(group + ends))

    return chains
