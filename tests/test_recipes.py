import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pytest

from pacman_otm.controllers.registry import create_controller_registry
from pacman_otm.mazes.generation.content import pellets_exclude_near_start, start_center
from pacman_otm.mazes.generation.pipeline import SeedStreams, build_maze, build_region
from pacman_otm.mazes.generation.recipe import (
    RecipeError,
    apply_overrides,
    load_recipe,
    recipe_from_dict,
)
from pacman_otm.mazes.origin import MazeOrigin
from pacman_otm.mazes.registry import (
    MazeSpecError,
    create_maze_registry,
    load_saved_maze,
    resolve_maze,
    resolve_maze_source,
    save_maze,
)
from pacman_otm.mazes.rules.hard import HARD_RULES
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.replay import ReplayPlayer
from pacman_otm.simulation.result import SimulationResult
from pacman_otm.simulation.runner import run_simulation

STARTER_RECIPES = ["open-lattice", "wide-halls", "blob-lattice", "classic-like", "twisty"]

MINIMAL = {"size": {"height": 21, "width": 21}}


def recipe(**changes):
    return recipe_from_dict({**MINIMAL, **changes})


def test_starter_recipes_are_registered() -> None:
    registry = create_maze_registry()

    for name in STARTER_RECIPES:
        assert registry.source(name).kind == "recipe"


@pytest.mark.parametrize("name", STARTER_RECIPES)
def test_starter_recipes_build_for_20_seeds(name: str) -> None:
    source = create_maze_registry().source(name)
    rules = HARD_RULES + source.recipe().rule_set

    for seed in range(20):
        maze = source.build(seed)
        assert rules.holds(maze.topography), (name, seed)
        assert maze.pacman_start not in maze.initial_pellets


def test_minimal_recipe_uses_defaults() -> None:
    built = recipe()

    assert (built.shape.name, built.generator, built.pellets.name, built.start.name) == (
        "rectangle",
        "lattice",
        "all_corridors",
        "center",
    )
    assert built.rules == ()
    assert recipe_from_dict(built.to_dict()) == built


def test_same_seed_same_maze_and_origin_records_everything() -> None:
    built = recipe(rules=[{"rule": "max_dead_ends", "count": 0}])
    first, second = build_maze(built, 5), build_maze(built, 5)

    assert np.array_equal(first.topography, second.topography)
    assert first.initial_pellets == second.initial_pellets
    assert first.origin == second.origin
    assert first.origin.seed == 5 and first.origin.source == "generated"
    assert first.origin.package_version
    assert recipe_from_dict(json.loads(json.dumps(first.origin.to_dict()["params"]))) == built


def test_a_different_pellet_placer_keeps_topography_and_start() -> None:
    base = recipe()
    sparse = apply_overrides(base, ["content.pellets.placer=density", "content.pellets.p=0.3"])

    for seed in range(5):
        a, b = build_maze(base, seed), build_maze(sparse, seed)
        assert np.array_equal(a.topography, b.topography)
        assert a.pacman_start == b.pacman_start
        assert b.initial_pellets < a.initial_pellets


def test_different_rules_keep_the_shape() -> None:
    blob = recipe(shape={"kind": "blob"})
    strict = apply_overrides(blob, ["rules.max_dead_ends.count=0", "topography.extra_loops=0.4"])

    assert np.array_equal(build_region(blob, SeedStreams(3)), build_region(strict, SeedStreams(3)))


def test_content_placers() -> None:
    grid = build_maze(recipe(), 0).topography
    start = start_center(grid, np.random.default_rng(0))

    near = pellets_exclude_near_start(grid, start, np.random.default_rng(0), distance=3)
    rows, cols = zip(*near)
    assert all(abs(r - start[0]) + abs(c - start[1]) > 3 for r, c in near)
    assert len(rows) == len(cols) > 0


