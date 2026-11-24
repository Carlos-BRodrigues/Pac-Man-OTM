from itertools import permutations

import numpy as np
import pytest

from pacman_otm.algorithms.graph.metric_closure import MetricClosure
from pacman_otm.algorithms.graph.mst import mst_weight
from pacman_otm.algorithms.tours.held_karp import TourTooLargeError, held_karp_tour
from pacman_otm.algorithms.tours.nearest_neighbour import nearest_neighbour_tour
from pacman_otm.algorithms.tours.tour import tour_length
from pacman_otm.algorithms.tours.two_opt import two_opt
from pacman_otm.controllers.registry import create_controller_registry
from pacman_otm.mazes.registry import resolve_maze
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.runner import run_simulation


def random_metric(seed: int, nodes: int = 7) -> np.ndarray:
    """Distances between random points on a grid (Manhattan): symmetric and metric."""
    points = np.random.default_rng(seed).integers(0, 20, size=(nodes, 2))
    return np.abs(points[:, None, :] - points[None, :, :]).sum(axis=2).astype(float)


def brute_force_length(distances: np.ndarray) -> float:
    rest = range(1, len(distances))
    return min(tour_length(distances, [0, *order]) for order in permutations(rest))


def test_mst_weight_of_a_known_matrix() -> None:
    # A path 0-1-2-3 with weights 1, 2, 3; every other edge is 10.
    distances = np.full((4, 4), 10.0)
    np.fill_diagonal(distances, 0)
    for a, b, w in [(0, 1, 1), (1, 2, 2), (2, 3, 3)]:
        distances[a, b] = distances[b, a] = w

    assert mst_weight(distances) == 6


@pytest.mark.parametrize("seed", range(8))
def test_held_karp_is_optimal_and_bounds_hold(seed: int) -> None:
    distances = random_metric(seed)
    optimal = held_karp_tour(distances)
    nearest = nearest_neighbour_tour(distances)
    improved = two_opt(distances, nearest)

    assert sorted(improved) == list(range(len(distances))) and improved[0] == 0
    assert tour_length(distances, optimal) == brute_force_length(distances)
    assert mst_weight(distances) <= tour_length(distances, optimal)
    assert (
        tour_length(distances, optimal)
        <= tour_length(distances, improved)
        <= tour_length(distances, nearest)
    )


def test_held_karp_refuses_large_mazes() -> None:
    with pytest.raises(TourTooLargeError, match="at most 16"):
        create_controller_registry().create("held-karp", resolve_maze("classic"))


def test_nearest_neighbour_matches_nearest_pellet_tour_targets() -> None:
    maze = resolve_maze("classic")
    closure = MetricClosure(maze)
    order = nearest_neighbour_tour(closure.distances)

    controller = create_controller_registry().create("nearest-pellet-tour", maze)
    targets = []
    engine = SimulationEngine(maze)
    while not engine.state.terminated:
        if engine.pacman_needs_decision():
            engine.decide_pacman(controller.select_action(engine.state))

            if not targets or targets[-1] != controller.current_target:
                targets.append(controller.current_target)

        engine.advance()

    # The online controller skips nothing: each target is the nearest from the last one.
    assert targets == [closure.nodes[node] for node in order[1:]]


@pytest.mark.parametrize(
    "controller, spec",
    [
        ("held-karp", "classic-sparse"),
        ("two-opt", "classic-sparse"),
        ("two-opt", "classic"),
        ("two-opt", "classic-like1"),
        ("nearest-pellet-tour", "classic-sparse"),
    ],
)
def test_tour_controllers_complete_and_report(controller: str, spec: str) -> None:
    maze = resolve_maze(spec)
    result = run_simulation(
        SimulationEngine(maze),
        create_controller_registry().create(controller, maze),
        max_steps=20000,
    )
    tour = result.controller["tour"]

    assert result.metrics.completed
    # The path walked is never longer than the planned tour (time also counts pellet pauses).
    assert result.metrics.pacman_moves <= tour["tour_length"]
    assert tour["pellets"] == len(maze.initial_pellets)

    if controller != "held-karp":
        assert tour["lower_bound"] <= tour["tour_length"]
        assert tour["gap_percent"] >= 0

    if controller == "two-opt":
        assert tour["tour_length"] <= tour["nn_length"]
        assert tour["improvement_percent"] >= 0


def test_held_karp_is_no_longer_than_two_opt_on_classic_sparse() -> None:
    maze = resolve_maze("classic-sparse")
    lengths = {}
    for name in ("held-karp", "two-opt"):
        result = run_simulation(
            SimulationEngine(maze), create_controller_registry().create(name, maze)
        )
        lengths[name] = result.controller["tour"]["tour_length"]

    assert lengths["held-karp"] <= lengths["two-opt"]
