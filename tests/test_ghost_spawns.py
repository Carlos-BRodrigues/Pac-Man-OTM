"""Ghost spawns are maze content: placed after the topography, never changing it."""

import numpy as np
import pytest

from pacman_otm.mazes.analysis import analyze, start_distances
from pacman_otm.mazes.generation.content import place_ghost_spawns
from pacman_otm.mazes.generation.errors import GenerationError
from pacman_otm.mazes.generation.pipeline import with_ghost_count
from pacman_otm.mazes.generation.recipe import RecipeError, apply_overrides, load_recipe
from pacman_otm.mazes.layout import format_layout, parse_layout
from pacman_otm.mazes.maze import Maze
from pacman_otm.mazes.registry import RECIPES_DIR, create_maze_registry, resolve_maze
from pacman_otm.mazes.serialization import maze_from_dict, maze_to_dict
from pacman_otm.mazes.tiles import Tile

SPAWN_LAYOUT = (
    "#######\n"
    "#P.g G#\n"
    "#.###.#\n"
    "#.....#\n"
    "#######\n"
)


def test_layout_spawns_in_reading_order_and_round_trip() -> None:
    maze = parse_layout(SPAWN_LAYOUT, name="spawns")

    assert maze.ghost_spawns == ((1, 3), (1, 5))
    # 'g' holds a pellet, 'G' does not.
    assert (1, 3) in maze.initial_pellets
    assert (1, 5) not in maze.initial_pellets
    assert format_layout(maze) == SPAWN_LAYOUT


def test_classic_has_blinky_above_the_house_and_three_ghosts_inside() -> None:
    maze = create_maze_registry().create("classic")

    assert maze.ghost_spawns == ((11, 13), (14, 12), (14, 13), (14, 15))
    assert maze.ghost_spawn_kinds == ("blinky", "inky", "pinky", "clyde")
    assert all(maze.topography[spawn] == Tile.GHOST_HOUSE for spawn in maze.ghost_spawns[1:])
    assert analyze(maze).ghost_spawns == 4


@pytest.mark.parametrize(
    ("spawns", "message"),
    [
        ([(0, 0)], "walk"),
        ([(1, 1)], "start"),
        ([(1, 3), (1, 3)], "distinct"),
    ],
)
def test_maze_rejects_bad_spawns(spawns, message) -> None:
    good = parse_layout(SPAWN_LAYOUT, name="spawns")

    with pytest.raises(ValueError, match=message):
        Maze(
            topography=good.topography,
            pacman_start=good.pacman_start,
            pellets=good.initial_pellets,
            ghost_spawns=spawns,
        )


def test_serialization_keeps_spawns_and_old_mazes_load_without_them() -> None:
    maze = parse_layout(SPAWN_LAYOUT, name="spawns")
    data = maze_to_dict(maze)

    assert maze_from_dict(data).ghost_spawns == maze.ghost_spawns

    del data["ghost_spawn_kinds"]
    assert maze_from_dict(data).ghost_spawn_kinds == (None,) * len(maze.ghost_spawns)

    del data["ghost_spawns"]
    assert maze_from_dict(data).ghost_spawns == ()


def test_placer_is_deterministic_distinct_far_and_prefix_stable() -> None:
    maze = create_maze_registry().create("classic")
    distances = start_distances(maze)

    def place(count: int, seed: int = 5) -> list:
        return place_ghost_spawns(
            maze.topography,
            maze.pacman_start,
            np.random.default_rng(seed),
            count=count,
            min_distance=12,
        )

    four = place(4)

    assert four == place(4)
    assert len(set(four)) == 4
    assert all(distances[spawn] >= 12 for spawn in four)
    assert place(2) == four[:2]
    assert place(4, seed=6) != four


def test_placer_names_the_fields_when_there_is_no_room() -> None:
    maze = parse_layout(SPAWN_LAYOUT, name="spawns")

    with pytest.raises(GenerationError, match="content.ghosts"):
        place_ghost_spawns(maze.topography, maze.pacman_start, np.random.default_rng(0), count=3, min_distance=50)


def test_layout_keeps_its_own_spawns_first() -> None:
    maze = create_maze_registry().create("classic")

    assert with_ghost_count(maze, 0, seed=0).ghost_spawns == ()

    six = with_ghost_count(maze, 6, seed=3)
    assert six.ghost_spawns[:4] == maze.ghost_spawns
    assert len(six.ghost_spawns) == 6
    assert six.origin.params["ghosts"] == {"count": 6, "seed": 3}
    assert np.array_equal(six.topography, maze.topography)
    assert six.initial_pellets == maze.initial_pellets


@pytest.mark.parametrize("recipe", ["open-lattice", "twisty", "organic"])
def test_ghost_count_never_changes_topography_start_or_pellets(recipe) -> None:
    mazes = [resolve_maze(recipe, maze_seed=7, ghost_count=count) for count in (0, 1, 4)]

    for maze in mazes[1:]:
        assert np.array_equal(maze.topography, mazes[0].topography)
        assert maze.pacman_start == mazes[0].pacman_start
        assert maze.initial_pellets == mazes[0].initial_pellets

    assert [len(maze.ghost_spawns) for maze in mazes] == [0, 1, 4]
    assert mazes[2].ghost_spawns[:1] == mazes[1].ghost_spawns


def test_recipe_ghost_table_and_overrides() -> None:
    recipe = load_recipe(RECIPES_DIR / "open-lattice.toml")

    assert recipe.ghosts.params["count"] == 4
    assert recipe.to_dict()["content"]["ghosts"]["placer"] == "random"

    changed = apply_overrides(recipe, ["content.ghosts.count=3"])
    assert changed.ghosts.params["count"] == 3

    with pytest.raises(RecipeError, match="content.ghosts"):
        apply_overrides(recipe, ["content.ghosts.colour=3"])


# The default pellet placer: a pellet-free box at the centre of the grid.


@pytest.mark.parametrize(
    ("shape", "box"),
    [((31, 28), (11, 9, 9, 10)), ((31, 31), (10, 10, 11, 11)), ((11, 11), (3, 3, 5, 5)), ((101, 101), (33, 33, 35, 35))],
)
def test_clear_center_box_is_centred_and_scales(shape, box) -> None:
    from pacman_otm.mazes.generation.content import clear_center_box

    top, left, rows, cols = clear_center_box(*shape)
    assert (top, left, rows, cols) == box
    # Centred exactly: equal margins on both sides of each axis.
    assert top == shape[0] - top - rows
    assert left == shape[1] - left - cols


def test_clear_center_is_the_default_and_leaves_the_centre_empty() -> None:
    from pacman_otm.mazes.generation.content import clear_center_box

    maze = resolve_maze("organic", maze_seed=4)
    top, left, rows, cols = clear_center_box(maze.height, maze.width)

    assert load_recipe(RECIPES_DIR / "organic.toml").pellets.name == "clear_center"
    assert maze.initial_pellets
    assert not any(top <= row < top + rows and left <= col < left + cols for row, col in maze.initial_pellets)
    # Everything outside the box has a pellet.
    outside = {
        tile for tile in maze.walkable_positions()
        if not (top <= tile[0] < top + rows and left <= tile[1] < left + cols)
    } - {maze.pacman_start}
    assert outside == set(maze.initial_pellets)