def test_layout_start_and_shape(tmp_path) -> None:
    built = recipe_from_dict(
        {
            "size": {"height": 31, "width": 28},
            "shape": {"kind": "layout", "path": "classic"},
            "content": {"start": {"placer": "layout"}},
        }
    )
    maze = build_maze(built, 0)

    # Near classic's 'P' at (23, 13).
    assert abs(maze.pacman_start[0] - 23) + abs(maze.pacman_start[1] - 13) <= 4


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({}, "size: missing"),
        ({**MINIMAL, "sise": 3}, r"unknown parameter\(s\) sise for a recipe"),
        ({"size": {"height": 21}}, "size.width: missing"),
        ({"size": {"height": "big", "width": 21}}, "size.height: expected an integer"),
        ({**MINIMAL, "shape": {"kind": "star"}}, "shape.kind: unknown kind 'star'"),
        ({**MINIMAL, "shape": {"kind": "blob", "fil": 0.5}}, r"shape: unknown parameter\(s\) fil for kind 'blob'"),
        ({**MINIMAL, "topography": {"spacing": 3}}, "topography.spacing: expected a list of 2 values"),
        ({**MINIMAL, "topography": {"spacing": [1, 3]}}, "topography.spacing: min must be >= corridor_width"),
        ({**MINIMAL, "topography": {"loops": 0.1}}, r"topography: unknown parameter\(s\) loops for generator 'lattice'"),
        ({**MINIMAL, "topography": {"generator": "maze-o-matic"}}, "topography.generator: unknown generator"),
        ({**MINIMAL, "rules": [{"rule": "max_blok"}]}, r"rules\[0\]: unknown rule 'max_blok'"),
        ({**MINIMAL, "rules": [{"rule": "max_block", "tile": "wall"}]}, r"rules\[0\]\.size: missing"),
        ({**MINIMAL, "content": {"pellets": {"placer": "sprinkle"}}}, "content.pellets.placer: unknown placer"),
        ({**MINIMAL, "content": {"pellets": {"placer": "density", "q": 1}}}, r"unknown parameter\(s\) q for placer 'density'"),
        ({**MINIMAL, "content": {"start": {"placer": "layout"}}}, "placer 'layout' needs content.start.path"),
    ],
)
def test_bad_recipes_name_the_field(data, message: str) -> None:
    with pytest.raises(RecipeError, match=message):
        recipe_from_dict(data)


def test_recipe_file_errors_name_the_file(tmp_path) -> None:
    path = tmp_path / "broken.toml"
    path.write_text('[size]\nheight = 21\nwidth = 21\n[topography]\nspacing = [2]\n', encoding="utf-8")

    with pytest.raises(RecipeError, match=r"broken.toml: topography.spacing: expected a list of 2 values"):
        load_recipe(path)

    path.write_text("[size\n", encoding="utf-8")

    with pytest.raises(RecipeError, match="broken.toml: invalid TOML"):
        load_recipe(path)


def test_overrides() -> None:
    base = load_recipe(create_maze_registry().source("open-lattice").path)
    changed = apply_overrides(
        base,
        [
            "size=41x45",
            "topography.extra_loops=0.3",
            "topography.spacing=[2, 3]",
            "rules.max_block.wall.size=4",
            "rules.max_dead_ends=off",
            "rules.max_straight_run.length=9",
            "shape.kind=blob",
            "shape.fill=0.5",
            'description="tweaked"',
        ],
    )

    assert (changed.heights, changed.widths) == ((41, 41), (45, 45))
    assert changed.topography.extra_loops == 0.3 and changed.topography.spacing == (2, 3)
    assert changed.shape.name == "blob" and changed.shape.params["fill"] == 0.5
    assert changed.description == "tweaked"

    rules = {rule.describe() for rule in changed.rules}
    assert "max_block(tile=wall, size=4)" in rules
    assert "max_straight_run(length=9)" in rules
    assert not any(rule.name == "max_dead_ends" for rule in changed.rules)
    assert apply_overrides(base, []) is base


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ("size", "expected KEY=VALUE"),
        ("size=big", "size: expected HxW"),
        ("colour=red", "unknown key"),
        ("rules.max_dead_ends=on", "use rules.max_dead_ends=off"),
        ("rules.min_loops=off", "no rule min_loops to remove"),
        ("rules.max_block.size=3", "tile must be one of corridor, wall, void, got 'size'"),
        ("topography.extra_loops=lots", "topography.extra_loops: expected a number"),
        ("content.start.placer=layout", "placer 'layout' needs content.start.path"),
    ],
)
def test_bad_overrides(override: str, message: str) -> None:
    base = load_recipe(create_maze_registry().source("open-lattice").path)

    with pytest.raises(RecipeError, match=message):
        apply_overrides(base, [override])


def test_ambiguous_rule_override() -> None:
    base = recipe(rules=[{"rule": "min_loops", "count": 1}, {"rule": "min_loops", "count": 2}])

    with pytest.raises(RecipeError, match="has 2 min_loops rules; the key is ambiguous"):
        apply_overrides(base, ["rules.min_loops.count=3"])


def test_density_needs_a_valid_p() -> None:
    base = recipe()

    with pytest.raises(MazeSpecError, match=r"p must be in \(0, 1\]"):
        source = resolve_maze_source("open-lattice", ["content.pellets.placer=density", "content.pellets.p=0"])
        source.build(0)

    assert apply_overrides(base, ["content.pellets.placer=density"]).pellets.name == "density"


def test_resolve_specs(tmp_path) -> None:
    assert resolve_maze_source("open-lattice").kind == "recipe"
    assert resolve_maze("open-lattice", maze_seed=2).origin.seed == 2

    recipe_path = tmp_path / "mine.toml"
    recipe_path.write_text('[size]\nheight = 15\nwidth = 15\n', encoding="utf-8")
    assert resolve_maze(str(recipe_path), maze_seed=1).height == 15

    with pytest.raises(MazeSpecError, match="--maze-set only applies to recipes; 'classic' is a layout"):
        resolve_maze_source("classic", ["size=41x41"])

    with pytest.raises(MazeSpecError, match="must end in .txt, .toml, .json"):
        resolve_maze_source(str(tmp_path / "maze.yaml"))


