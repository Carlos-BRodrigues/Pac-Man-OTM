import json

import pytest

from pacman_otm.algorithms.pathfinding.bfs import BreadthFirstSearch
from pacman_otm.controllers.registry import create_controller_registry
from pacman_otm.experiments.runner import ExperimentRunner
from pacman_otm.maze_commands import experiment_mazes
from pacman_otm.mazes.layout import parse_layout
from pacman_otm.mazes.registry import MazeSpecError, resolve_maze
from pacman_otm.mazes.sets import load_maze_set, maze_sets
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.runner import run_simulation


def test_nearest_goal_ties_go_to_lowest_row_col() -> None:
    # Pellets at distance 3 on both sides of the start; BFS order alone would pick by
    # movement order, the rule says lowest (row, col): (1, 1).
    maze = parse_layout("#######\n#.   .#\n#  P  #\n#     #\n#######\n", name="tie")
    goal, path = BreadthFirstSearch().find_path_to_nearest(
        maze, maze.pacman_start, set(maze.initial_pellets)
    )

    assert goal == (1, 1)
    assert len(path) == 3


def test_nearest_goal_is_none_when_nothing_to_reach() -> None:
    maze = resolve_maze("small")
    assert BreadthFirstSearch().find_path_to_nearest(maze, maze.pacman_start, set()) is None


@pytest.mark.parametrize("spec", ["small", "classic", "classic-sparse"])
def test_nearest_pellet_and_its_metric_closure_version_play_identically(spec: str) -> None:
    maze = resolve_maze(spec)
    registry = create_controller_registry()
    runs = [
        run_simulation(SimulationEngine(maze), registry.create(name, maze), max_steps=5000)
        for name in ("nearest-pellet", "nearest-pellet-tour")
    ]

    assert runs[0].actions == runs[1].actions
    assert runs[0].metrics.completed


def test_classic_sparse_has_fifteen_pellets_on_classic_walls() -> None:
    classic, sparse = resolve_maze("classic"), resolve_maze("classic-sparse")

    assert len(sparse.initial_pellets) == 15
    assert set(sparse.initial_pellets) <= set(classic.initial_pellets)
    assert (sparse.topography == classic.topography).all()


def test_starter_set_builds_every_maze() -> None:
    my_mazes = maze_sets()["my-mazes"]
    names = [maze.name for maze in my_mazes.build()]

    assert names[:2] == ["classic", "classic-sparse"]
    assert len(names) == len(my_mazes.specs)


def test_experiment_on_a_set_plays_maze_i_in_run_i(tmp_path) -> None:
    mazes = experiment_mazes("my-mazes", (), None)
    expected = list(maze_sets()["my-mazes"].specs)
    runner = ExperimentRunner(
        maze_factory=mazes.factory,
        controller_factory=lambda maze, seed: create_controller_registry().create(
            "nearest-pellet", maze, seed
        ),
        controller_name="nearest-pellet",
        experiment_name="set",
        maze_label=mazes.label,
        maze_info=mazes.info,
        output_root=tmp_path,
        max_steps=20000,
    )

    results = runner.run(mazes.set_size + 1)
    data = json.loads((results.output_dir / "results.json").read_text(encoding="utf-8"))

    # One extra run cycles back to the first maze.
    assert [run["maze"] for run in data["individual_runs"]] == expected + expected[:1]
    assert data["experiment"]["maze_set_mazes"] == expected


def test_set_rejects_maze_seed_and_recipes(tmp_path) -> None:
    with pytest.raises(MazeSpecError, match="do not apply"):
        experiment_mazes("my-mazes", (), 3)

    path = tmp_path / "bad.toml"
    path.write_text('mazes = ["classic", "open-lattice"]\n', encoding="utf-8")

    with pytest.raises(MazeSpecError, match="recipe 'open-lattice'"):
        load_maze_set(path).build()


def test_set_named_like_a_maze_is_an_error(tmp_path) -> None:
    (tmp_path / "classic.toml").write_text('mazes = ["small"]\n', encoding="utf-8")

    with pytest.raises(MazeSpecError, match="used by maze set"):
        maze_sets(tmp_path)
