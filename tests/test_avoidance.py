"""two-opt-avoid: the Level 1 danger check + flee controller."""

import pytest

from pacman_otm.controllers.algorithmic.tours.two_opt import TwoOptController
from pacman_otm.controllers.algorithmic.tours.two_opt_avoid import TwoOptAvoidController
from pacman_otm.controllers.ghosts.registry import create_ghosts
from pacman_otm.mazes.layout import parse_layout
from pacman_otm.mazes.registry import resolve_maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.ghosts import CAUGHT_REASON, GhostState
from pacman_otm.simulation.runner import run_simulation
from pacman_otm.simulation.speeds import ARCADE, EQUAL
from pacman_otm.simulation.state import SimulationState

# A ring. Pac-Man starts at a junction (right or down); the only pellet is at the end
# of the top corridor, behind the ghost's spawn. The short way runs into the ghost,
# the long way round leaves him behind.
RING = parse_layout(
    "#########\n"
    "#P    G.#\n"
    "# ##### #\n"
    "#       #\n"
    "#########\n",
    name="avoid-ring",
)


def head_on_state() -> SimulationState:
    """Pac-Man at the junction, Blinky two tiles up the corridor coming at him."""
    state = SimulationState(RING)
    state.ghosts = (GhostState(kind="blinky", position=(1, 4), heading=Action.LEFT),)
    return state


def test_turns_away_from_a_ghost_coming_head_on() -> None:
    plain = TwoOptController(RING)
    avoid = TwoOptAvoidController(RING)

    assert plain.select_action(head_on_state()) == Action.RIGHT
    assert avoid.select_action(head_on_state()) == Action.DOWN
    assert avoid.flee_count == 1
    assert avoid.describe()["avoidance"] == {"horizon": 6, "margin": 1, "flee_count": 1}


def test_safe_path_follows_the_tour() -> None:
    avoid = TwoOptAvoidController(RING)
    state = SimulationState(RING)
    # On the bottom corridor driving left: it comes round behind Pac-Man, too late for his path.
    state.ghosts = (GhostState(kind="blinky", position=(3, 4), heading=Action.LEFT),)

    assert avoid.select_action(state) == Action.RIGHT
    assert avoid.flee_count == 0


def run(controller_class, maze, speeds, ghosts: int):
    kinds = ["blinky"] * ghosts
    return run_simulation(
        engine=SimulationEngine(maze, kinds, speeds),
        controller=controller_class(maze),
        ghosts=create_ghosts(maze, kinds),
    )


@pytest.mark.parametrize("speeds", [EQUAL, ARCADE])
def test_flee_then_return_to_the_same_target(speeds) -> None:
    # Plain two-opt walks into the ghost; two-opt-avoid goes round and still eats
    # the pellet, which it could not if the flee had skipped its target.
    assert run(TwoOptController, RING, speeds, ghosts=1).states[-1].termination_reason == CAUGHT_REASON

    avoided = run(TwoOptAvoidController, RING, speeds, ghosts=1)
    assert avoided.states[-1].termination_reason == "completed"
    assert avoided.controller["avoidance"]["flee_count"] >= 1


def test_repath_keeps_the_target() -> None:
    avoid = TwoOptAvoidController(RING)
    state = head_on_state()
    avoid.select_action(state)
    target, order_index = avoid.current_target, avoid.order_index

    state.pacman_position = (2, 1)
    avoid._repath(state)

    assert (avoid.current_target, avoid.order_index) == (target, order_index)
    assert list(avoid.current_plan) == [Action.UP, *[Action.RIGHT] * 6]


def test_without_ghosts_plays_exactly_like_two_opt() -> None:
    maze = resolve_maze("classic", ghost_count=0)
    plain = run(TwoOptController, maze, ARCADE, ghosts=0)
    avoid = run(TwoOptAvoidController, maze, ARCADE, ghosts=0)

    assert avoid.actions == plain.actions
    assert avoid.states[-1].termination_reason == plain.states[-1].termination_reason == "completed"
    assert avoid.controller["avoidance"]["flee_count"] == 0
