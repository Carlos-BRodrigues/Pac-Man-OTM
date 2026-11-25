"""Movement speeds: ticks, progress, pellet pauses and collisions between speeds."""

import math

import pytest

from pacman_otm.controllers.registry import create_controller_registry
from pacman_otm.mazes.layout import parse_layout
from pacman_otm.mazes.registry import resolve_maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.ghosts import CAUGHT_REASON
from pacman_otm.simulation.runner import run_simulation
from pacman_otm.simulation.speeds import ARCADE, DEFAULT_SPEEDS, EASY, EQUAL, SPEED_PRESETS, SpeedRules, occupied_tile

L, R = Action.LEFT, Action.RIGHT


def corridor(pellets: bool, ghost_ahead: bool = False):
    """A long straight corridor; Pac-Man at column 6, the ghost spawn at column 1 (or at the far end)."""

    width = 60
    row = ["#"] + ["." if pellets else " "] * (width - 2) + ["#"]
    row[6] = "P"
    row[width - 2 if ghost_ahead else 1] = "G"
    wall = "#" * width
    # One spare pellet out of reach of nothing: the run must not complete.
    spare = "#" + "." + "#" * (width - 2)
    text = "\n".join([wall, "".join(row), spare, wall, wall]) + "\n"
    return parse_layout(text, name="corridor")


def run_ticks(engine: SimulationEngine, ticks: int, pacman: Action, ghost: Action) -> None:
    for _ in range(ticks):
        if engine.pacman_needs_decision():
            engine.decide_pacman(pacman)

        while engine.ghost_needs_decision(0):
            engine.decide_ghost(0, ghost)

        engine.advance()


def test_speed_rules_are_checked() -> None:
    with pytest.raises(ValueError, match="between 1 and move_cost"):
        SpeedRules(ghost=17)

    with pytest.raises(ValueError, match="pellet_pause"):
        SpeedRules(pellet_pause=-1)

    assert SpeedRules.from_dict(ARCADE.to_dict()) == ARCADE


def test_a_ghost_loses_ground_in_an_empty_corridor() -> None:
    engine = SimulationEngine(corridor(pellets=False), ["blinky"], ARCADE)
    run_ticks(engine, 32, R, R)

    # 32 ticks: Pac-Man 32 tiles, the ghost 32 * 15/16 = 30.
    assert engine.state.pacman_position == (1, 6 + 32)
    assert engine.state.ghosts[0].position == (1, 1 + 30)


def test_a_ghost_gains_ground_in_a_corridor_of_dots() -> None:
    engine = SimulationEngine(corridor(pellets=True), ["blinky"], ARCADE)
    run_ticks(engine, 36, R, R)

    # 36 ticks: Pac-Man 36 * 16/18 = 32 tiles (one pellet each), the ghost 36 * 15/16 = 33.75.
    assert engine.state.pacman_position == (1, 6 + 32)
    assert engine.state.ghosts[0].position == (1, 1 + 33)



def test_easy_ghost_loses_ground_even_in_a_corridor_of_dots() -> None:
    engine = SimulationEngine(corridor(pellets=True), ["blinky"], EASY)
    run_ticks(engine, 32, R, R)

    # Eating costs nothing: Pac-Man 32 tiles as in an empty corridor, the ghost 30.
    assert engine.state.pacman_position == (1, 6 + 32)
    assert engine.state.ghosts[0].position == (1, 1 + 30)


def test_easy_is_the_cli_default() -> None:
    assert SPEED_PRESETS[DEFAULT_SPEEDS] == EASY == SpeedRules(ghost=15, pellet_pause=0)

def test_decisions_only_at_tile_centres() -> None:
    engine = SimulationEngine(corridor(pellets=True), ["blinky"], ARCADE)
    asked = []

    for _ in range(20):
        asked.append(engine.pacman_needs_decision())
        run_ticks(engine, 1, R, R)

    moves = sum(1 for before, after in zip(engine.states, engine.states[1:]) if before.pacman_position != after.pacman_position)
    # Pac-Man is asked once per tile he starts, never in between.
    assert sum(asked) in (moves, moves + 1)
    assert engine.actions.count(None) == asked.count(False)


@pytest.mark.parametrize("spec", ["classic", "small", "classic-sparse"])
@pytest.mark.parametrize("controller", ["nearest-pellet", "nearest-pellet-tour"])
def test_ticks_follow_moves_and_pellets_exactly(spec, controller) -> None:
    """The pellet term is a constant, so the shortest tour is still the fastest."""

    maze = resolve_maze(spec, ghost_count=0)
    result = run_simulation(
        engine=SimulationEngine(maze, (), ARCADE),
        controller=create_controller_registry().create(controller, maze, 0),
    )
    metrics = result.metrics

    assert metrics.completed
    # The last pellet's pause never has to be paid: the run ends on it.
    units = ARCADE.move_cost * metrics.pacman_moves + ARCADE.pellet_pause * (metrics.initial_pellets - 1)
    assert metrics.total_steps == math.ceil(units / ARCADE.pacman)


def test_equal_speeds_take_one_tick_per_tile() -> None:
    maze = resolve_maze("classic", ghost_count=0)
    result = run_simulation(
        engine=SimulationEngine(maze, (), EQUAL),
        controller=create_controller_registry().create("nearest-pellet", maze, 0),
    )

    assert result.metrics.total_steps == result.metrics.pacman_moves == 335
    assert None not in result.actions


def test_occupied_tile_switches_halfway() -> None:
    assert occupied_tile((1, 1), R, 7, 16) == (1, 1)
    assert occupied_tile((1, 1), R, 8, 16) == (1, 2)
    assert occupied_tile((1, 1), None, 12, 16) == (1, 1)
    assert occupied_tile((1, 1), R, -2, 16) == (1, 1)


def test_head_on_at_different_speeds_is_caught_before_passing() -> None:
    engine = SimulationEngine(corridor(pellets=False, ghost_ahead=True), ["blinky"], ARCADE)
    distances = []

    while not engine.state.terminated:
        run_ticks(engine, 1, R, L)
        pacman = engine.state.pacman_point
        ghost = engine.state.ghost_point(0)
        distances.append(ghost[1] - pacman[1])

    assert engine.state.termination_reason == CAUGHT_REASON
    # They never passed each other: the ghost was always ahead (or level) when caught.
    assert all(distance >= -1 for distance in distances)
    assert distances[-1] <= 1


@pytest.mark.parametrize("seed", range(6))
def test_no_ghost_passes_through_pacman(seed) -> None:
    """At arcade speeds, whenever a ghost's and Pac-Man's tracks cross, the run ends there."""

    from pacman_otm.controllers.ghosts.registry import create_ghosts, ghost_lineup

    maze = resolve_maze("classic", ghost_count=4, maze_seed=seed)
    kinds = ghost_lineup(maze)
    result = run_simulation(
        engine=SimulationEngine(maze, kinds, ARCADE),
        controller=create_controller_registry().create("random-walk", maze, seed),
        ghosts=create_ghosts(maze, kinds),
        max_steps=600,
    )

    for before, after in zip(result.states, result.states[1:]):
        if after.terminated:
            break

        for index in range(len(after.ghosts)):
            # Not on the same occupied tile, and not swapped, unless the run ended.
            assert after.ghost_occupied(index) != after.pacman_occupied
            assert not (
                after.ghost_occupied(index) == before.pacman_occupied
                and before.ghost_occupied(index) == after.pacman_occupied
            )
