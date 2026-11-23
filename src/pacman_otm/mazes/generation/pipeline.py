"""
build_maze(recipe, seed): size -> shape -> topography -> final rule check -> content -> Maze.

The seed is split into independent streams (numpy SeedSequence), so changing
one part of a recipe never changes what the others make: another pellet placer
keeps the topography and the start, other rules keep the shape.
"""

from typing import Any

import numpy as np

from pacman_otm.mazes.generation.content import PELLET_PLACERS, START_PLACERS
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
        shape, topography, start, pellets, size = np.random.SeedSequence(seed).spawn(5)
        self.shape = np.random.default_rng(shape)
        self.topography = np.random.default_rng(topography)
        self.start = np.random.default_rng(start)
        self.pellets = np.random.default_rng(pellets)
        self.size = np.random.default_rng(size)


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

    return Maze(
        topography=grid,
        pacman_start=start,
        pellets=pellets,
        origin=MazeOrigin(
            source="generated",
            name=recipe.name,
            generator=recipe.generator,
            params=recipe.to_dict(),
            seed=seed,
            package_version=package_version(),
        ),
    )


def _resolve_paths(params) -> dict[str, Any]:
    """A layout 'path' may be a registered layout name, e.g. path = "classic"."""

    resolved = dict(params)
    path = resolved.get("path")

    if isinstance(path, str) and path and (LAYOUTS_DIR / f"{path}.txt").is_file():
        resolved["path"] = str(LAYOUTS_DIR / f"{path}.txt")

    return resolved
