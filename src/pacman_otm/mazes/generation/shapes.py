"""
Region shapes: which tiles of the H x W grid belong to the maze at all.

A shape is a boolean mask. The maze's outer ring of the mask becomes wall and
everything outside becomes void, so only `playable_area(mask)` ever holds
corridors and every generated maze is enclosed by construction.
"""

from pathlib import Path
from typing import Any

import numpy as np

from pacman_otm.mazes.generation.errors import GenerationError
from pacman_otm.mazes.grid import components, walkable_mask
from pacman_otm.mazes.layout import load_layout
from pacman_otm.mazes.rules.structure import MIRROR_AXES, mirror_flips
from pacman_otm.mazes.tiles import Tile

MIRROR_CHOICES = ("none", *MIRROR_AXES)


def rectangle(height: int, width: int, rng: np.random.Generator) -> np.ndarray:
    return np.ones((height, width), dtype=bool)


def ellipse(height: int, width: int, rng: np.random.Generator) -> np.ndarray:
    """The largest axis-aligned ellipse that fits; symmetric on both axes."""

    rows = (np.arange(height) - (height - 1) / 2) / (height / 2)
    cols = (np.arange(width) - (width - 1) / 2) / (width / 2)

    return rows[:, None] ** 2 + cols[None, :] ** 2 <= 1.0


def blob(
    height: int,
    width: int,
    rng: np.random.Generator,
    fill: float = 0.6,
    mirror: str = "none",
) -> np.ndarray:
    """
    A seeded random connected shape: a random walk of overlapping discs from the
    centre until `fill` of the grid is covered, optionally mirrored, then one
    smoothing pass and the largest connected part.
    """
    if not 0.1 <= fill <= 0.95:
        raise GenerationError(f"shape.fill must be between 0.1 and 0.95, got {fill}.")

    if mirror not in MIRROR_CHOICES:
        raise GenerationError(
            f"shape.mirror must be one of {', '.join(MIRROR_CHOICES)}, got '{mirror}'."
        )

    radius = max(2, round(min(height, width) / 8))
    disc_rows, disc_cols = np.mgrid[-radius:radius + 1, -radius:radius + 1]
    disc = disc_rows**2 + disc_cols**2 <= radius**2

    mask = np.zeros((height, width), dtype=bool)
    padded = np.pad(mask, radius)
    centre = np.array([(height - 1) / 2, (width - 1) / 2])
    target = fill * height * width

    for _ in range(20 * height * width):
        row, col = np.rint(centre).astype(int)
        padded[row:row + 2 * radius + 1, col:col + 2 * radius + 1] |= disc

        covered = padded[radius:-radius, radius:-radius]

        # A mirrored blob is measured as it will end up, after mirroring.
        if (symmetrize(covered, mirror) if mirror != "none" else covered).sum() >= target:
            break

        # A step no longer than the radius keeps consecutive discs overlapping,
        # and clipping to the grid never lengthens a step, so the walk stays connected.
        angle = rng.uniform(0, 2 * np.pi)
        step = radius * np.array([np.sin(angle), np.cos(angle)])
        centre = np.clip(centre + step, [0, 0], [height - 1, width - 1])

    mask = padded[radius:-radius, radius:-radius].copy()

    if mirror != "none":
        mask = symmetrize(mask, mirror)

    mask = _smooth(mask)
    labels, count = components(mask)

    if count == 0:
        raise GenerationError("shape 'blob' came out empty; increase shape.fill.")

    sizes = np.bincount(labels.ravel())[1:]
    largest = labels == int(np.argmax(sizes)) + 1

    # The largest part may have an equally large mirror twin; keep both so the
    # shape stays symmetric (the generator then uses one symmetric part).
    if mirror != "none":
        largest = symmetrize(largest, mirror)

    return largest


def symmetrize(mask: np.ndarray, axis: str) -> np.ndarray:
    """The smallest superset of mask that is symmetric under the mirror(s) of axis."""

    result = mask.copy()

    # One flip at a time: flips commute, so after both the result is closed under the pair.
    if axis in ("horizontal", "both"):
        result = result | result[:, ::-1]
    if axis in ("vertical", "both"):
        result = result | result[::-1, :]

    return result


