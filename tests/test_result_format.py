"""The saved result format: compact on disk, identical after loading."""

import json

import pytest

from pacman_otm.controllers.ghosts.registry import create_ghosts, ghost_lineup
from pacman_otm.controllers.registry import create_controller_registry
from pacman_otm.mazes.registry import resolve_maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.encoding import decode_moves, decode_path, encode_moves, encode_path
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.replay import ReplayPlayer
from pacman_otm.simulation.result import FORMAT_VERSION, SimulationResult
from pacman_otm.simulation.runner import run_simulation


def run(spec: str, controller: str, ghost_count: int | None = None, seed: int = 0, max_steps: int = 3000):
    maze = resolve_maze(spec, maze_seed=seed, ghost_count=ghost_count)
    kinds = ghost_lineup(maze)

    return run_simulation(
        engine=SimulationEngine(maze, kinds),
        controller=create_controller_registry().create(controller, maze, seed),
        ghosts=create_ghosts(maze, kinds),
        max_steps=max_steps,
    )


def assert_same(loaded: SimulationResult, result: SimulationResult) -> None:
    assert [state.to_dict() for state in loaded.states] == [state.to_dict() for state in result.states]
    assert loaded.actions == result.actions
    assert loaded.statuses == result.statuses
    assert loaded.ghost_statuses == result.ghost_statuses
    assert loaded.ghosts == result.ghosts
    assert loaded.controller == result.controller
    assert loaded.metrics == result.metrics


@pytest.mark.parametrize(
    ("spec", "controller", "ghosts"),
    [
        ("classic", "nearest-pellet", None),
        ("classic", "random-walk", 4),
        ("classic", "nearest-pellet", 0),
        ("small", "two-opt", None),
        ("open-lattice", "nearest-pellet-tour", 3),
    ],
)
def test_round_trip(tmp_path, spec, controller, ghosts) -> None:
    result = run(spec, controller, ghosts)
    path = tmp_path / "result.json"
    result.save_json(path)

    assert_same(SimulationResult.load_json(path), result)


def test_large_run_stays_small(tmp_path) -> None:
    # Without ghosts this run took about 4.9 MB in format 3.
    result = run("big_grotto1", "nearest-pellet-tour", ghost_count=0, max_steps=1000)
    path = tmp_path / "result.json"
    result.save_json(path)

    assert len(result.actions) == 1000
    assert path.stat().st_size < 200_000
    assert_same(SimulationResult.load_json(path), result)


def test_replay_frames_carry_ghost_statuses(tmp_path) -> None:
    result = run("classic", "random-walk", 2, seed=4)
    path = tmp_path / "result.json"
    result.save_json(path)
    replay = ReplayPlayer(SimulationResult.load_json(path))

    assert replay.get_frame(0).ghost_statuses == ()
    assert replay.get_frame(1).ghost_statuses == result.ghost_statuses[0]
    assert len(replay.get_frame(1).state.ghosts) == 2


def test_old_versions_are_rejected() -> None:
    data = run("small", "nearest-pellet").to_dict()
    data["format_version"] = FORMAT_VERSION - 1

    with pytest.raises(ValueError, match="Re-run"):
        SimulationResult.from_dict(json.loads(json.dumps(data)))


def test_path_and_move_encoding() -> None:
    path = ((11, 13), (11, 12), (10, 12), (10, 13))

    assert encode_path(path) == "11,13:LUR"
    assert decode_path("11,13:LUR") == path
    assert encode_path(()) == "" and decode_path("") == ()

    jump = ((1, 1), (5, 5))
    assert encode_path(jump) == "1,1|5,5"
    assert decode_path("1,1|5,5") == jump

    assert decode_moves(encode_moves(list(Action))) == list(Action)
