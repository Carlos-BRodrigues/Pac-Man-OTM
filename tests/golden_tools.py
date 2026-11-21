"""Helpers shared by the golden-result tests and the script that regenerates them."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from pacman_otm.controllers.registry import create_controller_registry
from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.result import SimulationResult
from pacman_otm.simulation.runner import run_simulation

GOLDEN_DIR = Path(__file__).parent / "golden"

# Timing varies between runs and machines, so it is never compared.
TIMING_FIELDS = ("elapsed_time_seconds", "controller_time_seconds")


def maze_factories() -> dict[str, Callable[[], Maze]]:
    """The only place the golden tests learn how mazes are built."""
    from pacman_otm.mazes.registry import create_maze_registry

    registry = create_maze_registry()

    return {
        "small": lambda: registry.create("small"),
        "classic": lambda: registry.create("classic"),
    }


# (golden file name, controller, maze, seed)
GOLDEN_CASES = [
    ("nearest-pellet_small", "nearest-pellet", "small", 42),
    ("nearest-pellet_classic", "nearest-pellet", "classic", 42),
    ("random-walk_small_seed7", "random-walk", "small", 7),
]


def run_case(controller_name: str, maze_name: str, seed: int) -> SimulationResult:
    maze = maze_factories()[maze_name]()
    controller = create_controller_registry().create(controller_name, maze, seed)

    return run_simulation(
        engine=SimulationEngine(maze),
        controller=controller,
        max_steps=1000,
    )


def summarize(result: SimulationResult) -> dict[str, Any]:
    """
    A compact, timing-free fingerprint of a run. The engine is deterministic,
    so positions plus pellet counts pin down the full history.
    """
    metrics = {
        key: value
        for key, value in result.metrics.to_dict().items()
        if key not in TIMING_FIELDS
    }

    return {
        "controller": result.controller,
        "actions": [action.value for action in result.actions],
        "states": [
            [
                list(state.pacman_position),
                state.steps,
                len(state.remaining_pellets),
                state.terminated,
                state.termination_reason,
            ]
            for state in result.states
        ],
        "status_targets": [
            None if status is None or status.target is None else list(status.target)
            for status in result.statuses
        ],
        "metrics": metrics,
    }
