"""
Content placers: where Pac-Man starts, where the pellets are and where the
ghosts spawn, given a finished tile grid. Placers never change tiles, and the
start never gets a pellet (as with 'P' in layouts). Spawns ignore pellets: a
spawn may hold one, and the number of ghosts never changes the pellets.

Start placers:  (grid, rng, **params) -> Position
Pellet placers: (grid, start, rng, **params) -> set[Position]
Ghost placers:  (grid, start, rng, **params) -> list[Position]  (ghost i starts on spawn i)
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


def clear_center_box(height: int, width: int, size: int = 0) -> tuple[int, int, int, int]:
    """
    (top, left, rows, cols) of the pellet-free box: `size` tiles across (0: a
    third of the shorter side, at least 3), adjusted per axis to the parity of
    that axis so the box sits exactly on the centre: 9x10 on a 31x28 grid.
    """
    target = size if size > 0 else max(3, round(min(height, width) / 3))

    def fit(dimension: int) -> int:
        cells = target if target % 2 == dimension % 2 else target + 1
        return min(cells, dimension)

    rows, cols = fit(height), fit(width)
    return (height - rows) // 2, (width - cols) // 2, rows, cols


def pellets_clear_center(
    grid: np.ndarray,
    start: Position,
    rng: np.random.Generator,
    size: int = 0,
) -> set[Position]:
    """
    Every walkable tile except a box centred on the grid, so a start near the
    centre is not surrounded by pellets. `size`: the box's width in tiles
    (0: automatic, a third of the shorter side, e.g. 9 on a classic-sized maze).
    """
    if size < 0:
        raise GenerationError(f"content.pellets.size must be >= 0 (0: automatic), got {size}.")

    top, left, rows, cols = clear_center_box(*grid.shape, size=size)
    pellets = {
        (row, col)
        for row, col in _walkable(grid)
        if not (top <= row < top + rows and left <= col < left + cols)
    } - {start}

    if not pellets:
        raise GenerationError(
            f"content.pellets: the clear centre ({rows}x{cols}) leaves no pellet; lower content.pellets.size."
        )

    return pellets


PELLET_PLACERS = frozendict(
    {
        "clear_center": pellets_clear_center,
        "all_corridors": pellets_all_corridors,
        "density": pellets_density,
        "exclude_near_start": pellets_exclude_near_start,
    }
)


# Ghost spawn placers


DEFAULT_GHOST_MIN_DISTANCE = 10


def ghosts_random(
    grid: np.ndarray,
    start: Position,
    rng: np.random.Generator,
    count: int = 0,
    min_distance: int = DEFAULT_GHOST_MIN_DISTANCE,
) -> list[Position]:
    """`count` distinct spawns at least `min_distance` steps (BFS) from the start."""
    return place_ghost_spawns(grid, start, rng, count=count, min_distance=min_distance)


def place_ghost_spawns(
    grid: np.ndarray,
    start: Position,
    rng: np.random.Generator,
    count: int,
    min_distance: int = DEFAULT_GHOST_MIN_DISTANCE,
    fixed: tuple[Position, ...] = (),
) -> list[Position]:
    """
    `count` distinct spawns at least `min_distance` steps (BFS) from the start.

    `fixed` spawns (a layout's G tiles) come first, as given. The others are a
    seeded shuffle of the eligible tiles, taken in order, so a larger count only
    adds spawns: the first ones stay where they are.
    """
    if count < 0:
        raise GenerationError(f"content.ghosts.count must be >= 0, got {count}.")

    if min_distance < 1:
        raise GenerationError(f"content.ghosts.min_distance must be >= 1, got {min_distance}.")

    fixed = [tuple(position) for position in fixed]

    if count <= len(fixed):
        return fixed[:count]

    steps = _bfs_steps(walkable_mask(grid), start)
    eligible = sorted(tile for tile, step in steps.items() if step >= min_distance and tile not in fixed)
    needed = count - len(fixed)

    if len(eligible) < needed:
        raise GenerationError(
            f"content.ghosts: {count} ghost spawn(s) need {needed} free tile(s) at least {min_distance} steps "
            f"from the start, but only {len(eligible)} exist; lower content.ghosts.count or "
            f"content.ghosts.min_distance (--maze-set content.ghosts.min_distance=N), or use --ghosts 0."
        )

    order = rng.permutation(len(eligible))
    return fixed + [eligible[int(index)] for index in order[:needed]]


GHOST_PLACERS = frozendict(
    {
        "random": ghosts_random,
    }
)