def test_name_clashes_are_errors(tmp_path) -> None:
    layouts, recipes, saved = (tmp_path / name for name in ("layouts", "recipes", "saved"))

    for directory in (layouts, recipes, saved):
        directory.mkdir()

    (layouts / "twin.txt").write_text("#####\n#P..#\n#...#\n#...#\n#####\n", encoding="utf-8")
    (recipes / "twin.toml").write_text("[size]\nheight = 15\nwidth = 15\n", encoding="utf-8")

    with pytest.raises(MazeSpecError, match="Maze name 'twin' is used twice: layout .* and recipe"):
        create_maze_registry(layouts, recipes, saved)


def test_saved_maze_round_trip(tmp_path) -> None:
    maze = resolve_maze("blob-lattice", maze_seed=4)
    path = tmp_path / "keep.json"
    save_maze(maze, path)
    loaded = load_saved_maze(path)

    assert np.array_equal(loaded.topography, maze.topography)
    assert loaded.pacman_start == maze.pacman_start
    assert loaded.initial_pellets == maze.initial_pellets
    assert loaded.origin == maze.origin

    path.write_text('{"maze": {}}', encoding="utf-8")

    with pytest.raises(MazeSpecError, match="not a saved maze of version 1"):
        load_saved_maze(path)


def test_origin_params_are_deeply_frozen() -> None:
    origin = MazeOrigin(source="generated", name="x", params={"rules": [{"rule": "min_loops", "count": 1}]})

    with pytest.raises(TypeError):
        origin.params["rules"][0]["count"] = 5

    assert origin.to_dict()["params"] == {"rules": [{"rule": "min_loops", "count": 1}]}
    assert MazeOrigin.from_dict(origin.to_dict()) == origin


def test_generated_run_saves_and_replays_on_its_own(tmp_path) -> None:
    maze = resolve_maze("classic-like", maze_seed=7)
    result = run_simulation(
        engine=SimulationEngine(maze),
        controller=create_controller_registry().create("nearest-pellet", maze, 0),
        max_steps=300,
    )
    path = tmp_path / "run.json"
    result.save_json(path)
    loaded = SimulationResult.load_json(path)

    assert loaded.maze.origin == maze.origin
    assert np.array_equal(loaded.maze.topography, maze.topography)
    assert ReplayPlayer(loaded).last_frame().state.pacman_position == result.final_state.pacman_position


def test_preview_draws_highlights() -> None:
    import pygame

    from pacman_otm.visualization.pygame_renderer import PygameRenderer

    maze = resolve_maze("open-lattice", maze_seed=1)
    renderer = PygameRenderer(maze, scale=1)

    try:
        renderer.draw_preview([(1, 1)], "status")
        x, y = renderer._tile_pixel((1, 1))
        color = renderer.screen.get_at((int(x) + 1, int(y) + 1))
        assert color.r > color.b  # tinted red over the dark background
    finally:
        renderer.close()
        pygame.quit()


def test_a_recipe_without_a_seed_gets_a_random_announced_one(monkeypatch, capsys) -> None:
    import argparse

    from pacman_otm import maze_commands

    monkeypatch.setattr(maze_commands, "random_maze_seed", lambda: 1234)
    args = argparse.Namespace(maze_set=[], maze_seed=None)

    source, maze, seed = maze_commands.load_maze("open-lattice", args)
    assert seed == 1234 and maze.origin.seed == 1234
    assert "--maze-seed 1234" in capsys.readouterr().out

    # A given seed is used as is; layouts need none and print nothing.
    args.maze_seed = 5
    assert maze_commands.load_maze("open-lattice", args)[2] == 5
    args.maze_seed = None
    assert maze_commands.load_maze("small", args)[2] == 0
    assert capsys.readouterr().out == ""


def test_a_failing_random_seed_is_replaced(monkeypatch, capsys) -> None:
    import argparse

    from pacman_otm import maze_commands
    from pacman_otm.mazes.registry import MazeGenerationFailed, MazeSource

    seeds = iter([1, 2])
    monkeypatch.setattr(maze_commands, "random_maze_seed", lambda: next(seeds))
    original = MazeSource.build

    def build(self, seed=0):
        if seed == 1:
            raise MazeGenerationFailed(self.name, seed, "too strict")
        return original(self, seed)

    monkeypatch.setattr(MazeSource, "build", build)
    args = argparse.Namespace(maze_set=[], maze_seed=None)

    assert maze_commands.load_maze("open-lattice", args)[2] == 2
    output = capsys.readouterr().out
    assert "Maze seed 1 failed (too strict)" in output and "--maze-seed 2" in output

    # A seed the user chose is never replaced.
    args.maze_seed = 1
    with pytest.raises(MazeGenerationFailed, match="with seed 1: too strict"):
        maze_commands.load_maze("open-lattice", args)
