"""Ghost movement and the game rules around ghosts."""

import pytest

from pacman_otm.controllers.ghosts.blinky import Blinky
from pacman_otm.controllers.ghosts.registry import create_ghosts, ghost_lineup
from pacman_otm.controllers.registry import create_controller_registry
from pacman_otm.mazes.layout import parse_layout
from pacman_otm.mazes.registry import resolve_maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.ghosts import CAUGHT_REASON, GhostState
from pacman_otm.simulation.runner import run_simulation
from pacman_otm.simulation.state import SimulationState

U, L, D, R = Action.UP, Action.LEFT, Action.DOWN, Action.RIGHT

RING = parse_layout(
    "#######\n"
    "#P  G #\n"
    "# ### #\n"
    "#.....#\n"
    "#######\n",
    name="ring",
)

# A T junction: a horizontal corridor and a stem down to the ghost's spawn.
T_JUNCTION = parse_layout(
    "#########\n"
    "#P.     #\n"
    "#### ####\n"
    "#### ####\n"
    "####G####\n"
    "#########\n",
    name="t-junction",
)


def test_engine_places_ghosts_on_their_spawns() -> None:
    engine = SimulationEngine(RING, ["blinky"])

    assert engine.state.ghosts == (GhostState(kind="blinky", position=(1, 4)),)

    with pytest.raises(ValueError, match="ghost spawn"):
        SimulationEngine(RING, ["blinky", "blinky"])


def test_caught_on_the_same_tile() -> None:
    engine = SimulationEngine(RING, ["blinky"])

    engine.step(R, [L])  # Pac-Man (1, 2), ghost (1, 3): neighbours are safe
    assert not engine.state.terminated

    engine.step(U, [L])  # Pac-Man blocked at (1, 2), ghost arrives there
    assert engine.state.termination_reason == CAUGHT_REASON


def test_caught_when_swapping_tiles_head_on() -> None:
    engine = SimulationEngine(RING, ["blinky"])

    engine.step(R, [L])
    engine.step(R, [L])  # Pac-Man (1, 2) -> (1, 3), ghost (1, 3) -> (1, 2)

    assert engine.state.pacman_position == (1, 3)
    assert engine.state.ghosts[0].position == (1, 2)
    assert engine.state.termination_reason == CAUGHT_REASON


def test_caught_beats_eating_the_last_pellet() -> None:
    maze = parse_layout(
        "#######\n"
        "#P.G  #\n"
        "# ### #\n"
        "#     #\n"
        "#######\n",
        name="last-pellet",
    )
    engine = SimulationEngine(maze, ["blinky"])
    engine.step(R, [L])

    assert not engine.state.remaining_pellets
    assert engine.state.termination_reason == CAUGHT_REASON


def test_engine_rejects_illegal_ghost_moves() -> None:
    engine = SimulationEngine(RING, ["blinky"])

    with pytest.raises(RuntimeError, match="wall"):
        engine.step(R, [U])

    engine.step(D, [L])

    with pytest.raises(RuntimeError, match="reverse"):
        engine.step(D, [R])

    with pytest.raises(ValueError, match="ghost action"):
        engine.step(D, [])


def test_dead_end_is_the_only_place_to_reverse() -> None:
    engine = SimulationEngine(T_JUNCTION, ["blinky"])
    engine.step(U, [U])  # Pac-Man stays at (1, 1) against the wall

    with pytest.raises(RuntimeError, match="reverse"):
        engine.step(U, [D])  # (3, 4) has two exits

    for move in (U, U, R, R, R):
        engine.step(U, [move])

    assert engine.state.ghosts[0].position == (1, 7)
    engine.step(U, [L])  # (1, 7) is a dead end: turning back is allowed
    assert engine.state.ghosts[0] == GhostState(kind="blinky", position=(1, 6), direction=L)


def _state(maze, pacman, ghost_position, direction):
    state = SimulationState(maze)
    state.pacman_position = pacman
    state.ghosts = (GhostState(kind="blinky", position=ghost_position, direction=direction),)
    return state


