"""two-opt-safe: the Level 2 controller (next.md)."""

import pytest

from pacman_otm.controllers.algorithmic.tours.two_opt import TwoOptController
from pacman_otm.controllers.algorithmic.tours.two_opt_safe import TwoOptSafeController
from pacman_otm.controllers.ghosts.registry import create_ghosts
from pacman_otm.mazes.layout import parse_layout
from pacman_otm.mazes.registry import resolve_maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.ghosts import GhostState
from pacman_otm.simulation.runner import run_simulation
from pacman_otm.simulation.speeds import ARCADE, EASY, EQUAL
from pacman_otm.simulation.state import SimulationState

U, L, D, R = Action.UP, Action.LEFT, Action.DOWN, Action.RIGHT

# The ring from test_avoidance: the only pellet is up the top corridor, past the ghost spawn.
RING = parse_layout(
    "#########\n"
    "#P    G.#\n"
    "# ##### #\n"
    "#       #\n"
    "#########\n",
    name="safe-ring",
)

# A ring with two pellets: B near Pac-Man on the top, A in the middle of the bottom.
TWO_PELLETS = parse_layout(
    "#########\n"
    "#P .    #\n"
    "# ##### #\n"
    "#   .   #\n"
    "#########\n",
    name="two-pellets",
)
A, B = (3, 4), (1, 3)


def state_with(maze, *ghosts: GhostState, speeds=EASY) -> SimulationState:
    state = SimulationState(maze, speeds)
    state.ghosts = ghosts
    return state


def blinky(position, heading, next_heading=None, progress=0) -> GhostState:
    return GhostState(kind="blinky", position=position, heading=heading, next_heading=next_heading, progress=progress)


def run(controller, maze, speeds, ghosts: int):
    kinds = ["blinky"] * ghosts
    return run_simulation(
        engine=SimulationEngine(maze, kinds, speeds),
        controller=controller,
        ghosts=create_ghosts(maze, kinds),
    )


def test_takes_the_long_way_to_the_same_target() -> None:
    safe = TwoOptSafeController(RING)
    action = safe.select_action(state_with(RING, blinky((1, 4), L)))
    status = safe.get_status()

    assert action == D
    assert safe.current_target == (1, 7)
    assert status.target == (1, 7)
    assert status.planned_path[0] == (2, 1) and status.planned_path[-1] == (1, 7)
    assert safe.detours == 0


def test_eats_another_tour_pellet_when_the_target_is_cut_off_and_comes_back() -> None:
    safe = TwoOptSafeController(TWO_PELLETS)
    safe._plan()
    nodes = safe.closure.nodes
    # Force the tour to want A first, with B second.
    safe.order = [0, nodes.index(A), nodes.index(B)]

    # One ghost comes along the top toward Pac-Man (B is still won), one is on the
    # bottom heading for the left column: A is cut off both ways.
    state = state_with(TWO_PELLETS, blinky((1, 7), L), blinky((3, 2), L))
    action = safe.select_action(state)

    assert action == R
    assert safe.get_status().target == B
    assert (safe.current_target, safe.detours) == (A, 1)
    order_index = safe.order_index

    # B eaten and the ghosts gone: the pending target A is taken up again.
    later = state_with(TWO_PELLETS)
    later.pacman_position = B
    later.remaining_pellets = {A}
    action = safe.select_action(later)

    assert safe.current_target == A
    assert safe.order_index == order_index
    assert action == L


@pytest.mark.parametrize("speeds", [EASY, EQUAL, ARCADE])
def test_completes_the_ring(speeds) -> None:
    result = run(TwoOptSafeController(RING), RING, speeds, ghosts=1)

    assert result.states[-1].termination_reason == "completed"


@pytest.mark.parametrize("speeds", [EASY, ARCADE])
def test_without_ghosts_plays_exactly_like_two_opt(speeds) -> None:
    maze = resolve_maze("classic", ghost_count=0)
    plain = run(TwoOptController(maze), maze, speeds, ghosts=0)
    safe = run(TwoOptSafeController(maze), maze, speeds, ghosts=0)

    assert safe.actions == plain.actions
    assert safe.controller["avoidance"]["flee_count"] == 0


# A ring with a spur hanging down from (3, 3); the only pellets are in the spur.
SPUR = parse_layout(
    "#########\n"
    "#P      #\n"
    "# ##### #\n"
    "#       #\n"
    "###.#####\n"
    "###.#####\n"
    "#########\n",
    name="spur",
)


def spur_maze():
    maze = SPUR
    assert set(maze.initial_pellets) == {(4, 3), (5, 3)}
    return maze


def test_a_dead_end_pellet_is_skipped_while_a_ghost_nears_the_entrance() -> None:
    maze = spur_maze()

    # A ghost 6 tiles from the entrance (3, 3): Pac-Man would get in, but not back out.
    near = TwoOptSafeController(maze)
    action = near.select_action(state_with(maze, blinky((1, 7), D)))

    assert near.get_status().target not in {(4, 3), (5, 3)}
    assert near.escapes == 1

    # The same ghost driving away along the top: in and out in time, so he goes for it.
    far = TwoOptSafeController(maze)
    action = far.select_action(state_with(maze, blinky((1, 2), R)))

    assert action == D
    assert far.current_target in {(4, 3), (5, 3)}
    assert far.escapes == 0 and far.flee_count == 0


def test_leaves_a_corridor_through_the_junction_when_ghosts_close_both_ends() -> None:
    maze = parse_layout(
        "###########\n"
        "#    P   .#\n"
        "# ### ### #\n"
        "#         #\n"
        "###########\n",
        name="pincer",
    )
    state = state_with(maze, blinky((1, 2), R), blinky((1, 8), L))

    assert TwoOptController(maze).select_action(state) == R
    assert TwoOptSafeController(maze).select_action(state) == D


def test_replan_orders_exactly_the_remaining_pellets_from_pacman() -> None:
    from pacman_otm.algorithms.pathfinding.bfs import BreadthFirstSearch

    maze = resolve_maze("classic", ghost_count=0)
    safe = TwoOptSafeController(maze)
    safe._plan()
    nodes = safe.closure.nodes

    # Pac-Man somewhere else, a third of the pellets eaten.
    state = state_with(maze)
    state.pacman_position = (23, 3)
    state.remaining_pellets = set(sorted(maze.initial_pellets)[::3]) - {(23, 3)}
    full = list(safe.order)
    safe._replan(state)

    new = [nodes[index] for index in safe.order[safe.order_index:]]
    assert sorted(safe.order) == sorted(full)
    assert set(new) == state.remaining_pellets and len(new) == len(state.remaining_pellets)

    distances = BreadthFirstSearch().distances_from(maze, state.pacman_position)
    assert distances[new[0]] == min(distances[pellet] for pellet in state.remaining_pellets)
    assert safe.replans == 1 and safe.current_target is None


@pytest.mark.parametrize("replan", [True, False])
def test_replanning_can_be_turned_off(replan) -> None:
    maze = resolve_maze("cool_1_ghost_duel", ghost_count=2)
    result = run(TwoOptSafeController(maze, replan=replan), maze, EASY, ghosts=2)
    avoidance = result.controller["avoidance"]

    assert avoidance["replan"] is replan
    assert (avoidance["replans"] > 0) is replan
