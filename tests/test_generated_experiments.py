import csv
import json

import numpy as np
import pytest

from pacman_otm.controllers.registry import create_controller_registry
from pacman_otm.experiments.runner import ExperimentRunner
from pacman_otm.experiments.seeding import derive_run_seeds
from pacman_otm.maze_commands import experiment_mazes
from pacman_otm.simulation.replay import ReplayPlayer
from pacman_otm.simulation.result import SimulationResult

RECIPE = """
name = "tiny-lattice"

[size]
height = 15
width = 15

[topography]
extra_loops = 0.2

[[rules]]
rule = "max_dead_ends"
count = 0
"""


@pytest.fixture
def recipe_path(tmp_path):
    path = tmp_path / "tiny-lattice.toml"
    path.write_text(RECIPE, encoding="utf-8")
    return path


def run_experiment(tmp_path, spec, controller="random-walk", name="exp", runs=20, maze_seed=None, seed=42):
    mazes = experiment_mazes(spec, (), maze_seed)
    runner = ExperimentRunner(
        maze_factory=mazes.factory,
        controller_factory=lambda maze, seed: create_controller_registry().create(controller, maze, seed),
        controller_name=controller,
        experiment_name=name,
        maze_label=mazes.label,
        output_root=tmp_path / "results",
        seed=seed,
        max_steps=60,
        maze_info=mazes.info,
    )
    return runner.run(runs)


def topographies(results) -> list[bytes]:
    return [run.maze.topography.tobytes() for run in results.runs]


def test_a_recipe_gives_every_run_its_own_maze(tmp_path, recipe_path) -> None:
    results = run_experiment(tmp_path, str(recipe_path))

    assert len(set(topographies(results))) == 20
    assert [run.maze.origin.seed for run in results.runs] == [
        derive_run_seeds(42, index).maze_seed for index in range(20)
    ]

    rerun = run_experiment(tmp_path, str(recipe_path), name="again")
    assert topographies(rerun) == topographies(results)
    assert [run.maze.initial_pellets for run in rerun.runs] == [run.maze.initial_pellets for run in results.runs]


def test_controllers_get_identical_maze_sequences(tmp_path, recipe_path) -> None:
    walker = run_experiment(tmp_path, str(recipe_path), controller="random-walk", name="a", runs=6)
    nearest = run_experiment(tmp_path, str(recipe_path), controller="nearest-pellet", name="b", runs=6)

    assert topographies(walker) == topographies(nearest)
    assert [run.maze.pacman_start for run in walker.runs] == [run.maze.pacman_start for run in nearest.runs]


def test_a_fixed_maze_seed_fixes_the_maze(tmp_path, recipe_path) -> None:
    results = run_experiment(tmp_path, str(recipe_path), runs=4, maze_seed=9)

    assert len(set(topographies(results))) == 1
    assert {run.maze.origin.seed for run in results.runs} == {9}

    summary = json.loads((results.output_dir / "results.json").read_text(encoding="utf-8"))
    assert summary["experiment"]["maze"] == "tiny-lattice-seed9"
    assert summary["experiment"]["maze_per_run"] is False
    assert summary["experiment"]["maze_seed"] == 9
    assert all(record["maze_seed"] == 9 for record in summary["individual_runs"])


def test_experiment_files_describe_the_mazes(tmp_path, recipe_path) -> None:
    results = run_experiment(tmp_path, str(recipe_path), runs=5)

    summary = json.loads((results.output_dir / "results.json").read_text(encoding="utf-8"))
    experiment = summary["experiment"]

    # The recipe is stored once, in full; each run file has the full maze.
    assert experiment["maze"] == "tiny-lattice"
    assert experiment["maze_kind"] == "recipe" and experiment["maze_per_run"] is True
    assert experiment["maze_recipe"]["size"] == {"height": 15, "width": 15}
    assert experiment["maze_recipe"]["rules"] == [{"rule": "max_dead_ends", "count": 0}]
    assert set(summary["aggregates"]["maze_metrics"]) >= {"maze_loops", "maze_walkable_tiles"}

    with (results.output_dir / "results.csv").open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    header = list(rows[0])
    assert header[:4] == ["run", "maze", "maze_seed", "controller_seed"]
    assert header[-6:] == [
        "maze_walkable_tiles",
        "maze_loops",
        "maze_dead_ends",
        "maze_junction_share",
        "maze_longest_straight_run",
        "maze_longest_corridor",
    ]
    assert [int(row["maze_seed"]) for row in rows] == [derive_run_seeds(42, i).maze_seed for i in range(5)]
    assert all(int(row["maze_dead_ends"]) == 0 for row in rows)


