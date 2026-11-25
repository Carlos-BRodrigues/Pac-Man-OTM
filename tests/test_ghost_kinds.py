"""Pinky, Inky and Clyde, lineups, per-kind spawns, the ghost house and the classic tunnel."""

import pytest

from pacman_otm.algorithms.graph.nearest import NearestTile
from pacman_otm.algorithms.pathfinding.bfs import BreadthFirstSearch
from pacman_otm.algorithms.pathfinding.no_reverse import NoReverseSearch
from pacman_otm.controllers.ghosts.clyde import Clyde
from pacman_otm.controllers.ghosts.inky import Inky
from pacman_otm.controllers.ghosts.pinky import Pinky
from pacman_otm.controllers.ghosts.registry import default_lineup, ghost_lineup, validate_lineup
from pacman_otm.mazes.generation.pipeline import assign_ghost_spawns
from pacman_otm.mazes.layout import format_layout, parse_layout
from pacman_otm.mazes.registry import create_maze_registry
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.encoding import decode_arrivals, encode_arrivals
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.ghosts import CAUGHT_REASON, GhostState
from pacman_otm.simulation.speeds import EQUAL
from pacman_otm.simulation.state import SimulationState

U, L, D, R = Action.UP, Action.LEFT, Action.DOWN, Action.RIGHT


@pytest.fixture(scope="module")
def classic():
    return create_maze_registry().create("classic")


def state_with(maze, pacman, facing, ghosts) -> SimulationState:
    state = SimulationState(maze)
    state.pacman_position = pacman
    state.pacman_facing = facing
    state.ghosts = tuple(GhostState(kind=kind, position=position) for kind, position in ghosts)
    return state


# Facing


def test_facing_starts_left_follows_moves_and_survives_a_wall(classic) -> None:
    engine = SimulationEngine(classic, speeds=EQUAL)
    assert engine.state.pacman_facing == L

    engine.step(R)
    assert engine.state.pacman_facing == R

    engine.step(D)  # (23,14) has a wall below: blocked, still facing right
    assert engine.state.pacman_position == (23, 14) and engine.state.pacman_facing == R


# Targets


def test_nearest_tile_projects_walls_void_and_off_grid_points(classic) -> None:
    nearest = NearestTile(classic)

    assert nearest((23, 13)) == (23, 13)
    assert nearest((0, 0)) == (1, 1)
    assert nearest((-7, -3)) == (1, 1)
    assert nearest((40, 30)) == (29, 26)
    # (2,2) is a wall equally near (1,2) and (2,1): reading order wins.
    assert nearest((2, 2)) == (1, 2)


def test_pinky_aims_four_ahead_and_straight_up(classic) -> None:
    pinky = Pinky(classic, 0)

    assert pinky.target(state_with(classic, (23, 13), U, [("pinky", (5, 1))])) == (19, 13)
    assert pinky.target(state_with(classic, (23, 13), L, [("pinky", (5, 1))])) == (23, 9)


def test_inky_aims_at_twice_two_ahead_minus_blinky(classic) -> None:
    inky = Inky(classic, 1)
    state = state_with(classic, (23, 13), R, [("blinky", (20, 10)), ("inky", (5, 1))])

    assert inky.target(state) == (26, 20)

    # Far off the grid: steering uses the nearest corridor tile, the status keeps both.
    state = state_with(classic, (29, 1), D, [("blinky", (1, 26)), ("inky", (5, 1))])
    assert inky.target(state) == (61, -24)
    assert inky.nearest(inky.target(state)) == (29, 1)

    with pytest.raises(RuntimeError, match="Blinky"):
        inky.target(state_with(classic, (23, 13), R, [("inky", (5, 1))]))


def test_clyde_chases_beyond_eight_tiles_and_flees_to_his_corner(classic) -> None:
    clyde = Clyde(classic, 0)

    assert clyde.corner == (29, 1)
    assert clyde.target(state_with(classic, (23, 13), L, [("clyde", (15, 13))])) == (29, 1)  # d2 = 64
    assert clyde.target(state_with(classic, (23, 13), L, [("clyde", (15, 12))])) == (23, 13)  # d2 = 65


# Lineups and spawns


