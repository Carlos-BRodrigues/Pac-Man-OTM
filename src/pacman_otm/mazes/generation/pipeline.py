"""
build_maze(recipe, seed): size -> shape -> topography -> final rule check -> content -> Maze.

The seed is split into independent streams (numpy SeedSequence), so changing
one part of a recipe never changes what the others make: another pellet placer
keeps the topography and the start, other rules keep the shape, and the number
of ghosts changes only the ghost spawns.
"""

from collections.abc import Sequence
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

Position = tuple[int, int]


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
    The same maze with `count` ghost spawns for any ghost: its own spawns first
    (a layout's spawn letters, in reading order), then seeded random ones from the
    seed's ghost stream. The tiles, start and pellets are unchanged.
    """
    return assign_ghost_spawns(maze, (None,) * count, seed)


def assign_ghost_spawns(maze: Maze, kinds: Sequence[str | None], seed: int) -> Maze:
    """
    The maze of a run whose ghosts are `kinds` (None: any kind), with ghost i on
    spawn i. Deterministic, in reading order:

    1. each ghost takes the first unused spawn marked for its own kind;
    2. ghosts still without one take unused spawns for any ghost, or marked for a
       kind that is not in this run;
    3. any left get seeded random spawns from the seed's ghost stream (never on a
       layout spawn), as with_ghost_count always did: prefix-stable.

    Each spawn is then marked with its ghost's kind (a None ghost keeps the
    spawn's own mark). Tiles, start and pellets never change; the origin records
    the count, kinds and seed. Kinds are plain names: mazes know no ghost classes.
    """
    spawns = maze.ghost_spawns
    marks = maze.ghost_spawn_kinds
    in_run = {kind for kind in kinds if kind is not None}
    chosen: list[int | None] = [None] * len(kinds)
    used: set[int] = set()

    def take(ghost: int, fits) -> None:
        for index, mark in enumerate(marks):
            if index not in used and fits(mark):
                chosen[ghost] = index
                used.add(index)
                return

    for ghost, kind in enumerate(kinds):
        if kind is not None:
            take(ghost, lambda mark, kind=kind: mark == kind)

    for ghost in range(len(kinds)):
        if chosen[ghost] is None:
            take(ghost, lambda mark: mark is None or mark not in in_run)

    missing = chosen.count(None)
    extra: list[Position] = []

    if missing:
        extra = place_ghost_spawns(
            maze.topography,
            maze.pacman_start,
            SeedStreams(seed).ghosts,
            count=len(spawns) + missing,
            fixed=spawns,
        )[len(spawns):]

    extras = iter(extra)
    positions, spawn_kinds = [], []

    for ghost, index in enumerate(chosen):
        positions.append(spawns[index] if index is not None else next(extras))
        spawn_kinds.append(kinds[ghost] if kinds[ghost] is not None else (marks[index] if index is not None else None))

    if tuple(positions) == spawns and tuple(spawn_kinds) == marks:
        return maze

    origin = maze.origin

    if origin is not None:
        ghosts = {"count": len(kinds), "seed": seed}

        if in_run:
            ghosts["kinds"] = list(kinds)

        origin = replace(origin, params={**origin.params, "ghosts": ghosts})

    return Maze(
        topography=maze.topography,
        pacman_start=maze.pacman_start,
        pellets=maze.initial_pellets,
        origin=origin,
        ghost_spawns=positions,
        ghost_spawn_kinds=spawn_kinds,
    )


def _resolve_paths(params) -> dict[str, Any]:
    """A layout 'path' may be a registered layout name, e.g. path = "classic"."""

    resolved = dict(params)
    path = resolved.get("path")

    if isinstance(path, str) and path and (LAYOUTS_DIR / f"{path}.txt").is_file():
        resolved["path"] = str(LAYOUTS_DIR / f"{path}.txt")

    return resolved