def test_ghost_commits_one_tile_ahead_and_can_be_juked() -> None:
    ghost = Blinky(T_JUNCTION, 0)

    # At the spawn: the first move is free; the stem is a corridor, so forced.
    assert ghost.select_action(_state(T_JUNCTION, (1, 1), (4, 4), None)) == U
    assert ghost.select_action(_state(T_JUNCTION, (1, 1), (3, 4), U)) == U

    # Moving onto the junction (1, 4): it chooses the exit now, from Pac-Man on the left.
    assert ghost.select_action(_state(T_JUNCTION, (1, 1), (2, 4), U)) == U
    status = ghost.get_status()
    assert status.decided
    assert status.decision_tile == (1, 4)
    assert status.options == (L, R)
    assert status.decision == L

    # Pac-Man is now on the right, but the decision is final: the ghost goes left.
    assert ghost.select_action(_state(T_JUNCTION, (1, 7), (1, 4), U)) == L
    assert not ghost.get_status().decided


def test_ghost_status_path_is_the_shortest_legal_path() -> None:
    ghost = Blinky(T_JUNCTION, 0)
    ghost.select_action(_state(T_JUNCTION, (1, 1), (4, 4), None))
    status = ghost.get_status()

    assert status.target == (1, 1)
    assert status.planned_path == ((3, 4), (2, 4), (1, 4), (1, 3), (1, 2), (1, 1))


def test_without_status_collection_the_ghost_moves_the_same() -> None:
    maze = resolve_maze("classic", ghost_count=4, maze_seed=2)
    kinds = ghost_lineup(maze)

    def run(collect: bool):
        ghosts = create_ghosts(maze, kinds)

        for ghost in ghosts:
            ghost.set_status_collection(collect)

        return run_simulation(
            engine=SimulationEngine(maze, kinds),
            controller=create_controller_registry().create("random-walk", maze, 3),
            ghosts=ghosts,
            max_steps=300,
        )

    with_status, without = run(True), run(False)

    assert [state.ghosts for state in with_status.states] == [state.ghosts for state in without.states]
    assert all(status is None for step in without.ghost_statuses for status in step)


def legal_ghost_tracks(result, maze) -> None:
    """Every ghost moves one tile each step and reverses only at dead ends."""

    for before, after in zip(result.states, result.states[1:]):
        for ghost_before, ghost_after in zip(before.ghosts, after.ghosts):
            exits = maze.get_valid_movements(ghost_before.position)
            assert exits[ghost_after.direction] == ghost_after.position

            if ghost_before.direction is not None and ghost_after.direction == ghost_before.direction.reverse:
                assert len(exits) == 1


@pytest.mark.parametrize(
    ("spec", "seed"),
    [("classic", 0), ("classic", 1), ("twisty", 3), ("organic", 5), ("open-lattice", 9)],
)
def test_ghost_tracks_are_legal_over_many_runs(spec, seed) -> None:
    maze = resolve_maze(spec, maze_seed=seed, ghost_count=4)
    kinds = ghost_lineup(maze)

    for controller_seed in range(8):
        result = run_simulation(
            engine=SimulationEngine(maze, kinds),
            controller=create_controller_registry().create("random-walk", maze, controller_seed),
            ghosts=create_ghosts(maze, kinds),
            max_steps=500,
        )
        legal_ghost_tracks(result, maze)
        assert len(result.ghost_statuses) == len(result.actions)


def test_blinky_catches_nearest_pellet_on_classic() -> None:
    maze = resolve_maze("classic")
    kinds = ghost_lineup(maze)

    result = run_simulation(
        engine=SimulationEngine(maze, kinds),
        controller=create_controller_registry().create("nearest-pellet", maze, 42),
        ghosts=create_ghosts(maze, kinds),
    )

    assert kinds == ("blinky",)
    assert result.metrics.termination_reason == CAUGHT_REASON
    assert result.ghosts == [{"type": "ghost", "class": "Blinky", "kind": "blinky", "ghost_index": 0}]


def test_runner_checks_the_number_of_ghost_controllers() -> None:
    with pytest.raises(ValueError, match="ghost controller"):
        run_simulation(
            engine=SimulationEngine(RING, ["blinky"]),
            controller=create_controller_registry().create("random-walk", RING, 0),
        )