def test_lineups(classic) -> None:
    assert default_lineup(2) == ("blinky", "pinky")
    assert default_lineup(5) == ("blinky", "pinky", "inky", "clyde", "blinky")
    assert ghost_lineup(classic) == ("blinky", "inky", "pinky", "clyde")

    with pytest.raises(ValueError, match="Blinky"):
        validate_lineup(("pinky", "inky"))

    with pytest.raises(ValueError, match="Unknown"):
        validate_lineup(("sue",))


def test_spawn_assignment_stages(classic) -> None:
    # Own kind first, whatever the order of the lineup.
    maze = assign_ghost_spawns(classic, ("pinky", "blinky"), seed=0)
    assert maze.ghost_spawns == ((14, 13), (11, 13))
    assert ghost_lineup(maze) == ("pinky", "blinky")

    # A spawn for a kind not in the run serves any ghost; then seeded random ones.
    maze = assign_ghost_spawns(classic, ("blinky",) * 6, seed=4)
    assert maze.ghost_spawns[:4] == classic.ghost_spawns
    assert len(set(maze.ghost_spawns)) == 6
    assert maze.ghost_spawns == assign_ghost_spawns(classic, ("blinky",) * 6, seed=4).ghost_spawns


def test_layout_spawn_letters_round_trip_and_house_spawns_have_no_pellets() -> None:
    text = (
        "#########\n"
        "#P.b...K#\n"
        "#.##-##.#\n"
        "#.#HIH#.#\n"
        "#.#####.#\n"
        "#...c...#\n"
        "#########\n"
    )
    maze = parse_layout(text, name="letters")

    assert maze.ghost_spawns == ((1, 3), (1, 7), (3, 4), (5, 4))
    assert maze.ghost_spawn_kinds == ("blinky", "pinky", "inky", "clyde")
    assert maze.ghost_moves((3, 4)) == {U: (2, 4), L: (3, 3), R: (3, 5)}
    assert format_layout(maze) == text

    with pytest.raises(ValueError, match="house"):
        parse_layout(text.replace("#HIH#", "#HiH#"), name="bad")


# The ghost house


def test_the_gate_is_one_way_and_pacman_never_enters(classic) -> None:
    assert D not in classic.ghost_moves((11, 13))  # corridor -> gate
    assert D not in classic.ghost_moves((12, 13))  # gate -> house
    assert U in classic.ghost_moves((13, 13))  # house -> gate
    assert D not in classic.get_valid_movements((11, 13))
    assert not classic.is_walkable((14, 13))

    path = NoReverseSearch(classic).find_path((14, 15), None, (23, 13))
    tiles = [(14, 15)]

    for action in path:
        tiles.append(classic.get_destination(tiles[-1], action))

    gate = next(index for index, tile in enumerate(tiles) if tile in ((12, 13), (12, 14)))
    # Out through the gate, and only corridors after it.
    assert all(classic.is_walkable(tile) for tile in tiles[gate + 1:])


# The tunnel


def test_tunnel_wraps_for_movement_occupancy_paths_and_saved_arrivals(classic) -> None:
    assert classic.get_destination((14, 0), L) == (14, 27)
    assert classic.get_destination((14, 27), R) == (14, 0)
    assert BreadthFirstSearch().find_path(classic, (14, 1), (14, 26)) == [L, L, L]

    state = SimulationState(classic)
    state.pacman_position, state.pacman_heading, state.pacman_progress = (14, 0), L, 8
    assert state.pacman_occupied == (14, 27)
    assert state.pacman_point == (14.0, -0.5)

    positions = [(14, 1), (14, 0), (14, 27), (14, 27), (14, 0)]
    text = encode_arrivals(positions, classic)
    assert text == "LL.R"
    assert decode_arrivals((14, 1), text, classic) == positions


def test_a_ghost_catches_pacman_in_the_tunnel(classic) -> None:
    engine = SimulationEngine(classic, ("blinky",), speeds=EQUAL)
    engine.state.pacman_position = (14, 0)
    engine.state.ghosts = (GhostState(kind="blinky", position=(14, 26), heading=R, next_heading=R),)

    engine.step(L)

    assert engine.state.termination_reason == CAUGHT_REASON
