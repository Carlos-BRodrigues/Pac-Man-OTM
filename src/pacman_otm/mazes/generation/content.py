"""
Content placers: where Pac-Man starts and where the pellets are, given a
finished tile grid. Placers never change tiles, and the start never gets a
pellet (as with 'P' in layouts). Later, ghost spawns use the same interface.

Start placers:  (grid, rng, **params) -> Position
Pellet placers: (grid, start, rng, **params) -> set[Position]
"""

from collections import deque
from pathlib import Path

import numpy as np

from pacman_otm.mazes.generation.errors import GenerationError
from pacman_otm.mazes.grid import Position, positions, walkable_mask
from pacman_otm.mazes.layout import load_layout


def _walkable(grid: np.ndarray) -> list[Position]:
    tiles = list(positions(walkable_mask(grid)))

    if not tiles:
        raise GenerationError("The maze has no walkable tile to place content on.")

    return tiles


def _nearest(tiles: list[Position], point: tuple[float, float]) -> Position:
    """The tile closest to point; ties go to the lowest (row, col)."""
    return min(tiles, key=lambda tile: ((tile[0] - point[0]) ** 2 + (tile[1] - point[1]) ** 2, tile))


# Start placers


def start_center(grid: np.ndarray, rng: np.random.Generator) -> Position:
    """The walkable tile closest to the centre of the grid."""
    height, width = grid.shape
    return _nearest(_walkable(grid), ((height - 1) / 2, (width - 1) / 2))


def start_random(grid: np.ndarray, rng: np.random.Generator) -> Position:
    tiles = _walkable(grid)
    return tiles[int(rng.integers(len(tiles)))]


def start_layout(grid: np.ndarray, rng: np.random.Generator, path: str = "") -> Position:
    """The walkable tile closest to the 'P' of a layout file (shape 'layout' supplies the path)."""

    if not path:
        raise GenerationError(
            "content.start: placer 'layout' needs content.start.path or a shape of kind 'layout'."
        )

    return _nearest(_walkable(grid), load_layout(Path(path)).pacman_start)


START_PLACERS = frozendict(
    {
        "center": start_center,
        "random": start_random,
        "layout": start_layout,
    }
)


# Pellet placers


def pellets_all_corridors(grid: np.ndarray, start: Position, rng: np.random.Generator) -> set[Position]:
    return set(_walkable(grid)) - {start}


def pellets_density(grid: np.ndarray, start: Position, rng: np.random.Generator, p: float = 0.5) -> set[Position]:
    """Each walkable tile (except the start) holds a pellet with probability p."""

    if not 0.0 < p <= 1.0:
        raise GenerationError(f"content.pellets.p must be in (0, 1], got {p}.")

    tiles = [tile for tile in _walkable(grid) if tile != start]
    keep = rng.random(len(tiles)) < p
    return {tile for tile, kept in zip(tiles, keep) if kept}


def pellets_exclude_near_start(
    grid: np.ndarray,
    start: Position,
    rng: np.random.Generator,
    distance: int = 3,
) -> set[Position]:
    """Every walkable tile more than `distance` steps (BFS) from the start."""

    if distance < 0:
        raise GenerationError(f"content.pellets.distance must be >= 0, got {distance}.")

    steps = _bfs_steps(walkable_mask(grid), start)
    return {tile for tile, step in steps.items() if step > distance}


def _bfs_steps(walkable: np.ndarray, start: Position) -> dict[Position, int]:
    height, width = walkable.shape
    steps = {start: 0}
    frontier = deque([start])

    while frontier:
        row, col = frontier.popleft()

        for neighbour in ((row - 1, col), (row, col - 1), (row + 1, col), (row, col + 1)):
            n_row, n_col = neighbour

            if 0 <= n_row < height and 0 <= n_col < width and walkable[neighbour] and neighbour not in steps:
                steps[neighbour] = steps[(row, col)] + 1
                frontier.append(neighbour)

    return steps


PELLET_PLACERS = frozendict(
    {
        "all_corridors": pellets_all_corridors,
        "density": pellets_density,
        "exclude_near_start": pellets_exclude_near_start,
    }
)
