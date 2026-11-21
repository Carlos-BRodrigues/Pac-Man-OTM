import numpy as np
import pytest

from pacman_otm.controllers.registry import create_controller_registry
from pacman_otm.mazes.layout import parse_layout
from pacman_otm.mazes.registry import create_maze_registry
from pacman_otm.mazes.maze import Maze
from pacman_otm.mazes.origin import MazeOrigin
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.replay import ReplayPlayer
from pacman_otm.simulation.result import SimulationResult
from pacman_otm.simulation.runner import run_simulation


def test_unreachable_pellet_is_rejected() -> None:
    layout = (
        "#######\n"
        "#P.#..#\n"
        "#######\n"
    )

    with pytest.raises(ValueError, match=r"2 pellet\(s\) cannot be reached.*\(1, 4\)"):
        parse_layout(layout, name="split")


def test_pellet_on_wall_is_rejected() -> None:
    with pytest.raises(ValueError, match="do not allow pellets"):
        Maze(topography=[[1, 1, 1], [1, 0, 1], [1, 1, 1]], pacman_start=(1, 1), pellets={(0, 0)})


def test_unknown_tile_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"unknown tile values \[7\]"):
        Maze(topography=[[1, 1, 1], [1, 0, 7], [1, 1, 1]], pacman_start=(1, 1), pellets=set())


def test_ragged_grid_is_rejected() -> None:
    with pytest.raises(ValueError, match="rectangular"):
        Maze(topography=[[1, 1, 1], [1, 0], [1, 1, 1]], pacman_start=(1, 1), pellets=set())


def test_maze_is_immutable() -> None:
    maze = create_maze_registry().create("small")

    with pytest.raises(ValueError):
        maze.topography[1, 1] = 1

    assert isinstance(maze.initial_pellets, frozenset)

    with pytest.raises(TypeError):
        maze.get_valid_movements(maze.pacman_start)[Action.UP] = (0, 0)


def test_neighbour_order_follows_movements() -> None:
    maze = create_maze_registry().create("classic")

    for position in maze.walkable_positions():
        actions = list(maze.get_valid_movements(position))
        assert actions == [action for action in Maze.MOVEMENTS if action in actions]


def test_layout_origin() -> None:
    assert create_maze_registry().create("small").origin == MazeOrigin(source="layout", name="small")


@pytest.mark.parametrize("controller", ["nearest-pellet", "random-walk"])
def test_save_load_round_trip_replays(tmp_path, controller: str) -> None:
    maze = create_maze_registry().create("small")
    result = run_simulation(
        engine=SimulationEngine(maze),
        controller=create_controller_registry().create(controller, maze, 3),
        max_steps=200,
    )

    path = tmp_path / "run.json"
    result.save_json(path)
    loaded = SimulationResult.load_json(path)

    assert loaded.maze.origin == maze.origin
    assert np.array_equal(loaded.maze.topography, maze.topography)
    assert loaded.maze.initial_pellets == maze.initial_pellets
    assert loaded.actions == result.actions
    assert [s.to_dict() for s in loaded.states] == [s.to_dict() for s in result.states]

    replay = ReplayPlayer(loaded)
    frames = [replay.get_frame(index) for index in range(replay.total_frames)]
    assert frames[-1].state.pacman_position == result.final_state.pacman_position


def test_unsupported_format_version_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported result format version"):
        SimulationResult.from_dict({"maze": {}, "states": []})
