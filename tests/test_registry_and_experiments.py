import json

import pytest

from pacman_otm.controllers.registry import create_controller_registry
from pacman_otm.experiments.runner import ExperimentRunner
from pacman_otm.experiments.seeding import derive_run_seeds
from pacman_otm.mazes.registry import (
    DEFAULT_MAZE,
    MazeSpecError,
    create_maze_registry,
    resolve_maze,
)
from pacman_otm.simulation.replay import ReplayPlayer
from pacman_otm.simulation.result import SimulationResult


def test_layout_files_are_registered() -> None:
    names = create_maze_registry().names()

    assert {"small", "classic"} <= set(names)
    assert DEFAULT_MAZE in names


def test_resolve_by_name_and_by_path(tmp_path) -> None:
    assert resolve_maze("small").name == "small"

    path = tmp_path / "tiny.txt"
    path.write_text("####\n#P.#\n####\n", encoding="utf-8")

    maze = resolve_maze(str(path))
    assert maze.name == "tiny"
    assert maze.initial_pellets == {(1, 2)}


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ("nope", "Unknown maze 'nope'. Available: "),
        ("missing.txt", "does not exist"),
    ],
)
def test_bad_maze_specs(spec: str, message: str) -> None:
    with pytest.raises(MazeSpecError, match=message):
        resolve_maze(spec)


def test_invalid_layout_file_names_the_file(tmp_path) -> None:
    path = tmp_path / "broken.txt"
    path.write_text("####\n#..#\n####\n", encoding="utf-8")

    with pytest.raises(MazeSpecError, match="broken.txt.*exactly one 'P'"):
        resolve_maze(str(path))


def test_run_seeds_are_deterministic_and_distinct() -> None:
    first = [derive_run_seeds(42, index) for index in range(50)]
    second = [derive_run_seeds(42, index) for index in range(50)]

    assert first == second
    assert len({seeds.maze_seed for seeds in first}) == 50
    assert len({seeds.controller_seed for seeds in first}) == 50
    assert derive_run_seeds(43, 0) != derive_run_seeds(42, 0)

    with pytest.raises(ValueError):
        derive_run_seeds(-1, 0)


def _run_experiment(tmp_path, controller: str, name: str):
    maze = resolve_maze("small")
    requested_maze_seeds = []

    def maze_factory(maze_seed: int):
        requested_maze_seeds.append(maze_seed)
        return maze

    runner = ExperimentRunner(
        maze_factory=maze_factory,
        controller_factory=lambda maze, seed: create_controller_registry().create(
            controller, maze, seed
        ),
        controller_name=controller,
        experiment_name=name,
        maze_label=maze.name,
        output_root=tmp_path,
        seed=42,
        max_steps=200,
    )

    return runner.run(4), requested_maze_seeds


def test_controllers_see_the_same_maze_sequence(tmp_path) -> None:
    random_results, random_mazes = _run_experiment(tmp_path, "random-walk", "a")
    nearest_results, nearest_mazes = _run_experiment(tmp_path, "nearest-pellet", "b")

    assert random_mazes == nearest_mazes
    assert random_mazes == [derive_run_seeds(42, index).maze_seed for index in range(4)]

    rerun, _ = _run_experiment(tmp_path, "random-walk", "c")
    assert [run.actions for run in rerun.runs] == [run.actions for run in random_results.runs]


def test_experiment_files(tmp_path) -> None:
    results, _ = _run_experiment(tmp_path, "random-walk", "files")

    summary = json.loads((results.output_dir / "results.json").read_text(encoding="utf-8"))
    assert summary["experiment"]["seed"] == 42
    assert summary["experiment"]["maze"] == "small"
    assert "map" not in summary

    record = summary["individual_runs"][0]
    seeds = derive_run_seeds(42, 0)
    assert record["maze"] == "small"
    assert record["maze_seed"] == seeds.maze_seed
    assert record["controller_seed"] == seeds.controller_seed

    header = (results.output_dir / "results.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header.startswith("run,maze,maze_seed,controller_seed,")

    for run_file in sorted((results.output_dir / "runs").glob("*/result.json")):
        loaded = SimulationResult.load_json(run_file)
        assert loaded.maze.origin.name == "small"
        assert loaded.controller["seed"] in {s.controller_seed for s in results.seeds}
        ReplayPlayer(loaded).last_frame()
