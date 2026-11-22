"""
The static maze picture, built once per maze.

Walls are drawn as thin outlines that keep `wall_recess` pixels away from every
open tile, with rounded corners. Lines only appear where a wall faces an open
tile, so there is no line along the edge of the grid or next to void.
"""

import numpy as np
import pygame

from pacman_otm.mazes.maze import Maze
from pacman_otm.mazes.tiles import Tile
from pacman_otm.visualization.theme import Theme

# Ghost-house tiles are not walkable, but they are drawn as an open interior.
DRAWN_OPEN_TILES = (Tile.GHOST_HOUSE, Tile.GHOST_GATE)


def disc_offsets(radius: int) -> list[tuple[int, int]]:
    return [
        (dy, dx)
        for dy in range(-radius, radius + 1)
        for dx in range(-radius, radius + 1)
        if dy * dy + dx * dx <= radius * radius
    ]


def dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    """Pixels within `radius` (a disc) of a True pixel. Outside the array counts as False."""

    if radius <= 0:
        return mask.copy()

    height, width = mask.shape
    padded = np.pad(mask, radius, constant_values=False)
    result = np.zeros_like(mask)

    for dy, dx in disc_offsets(radius):
        result |= padded[radius + dy:radius + dy + height, radius + dx:radius + dx + width]

    return result


def erode(mask: np.ndarray, radius: int) -> np.ndarray:
    """Pixels whose whole disc is True. Outside the array counts as True."""
    return ~dilate(~mask, radius)


def open_pixel_mask(maze: Maze, theme: Theme) -> np.ndarray:
    """Base-pixel mask of everything drawn as open space."""

    open_tiles = maze.walkable_mask | np.isin(maze.topography, DRAWN_OPEN_TILES)
    block = np.ones((theme.tile, theme.tile), dtype=bool)
    return np.kron(open_tiles, block).astype(bool)


def wall_outline_mask(maze: Maze, theme: Theme) -> np.ndarray:
    """Base-pixel mask of the wall outlines."""

    open_pixels = open_pixel_mask(maze, theme)

    # Pad with wall so shapes continue past the grid edge and get no line there.
    margin = theme.wall_recess + theme.corner_radius + 2
    open_padded = np.pad(open_pixels, margin, constant_values=False)

    body = ~dilate(open_padded, theme.wall_recess)
    # Round the outward corners (an opening). An opening also deletes shapes thinner
    # than the radius, such as a one-tile wall, so parts far from any rounded shape
    # are kept as they were.
    rounded = dilate(erode(body, theme.corner_radius), theme.corner_radius)
    thin = body & ~dilate(rounded, theme.corner_radius)
    body = rounded | thin

    outline = body & ~erode(body, 1)

    return outline[margin:-margin, margin:-margin]


def gate_bar_mask(maze: Maze, theme: Theme) -> np.ndarray:
    mask = np.zeros((maze.height * theme.tile, maze.width * theme.tile), dtype=bool)
    top = (theme.tile - theme.gate_bar) // 2

    for row, col in zip(*np.nonzero(maze.topography == Tile.GHOST_GATE)):
        y, x = row * theme.tile, col * theme.tile
        vertical = (
            0 < row < maze.height - 1
            and maze.topography[row - 1, col] == Tile.GHOST_GATE
            and maze.topography[row + 1, col] == Tile.GHOST_GATE
        )

        if vertical:
            mask[y:y + theme.tile, x + top:x + top + theme.gate_bar] = True
        else:
            mask[y + top:y + top + theme.gate_bar, x:x + theme.tile] = True

    return mask


def render_maze(maze: Maze, theme: Theme, scale: int) -> pygame.Surface:
    """The maze background (walls and gate, no pellets), scaled by `scale`."""

    outline = wall_outline_mask(maze, theme)
    gate = gate_bar_mask(maze, theme)

    pixels = np.empty(outline.shape + (3,), dtype=np.uint8)
    pixels[:] = theme.background
    pixels[outline] = theme.wall_outline
    pixels[gate] = theme.gate

    # surfarray is indexed (x, y)
    surface = pygame.surfarray.make_surface(pixels.swapaxes(0, 1))

    return pygame.transform.scale_by(surface, scale)
