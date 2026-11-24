"""
build_maze(recipe, seed): size -> shape -> topography -> final rule check -> content -> Maze.

The seed is split into independent streams (numpy SeedSequence), so changing
one part of a recipe never changes what the others make: another pellet placer
keeps the topography and the start, other rules keep the shape, and the number
of ghosts changes only the ghost spawns.
"""

from dataclasses import replace
from typing import Any

import numpy as np

from pacman_otm.mazes.generation.content import (
    GHOST_PLACERS,
    PELLET_PLACERS,
    START_PLACERS,
    place_ghost_spawns,
)
from pacman_otm.mazes.generation.errors import GenerationError
from pacman_otm.mazes.generation.recipe import MazeRecipe
from pacman_otm.mazes.generation.registry import GENERATORS
from pacman_otm.mazes.generation.shapes import region_mask
from pacman_otm.mazes.layout import LAYOUTS_DIR
from pacman_otm.mazes.maze import Maze
from pacman_otm.mazes.origin import MazeOrigin, package_version


class SeedStreams:
    """One independent generator per part of the maze."""

    def __init__(self, seed: int) -> None:
        if seed < 0:
            raise GenerationError(f"The maze seed must be non-negative, got {seed}.")

        # New streams go at the end: SeedSequence children keep their values when
        # more are spawned, so existing recipes and seeds keep making the same mazes.
        shape, topography, start, pellets, size, ghosts = np.random.SeedSequence(seed).spawn(6)
        self.shape = np.random.default_rng(shape)
        self.topography = np.random.default_rng(topography)
        self.start = np.random.default_rng(start)
        self.pellets = np.random.default_rng(pellets)
        self.size = np.random.default_rng(size)
        self.ghosts = np.random.default_rng(ghosts)


def pick_size(recipe: MazeRecipe, streams: SeedStreams) -> tuple[int, int]:
    """Height and width, each drawn uniformly from the recipe's range."""

    (low_height, high_height), (low_width, high_width) = recipe.heights, recipe.widths
    height = int(streams.size.integers(low_height, high_height + 1))
    width = int(streams.size.integers(low_width, high_width + 1))
    return height, width


def build_region(recipe: MazeRecipe, streams: SeedStreams) -> np.ndarray:
    height, width = pick_size(recipe, streams)

    return region_mask(
        recipe.shape.name,
        height,
        width,
        streams.shape,
        **_resolve_paths(recipe.shape.params),
    )


def build_maze(recipe: MazeRecipe, seed: int) -> Maze:
    streams = SeedStreams(seed)
    region = build_region(recipe, streams)

    _, generate = GENERATORS[recipe.generator]
    # The generator runs the final full rule check itself.
    grid = generate(region, recipe.topography, recipe.rule_set, streams.topography)

    start_params = _resolve_paths(recipe.start.params)

    if recipe.start.name == "layout" and "path" not in start_params:
        start_params["path"] = _resolve_paths(recipe.shape.params)["path"]

    start = START_PLACERS[recipe.start.name](grid, streams.start, **start_params)
    pellets = PELLET_PLACERS[recipe.pellets.name](
        grid,
        start,
        streams.pellets,
        **_resolve_paths(recipe.pellets.params),
    )
    ghost_spawns = GHOST_PLACERS[recipe.ghosts.name](grid, start, streams.ghosts, **recipe.ghosts.params)

    return Maze(
        topography=grid,
        pacman_start=start,
        pellets=pellets,
        ghost_spawns=ghost_spawns,
        origin=MazeOrigin(
            source="generated",
            name=recipe.name,
            generator=recipe.generator,
            params=recipe.to_dict(),
            seed=seed,
            package_version=package_version(),
        ),
    )


def with_ghost_count(maze: Maze, count: int, seed: int) -> Maze:
    """
    The same maze with `count` ghost spawns: its own spawns first (a layout's G
    tiles, in order), then seeded random ones from the seed's ghost stream. The
    tiles, start and pellets are unchanged. The origin records count and seed.
    """
    if count == len(maze.ghost_spawns):
        return maze

    spawns = place_ghost_spawns(
        maze.topography,
        maze.pacman_start,
        SeedStreams(seed).ghosts,
        count=count,
        fixed=maze.ghost_spawns,
    )
    origin = maze.origin

    if origin is not None:
        origin = replace(origin, params={**origin.params, "ghosts": {"count": count, "seed": seed}})

    return Maze(
        topography=maze.topography,
        pacman_start=maze.pacman_start,
        pellets=maze.initial_pellets,
        origin=origin,
        ghost_spawns=spawns,
    )


def _resolve_paths(params) -> dict[str, Any]:
    """A layout 'path' may be a registered layout name, e.g. path = "classic"."""

    resolved = dict(params)
    path = resolved.get("path")

    if isinstance(path, str) and path and (LAYOUTS_DIR / f"{path}.txt").is_file():
        resolved["path"] = str(LAYOUTS_DIR / f"{path}.txt")

    return resolved
