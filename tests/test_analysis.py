from pacman_otm.controllers.registry import create_controller_registry
from pacman_otm.mazes.analysis import analyze
from pacman_otm.mazes.registry import create_maze_registry
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.result import SimulationResult
from pacman_otm.simulation.runner import run_simulation


def test_small_metrics_match_a_hand_count() -> None:
    #######
    #P....#   junctions: (3,1), (3,4), (5,4); dead end: (5,5)
    # ### #   edges 20, tiles 19, one region -> 2 loops
    #.....#   the top row is a straight run of 5; the corridor from (3,1)
    # ## ##   over the top to (3,4) is 10 tiles without a choice
    #.....#
    #######
    metrics = analyze(create_maze_registry().create("small"))

    assert metrics.to_dict() == {
        "height": 7,
        "width": 7,
        "walkable_tiles": 19,
        "walkable_fraction": 19 / 49,
        "regions": 1,
        "dead_ends": 1,
        "junctions": 3,
        "junction_share": 3 / 19,
        "loops": 2,
        "longest_straight_run": 5,
        "longest_corridor": 10,
        "largest_corridor_block": 1,
        "largest_wall_block": 1,
        "enclosed": True,
        "symmetric_horizontal": False,
        "symmetric_vertical": False,
        "pellets": 14,
    }


def test_classic_metrics() -> None:
    metrics = analyze(create_maze_registry().create("classic"))

    assert metrics.walkable_tiles == 300
    assert metrics.pellets == 244
    assert metrics.regions == 1
    # The two tunnel ends: no wrap-around yet.
    assert metrics.dead_ends == 2
    assert not metrics.enclosed
    assert metrics.symmetric_horizontal and not metrics.symmetric_vertical
    assert metrics.largest_corridor_block == 1


def test_saved_results_carry_maze_metrics(tmp_path) -> None:
    maze = create_maze_registry().create("small")
    result = run_simulation(
        engine=SimulationEngine(maze),
        controller=create_controller_registry().create("nearest-pellet", maze, 0),
        max_steps=50,
    )

    data = result.to_dict()
    assert data["maze"]["metrics"] == analyze(maze).to_dict()

    path = tmp_path / "run.json"
    result.save_json(path)
    assert SimulationResult.load_json(path).maze.initial_pellets == maze.initial_pellets
