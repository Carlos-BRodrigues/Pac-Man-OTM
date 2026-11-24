"""Size ranges, naming and saving mazes, the save default, and replaying experiment folders."""

import argparse
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pygame
import pytest

from pacman_otm import cli, maze_commands
from pacman_otm.controllers.registry import create_controller_registry
from pacman_otm.experiments.runner import ExperimentRunner
from pacman_otm.experiments.seeding import derive_run_seeds
from pacman_otm.mazes.generation.pipeline import build_maze
from pacman_otm.mazes.generation.recipe import RecipeError, apply_overrides, recipe_from_dict
from pacman_otm.mazes.layout import load_layout
from pacman_otm.mazes.registry import MazeSpecError, load_saved_maze, resolve_maze
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.replay import ResultSequence
from pacman_otm.simulation.runner import run_simulation
from pacman_otm.visualization.replay import ReplayPygameVisualizer

RANGED = {"size": {"height": [11, 41], "width": [21, 51]}}


# Size ranges


def test_size_ranges_are_drawn_from_the_seed() -> None:
    recipe = recipe_from_dict(RANGED)
    sizes = [(maze.height, maze.width) for maze in (build_maze(recipe, seed) for seed in range(30))]

    assert all(11 <= height <= 41 and 21 <= width <= 51 for height, width in sizes)
    assert len(set(sizes)) > 10
    assert [(m.height, m.width) for m in (build_maze(recipe, s) for s in range(30))] == sizes
    assert recipe.describe_size() == "11..41x21..51" and recipe.fixed_size is None
    assert recipe_from_dict(recipe.to_dict()) == recipe


def test_fixed_sizes_still_work() -> None:
    recipe = recipe_from_dict({"size": {"height": 25, "width": [31, 31]}})

    assert recipe.fixed_size == (25, 31)
    assert recipe.to_dict()["size"] == {"height": 25, "width": 31}


@pytest.mark.parametrize(
    ("size", "message"),
    [
        ({"height": [41, 11], "width": 21}, r"size.height: the range \[41, 11\] runs backwards"),
        ({"height": [3, 21], "width": 21}, "size.height: sizes must be between 5 and 101, got 3"),
        ({"height": 21, "width": [21, 200]}, "size.width: sizes must be between 5 and 101, got 200"),
        ({"height": 21, "width": [21]}, "size.width: expected a list of 2 values"),
    ],
)
def test_bad_size_ranges(size, message: str) -> None:
    with pytest.raises(RecipeError, match=message):
        recipe_from_dict({"size": size})


def test_size_range_overrides() -> None:
    base = recipe_from_dict({"size": {"height": 21, "width": 21}})

    assert apply_overrides(base, ["size=11x21..41x51"]).describe_size() == "11..41x21..51"
    assert apply_overrides(base, ["size.width=[21, 51]"]).widths == (21, 51)

    with pytest.raises(RecipeError, match="or a range such as 11x21..51x51"):
        apply_overrides(base, ["size=11x21..big"])


def test_experiment_runs_get_sizes_from_their_maze_seeds(tmp_path) -> None:
    path = tmp_path / "ranged.toml"
    path.write_text("[size]\nheight = [11, 31]\nwidth = [11, 31]\n", encoding="utf-8")

    mazes = maze_commands.experiment_mazes(str(path), (), None)
    sizes = [
        mazes.factory(i, derive_run_seeds(7, i).maze_seed).topography.shape for i in range(8)
    ]

    assert len(set(sizes)) > 1
    assert sizes == [
        mazes.factory(i, derive_run_seeds(7, i).maze_seed).topography.shape for i in range(8)
    ]


# Naming and saving mazes


def test_save_any_maze_as_json_or_editable_layout(tmp_path) -> None:
    maze = resolve_maze("twisty", maze_seed=4)

    json_path = maze_commands.save_named_maze(maze, str(tmp_path / "keep.json"), as_layout=False, force=False)
    saved = load_saved_maze(json_path)
    assert saved.origin.name == "keep" and saved.origin.seed == 4
    assert np.array_equal(saved.topography, maze.topography)

    txt_path = maze_commands.save_named_maze(maze, str(tmp_path / "edit-me.txt"), as_layout=True, force=False)
    layout = load_layout(txt_path)
    assert np.array_equal(layout.topography, maze.topography)
    assert layout.pacman_start == maze.pacman_start
    assert layout.initial_pellets == maze.initial_pellets

    # Hand edits: move the start and remove a pellet, then load it as a maze.
    text = txt_path.read_text(encoding="utf-8").replace("P", ".")
    lines = text.splitlines()
    row, col = sorted(maze.initial_pellets)[0]
    lines[row] = lines[row][:col] + "P" + lines[row][col + 1:]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    edited = resolve_maze(str(txt_path))
    assert edited.pacman_start == (row, col)
    assert (row, col) not in edited.initial_pellets

    with pytest.raises(MazeSpecError, match="already exists; use --force"):
        maze_commands.save_named_maze(maze, str(json_path), as_layout=False, force=False)