def test_every_run_file_replays_on_its_own(tmp_path, recipe_path) -> None:
    results = run_experiment(tmp_path, str(recipe_path), runs=4)
    run_files = sorted((results.output_dir / "runs").glob("*/result.json"))

    assert len(run_files) == 4

    for run_file, original in zip(run_files, results.runs):
        loaded = SimulationResult.load_json(run_file)

        assert loaded.maze.origin == original.maze.origin
        assert loaded.maze.origin.params["name"] == "tiny-lattice"
        assert np.array_equal(loaded.maze.topography, original.maze.topography)
        assert ReplayPlayer(loaded).last_frame().state.to_dict() == original.final_state.to_dict()


def test_layouts_stay_fixed(tmp_path) -> None:
    results = run_experiment(tmp_path, "small", runs=3)

    assert len(set(topographies(results))) == 1
    assert results.runs[0].maze.origin.seed is None


def test_closing_the_visualization_stops_the_experiment(tmp_path, recipe_path) -> None:
    mazes = experiment_mazes(str(recipe_path), (), None)
    started = []

    def on_run_start(run_index, maze):
        started.append(maze.origin.seed)
        steps = []

        # Run 2's window is "closed" after a few frames.
        def on_frame(frame):
            steps.append(frame)
            return not (run_index == 1 and len(steps) > 5)

        return on_frame

    runner = ExperimentRunner(
        maze_factory=mazes.factory,
        controller_factory=lambda maze, seed: create_controller_registry().create("random-walk", maze, seed),
        controller_name="random-walk",
        experiment_name="closed",
        maze_label=mazes.label,
        output_root=tmp_path,
        seed=42,
        max_steps=60,
        maze_info=mazes.info,
        on_run_start=on_run_start,
    )
    results = runner.run(5)

    assert results.stopped_early and len(results.runs) == 2
    assert started == [derive_run_seeds(42, index).maze_seed for index in range(2)]
    assert results.runs[1].metrics.termination_reason == "visualization_closed"

    summary = json.loads((results.output_dir / "results.json").read_text(encoding="utf-8"))
    assert summary["experiment"]["stopped_early"] is True
    assert len(summary["individual_runs"]) == 2


def test_experiment_visualizer_shows_each_runs_maze(tmp_path, recipe_path, monkeypatch) -> None:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    import pygame

    from pacman_otm.visualization.experiment import ExperimentVisualizer

    mazes = experiment_mazes(str(recipe_path), (), None)
    visualizer = ExperimentVisualizer(total_runs=3, scale=1, fps=1000, pause_seconds=0)
    shown = []

    def on_run_start(run_index, maze):
        live = visualizer(run_index, maze)
        shown.append((live.renderer.maze.origin.seed, live.renderer.caption))
        return live

    runner = ExperimentRunner(
        maze_factory=mazes.factory,
        controller_factory=lambda maze, seed: create_controller_registry().create("random-walk", maze, seed),
        controller_name="random-walk",
        experiment_name="watched",
        maze_label=mazes.label,
        output_root=tmp_path,
        seed=42,
        max_steps=8,
        on_run_start=on_run_start,
    )

    try:
        results = runner.run(3)
    finally:
        visualizer.close()
        pygame.quit()

    assert not results.stopped_early and len(results.runs) == 3
    assert [seed for seed, _ in shown] == [run.maze.origin.seed for run in results.runs]
    assert shown[2][1].endswith("run 3/3")
