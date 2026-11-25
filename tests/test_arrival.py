"""Arrival times (algorithms/safety/arrival.py) against real engine runs."""

import pytest

from pacman_otm.algorithms.pathfinding.no_reverse import NoReverseSearch
from pacman_otm.algorithms.safety.arrival import (
    earliest_ghost_ticks,
    ghost_occupancy_ticks,
    is_safe,
    pacman_occupancy_ticks,
)
from pacman_otm.mazes.layout import parse_layout
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.ghosts import GhostState
from pacman_otm.simulation.speeds import ARCADE, EASY, EQUAL, SpeedRules

L, R = Action.LEFT, Action.RIGHT
WIDTH = 50


def corridor(pellets: bool):
    """A straight corridor: the ghost spawn at column 1, Pac-Man at column 3, plus a spare pellet out of the way."""
    row = ["#"] + ["." if pellets else " "] * (WIDTH - 2) + ["#"]
    row[1], row[3] = "G", "P"
    wall = "#" * WIDTH
    spare = "#" + "." + "#" * (WIDTH - 2)
    return parse_layout("\n".join([wall, "".join(row), spare, wall, wall]) + "\n", name="arrival-corridor")


def run_right(engine: SimulationEngine, ticks: int) -> list:
    """Everyone drives right; returns the state copy at every tick (index = tick)."""
    states = [engine.state.copy()]

    for _ in range(ticks):
        if engine.state.terminated:
            break

        if engine.pacman_needs_decision():
            engine.decide_pacman(R)

        for index in range(len(engine.state.ghosts)):
            while engine.ghost_needs_decision(index):
                engine.decide_ghost(index, R)

        engine.advance()
        states.append(engine.state.copy())

    return states


def first_tick(states, start: int, occupied) -> dict:
    """For every tile, the first tick >= start at which `occupied(state)` is that tile."""
    seen = {}

    for tick in range(start, len(states)):
        seen.setdefault(occupied(states[tick]), tick - start)

    return seen


SPEEDS = [EASY, ARCADE, EQUAL, SpeedRules(ghost=11, pacman=13, pellet_pause=3)]


@pytest.mark.parametrize("speeds", SPEEDS)
def test_ghost_occupancy_matches_the_engine(speeds) -> None:
    maze = corridor(pellets=False)
    search = NoReverseSearch(maze)
    engine = SimulationEngine(maze, ["blinky"], speeds)
    # 40 ticks: the ghost stays well short of the far wall and of Pac-Man.
    states = run_right(engine, 40)
    cases = set()

    for start in range(0, 20):
        ghost = states[start].ghosts[0]
        cases.add((ghost.heading is None, ghost.next_heading is None, ghost.progress > 0))
        predicted = ghost_occupancy_ticks(search, maze, ghost, speeds)
        actual = first_tick(states, start, lambda state: state.ghost_occupied(0))

        for tile, tick in actual.items():
            # Only tiles ahead: in a corridor, the predicted earliest route is the one driven.
            if tile[1] >= ghost.position[1] and tick < len(states) - start - 2:
                assert predicted[tile] == tick, (speeds, start, ghost, tile)

    # The spawn, a committed exit, no exit yet, and leftover progress all came up.
    assert (True, True, False) in cases
    assert any(not heading and next_open for heading, next_open, _ in cases)
    # At full speed it reaches a centre every tick, so it is never seen mid-tile with an exit chosen.
    assert any(not heading and not next_open for heading, next_open, _ in cases) or speeds.ghost == speeds.move_cost
    assert any(progress for _, _, progress in cases) or speeds.ghost == speeds.move_cost


@pytest.mark.parametrize("speeds", SPEEDS)
def test_pacman_occupancy_matches_the_engine_with_pellet_pauses(speeds) -> None:
    maze = corridor(pellets=True)
    engine = SimulationEngine(maze, (), speeds)
    states = run_right(engine, 50)
    checked = 0

    for start in range(0, 25):
        state = states[start]

        if state.pacman_heading is not None:
            continue  # predictions are made at decisions, at a tile centre

        moves = [R] * 12
        predicted = pacman_occupancy_ticks(
            maze, state.pacman_position, state.pacman_progress, moves, state.remaining_pellets, speeds,
        )
        actual = first_tick(states, start, lambda s: s.pacman_occupied)

        for k, tick in enumerate(predicted):
            tile = (1, state.pacman_position[1] + k + 1)
            assert actual[tile] == tick, (speeds, start, tile)

        checked += 1

    assert checked >= 10


def test_ghost_occupancy_follows_the_commitment_and_its_own_tile() -> None:
    # A T junction: the ghost committed to turn down at (1, 4), so the corridor
    # to the right is reached only by... never (no reverse in the stem).
    maze = parse_layout(
        "#########\n"
        "#P      #\n"
        "#### ####\n"
        "#### ####\n"
        "#########\n",
        name="t",
    )
    search = NoReverseSearch(maze)
    ghost = GhostState(kind="blinky", position=(1, 3), heading=R, next_heading=Action.DOWN, progress=4)
    ticks = ghost_occupancy_ticks(search, maze, ghost, EQUAL)

    assert ticks[(1, 3)] == 0  # its own tile: not yet halfway out
    assert ticks[(1, 4)] == 1  # 4 + 16 >= 8
    assert ticks[(2, 4)] == 2
    # Down the stem, a dead end: it turns back, then may go either way.
    assert ticks[(3, 4)] == 3
    assert ticks[(1, 5)] == 6
    assert ticks[(1, 2)] == 7

    past_half = GhostState(kind="blinky", position=(1, 3), heading=R, next_heading=Action.DOWN, progress=9)
    assert ghost_occupancy_ticks(search, maze, past_half, EQUAL)[(1, 3)] > 0


def test_earliest_ghost_and_race() -> None:
    assert earliest_ghost_ticks([{(0, 0): 3, (0, 1): 5}, {(0, 1): 2}]) == {(0, 0): 3, (0, 1): 2}
    assert is_safe(2, None, 1)
    assert is_safe(2, 4, 1)
    assert not is_safe(2, 3, 1)
    assert is_safe(2, 3, 0)