@pytest.mark.parametrize(
    ("target", "message"),
    [
        ("open-lattice", "that name is a recipe"),
        ("classic", "Maze 'classic' already exists"),
        ("bad name!", "not a usable maze name"),
    ],
)
def test_save_names_are_checked(target: str, message: str) -> None:
    maze = resolve_maze("small")
    as_layout = target == "classic"

    with pytest.raises(MazeSpecError, match=message):
        maze_commands.save_named_maze(maze, target, as_layout=as_layout, force=False)


# Saving results


def test_simulate_and_play_do_not_save_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "RESULTS_DIR", tmp_path)
    maze = resolve_maze("small")
    result = run_simulation(
        engine=SimulationEngine(maze),
        controller=create_controller_registry().create("nearest-pellet", maze, 0),
        max_steps=20,
    )

    cli.save_result(result, argparse.Namespace(save=False, output=None), label="x")
    assert list(tmp_path.iterdir()) == []

    cli.save_result(result, argparse.Namespace(save=True, output=None), label="auto")
    cli.save_result(result, argparse.Namespace(save=False, output="named.json"), label="x")
    names = sorted(path.name for path in tmp_path.iterdir())
    assert names[0].startswith("auto_") and names[1] == "named.json"


# Replaying experiments


@pytest.fixture
def experiment_folder(tmp_path):
    path = tmp_path / "ranged.toml"
    path.write_text("[size]\nheight = [11, 21]\nwidth = [11, 21]\n", encoding="utf-8")
    mazes = maze_commands.experiment_mazes(str(path), (), None)
    results = ExperimentRunner(
        maze_factory=mazes.factory,
        controller_factory=lambda maze, seed: create_controller_registry().create("random-walk", maze, seed),
        controller_name="random-walk",
        experiment_name="exp",
        maze_label=mazes.label,
        output_root=tmp_path / "results",
        seed=3,
        max_steps=12,
        maze_info=mazes.info,
    ).run(4)
    return results


def test_result_sequence_reads_an_experiment_folder_in_order(experiment_folder) -> None:
    runs = ResultSequence.from_path(experiment_folder.output_dir)

    assert len(runs) == 4
    assert [runs.load(i).maze.origin.seed for i in range(4)] == [r.maze.origin.seed for r in experiment_folder.runs]
    assert runs.label(2) == "run 3/4 (run_0003)"
    assert len(ResultSequence.from_path(experiment_folder.output_dir / "runs")) == 4

    single = ResultSequence.from_path(runs.paths[0])
    assert len(single) == 1


def test_result_sequence_errors(tmp_path) -> None:
    with pytest.raises(ValueError, match="holds no run files"):
        ResultSequence.from_path(tmp_path)

    with pytest.raises(ValueError, match="does not exist"):
        ResultSequence.from_path(tmp_path / "missing")


def _key(key) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0)


def test_replay_moves_between_runs(experiment_folder) -> None:
    runs = ResultSequence.from_path(experiment_folder.output_dir)
    visualizer = ReplayPygameVisualizer.for_runs(runs, fps=30, scale=1)

    try:
        assert visualizer.renderer.hud_label == "RUN 1/4"

        visualizer._handle_event(_key(pygame.K_PAGEDOWN))
        visualizer._handle_event(_key(pygame.K_RIGHTBRACKET))
        assert visualizer.run_index == 2
        assert visualizer.renderer.maze.origin.seed == experiment_folder.runs[2].maze.origin.seed
        assert visualizer.renderer.hud_label == "RUN 3/4"
        visualizer._draw()

        visualizer._handle_event(_key(pygame.K_PAGEUP))
        assert visualizer.run_index == 1

        # Past either end nothing happens.
        visualizer.show_run(-1)
        visualizer.show_run(9)
        assert visualizer.run_index == 1

        # Playing to the end of a run goes on to the next one.
        visualizer.replay.seek(visualizer.replay.total_frames - 2)
        visualizer.playing = True

        for _ in range(200):
            visualizer._update_playback(100)

            if visualizer.run_index == 2:
                break

        assert visualizer.run_index == 2 and visualizer.playing

        visualizer._handle_event(_key(pygame.K_a))
        assert not visualizer.auto_advance
    finally:
        visualizer.close()