def layout(height: int, width: int, rng: np.random.Generator, path: str = "") -> np.ndarray:
    """The non-void tiles of a layout file; its size must match the maze size."""

    if not path:
        raise GenerationError("shape 'layout' needs shape.path, a .txt layout file.")

    maze = load_layout(Path(path))

    if (maze.height, maze.width) != (height, width):
        raise GenerationError(
            f"shape 'layout': '{path}' is {maze.height}x{maze.width}, "
            f"but the maze size is {height}x{width}."
        )

    return np.asarray(maze.topography) != Tile.VOID


SHAPES = frozendict(
    {
        "rectangle": rectangle,
        "ellipse": ellipse,
        "blob": blob,
        "layout": layout,
    }
)


def region_mask(
    kind: str,
    height: int,
    width: int,
    rng: np.random.Generator,
    **params: Any,
) -> np.ndarray:
    if kind not in SHAPES:
        raise GenerationError(
            f"Unknown shape '{kind}'; known shapes are {', '.join(SHAPES)}."
        )

    try:
        return SHAPES[kind](height, width, rng, **params)
    except TypeError as error:
        raise GenerationError(f"shape '{kind}': {error}") from error


def playable_area(mask: np.ndarray) -> np.ndarray:
    """The mask shrunk by one tile in all 8 directions; outside the grid counts as outside."""

    padded = np.pad(mask, 1, constant_values=False)
    height, width = mask.shape
    result = np.ones(mask.shape, dtype=bool)

    for d_row in (-1, 0, 1):
        for d_col in (-1, 0, 1):
            result &= padded[1 + d_row:1 + d_row + height, 1 + d_col:1 + d_col + width]

    return result


def frame_grid(mask: np.ndarray) -> np.ndarray:
    """Void outside the mask, wall inside it: the canvas a generator carves corridors into."""

    grid = np.full(mask.shape, Tile.VOID, dtype=np.uint8)
    grid[mask] = Tile.WALL
    return grid


def trim_outer_wall(grid: np.ndarray) -> np.ndarray:
    """
    Turn into void the wall that touches no corridor (not even diagonally) and
    is connected to the outside. That wall is never drawn: only outlines next to
    open tiles are. Removing it makes the maze's outline follow its corridors,
    so a ragged or curved shape edge the corridors cannot reach is not mistaken
    for a thick wall. Every corridor keeps its wall ring, so `enclosed` still
    holds, and wall inside the maze is kept for max_block(wall) to judge.
    """
    walkable = walkable_mask(grid)
    near_corridor = np.zeros(grid.shape, dtype=bool)
    padded = np.pad(walkable, 1, constant_values=False)
    height, width = grid.shape

    for d_row in (-1, 0, 1):
        for d_col in (-1, 0, 1):
            near_corridor |= padded[1 + d_row:1 + d_row + height, 1 + d_col:1 + d_col + width]

    hidden = (grid == Tile.WALL) & ~near_corridor
    outside = np.pad(grid == Tile.VOID, 1, constant_values=True)
    trimmed = np.zeros(grid.shape, dtype=bool)

    # Flood from the outside through hidden wall, 4-connected.
    while True:
        touching = outside[:-2, 1:-1] | outside[2:, 1:-1] | outside[1:-1, :-2] | outside[1:-1, 2:]
        grown = hidden & touching & ~trimmed

        if not grown.any():
            break

        trimmed |= grown
        outside[1:-1, 1:-1] |= grown

    result = grid.copy()
    result[trimmed] = Tile.VOID
    return result


def _smooth(mask: np.ndarray) -> np.ndarray:
    """One majority pass over the 3x3 neighbourhood: removes spikes and pinholes."""

    padded = np.pad(mask, 1, constant_values=False).astype(np.int8)
    height, width = mask.shape
    total = sum(
        padded[1 + d_row:1 + d_row + height, 1 + d_col:1 + d_col + width]
        for d_row in (-1, 0, 1)
        for d_col in (-1, 0, 1)
    )
    return total >= 5
