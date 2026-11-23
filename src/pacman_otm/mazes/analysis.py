"""
Measurements of a maze. No thresholds here: rules decide what is acceptable,
these numbers describe what a maze is like (and go into results).
"""

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from pacman_otm.mazes.grid import (
    components,
    corridor_chains,
    dead_end_mask,
    junction_mask,
    straight_runs,
    tile_mask,
    windows,
)
from pacman_otm.mazes.maze import Maze
from pacman_otm.mazes.rules.hard import Enclosed
from pacman_otm.mazes.rules.structure import cycle_rank, mirror_flips


@dataclass(frozen=True)
class MazeMetrics:
    height: int
    width: int
    walkable_tiles: int
    # Of the maze area: every tile except void.
    walkable_fraction: float
    regions: int
    dead_ends: int
    junctions: int
    junction_share: float
    loops: int
    longest_straight_run: int
    longest_corridor: int
    largest_corridor_block: int
    largest_wall_block: int
    enclosed: bool
    # Walkability unchanged by flipping left <-> right / top <-> bottom.
    symmetric_horizontal: bool
    symmetric_vertical: bool
    pellets: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def largest_block(mask: np.ndarray) -> int:
    """Side of the largest all-set square window (0 if none); windows are monotone in size."""

    low, high = 0, min(mask.shape)

    while low < high:
        size = (low + high + 1) // 2

        if windows(mask, size).any():
            low = size
        else:
            high = size - 1

    return low


def analyze(maze: Maze) -> MazeMetrics:
    grid = np.asarray(maze.topography)
    walkable = maze.walkable_mask

    walkable_tiles = int(walkable.sum())
    area = int((~tile_mask(grid, "void")).sum())
    junctions = int(junction_mask(walkable).sum())
    _, regions = components(walkable)

    def symmetric(axis: str) -> bool:
        return all(np.array_equal(walkable, flipped) for flipped in mirror_flips(walkable, axis))

    return MazeMetrics(
        height=maze.height,
        width=maze.width,
        walkable_tiles=walkable_tiles,
        walkable_fraction=walkable_tiles / area if area else 0.0,
        regions=regions,
        dead_ends=int(dead_end_mask(walkable).sum()),
        junctions=junctions,
        junction_share=junctions / walkable_tiles if walkable_tiles else 0.0,
        loops=cycle_rank(walkable),
        longest_straight_run=max((len(run) for run in straight_runs(walkable)), default=0),
        longest_corridor=max((len(chain) for chain in corridor_chains(walkable)), default=0),
        largest_corridor_block=largest_block(walkable),
        largest_wall_block=largest_block(tile_mask(grid, "wall")),
        enclosed=not Enclosed().violations(grid),
        symmetric_horizontal=symmetric("horizontal"),
        symmetric_vertical=symmetric("vertical"),
        pellets=len(maze.initial_pellets),
    )
