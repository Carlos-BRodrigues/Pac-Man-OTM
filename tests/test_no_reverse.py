import pytest

from pacman_otm.algorithms.pathfinding.bfs import BreadthFirstSearch
from pacman_otm.algorithms.pathfinding.no_reverse import NoReverseSearch, reverse
from pacman_otm.mazes.layout import parse_layout
from pacman_otm.mazes.registry import create_maze_registry
from pacman_otm.simulation.actions import Action

U, L, D, R = Action.UP, Action.LEFT, Action.DOWN, Action.RIGHT

# A ring around one wall block: every tile has two exits.
RING = parse_layout(
    "#####\n"
    "#P  #\n"
    "# # #\n"
    "#   #\n"
    "#####\n",
    name="ring",
)

# A dead-end corridor.
CORRIDOR = parse_layout(
    "#######\n"
    "#######\n"
    "#P    #\n"
    "#######\n"
    "#######\n",
    name="corridor",
)


def walk(maze, start, actions):
    position = start

    for action in actions:
        position = maze.get_destination(position, action)
        assert maze.is_walkable(position)

    return position


def test_reverse() -> None:
    assert [reverse(action) for action in (U, L, D, R)] == [D, R, U, L]


def test_target_behind_goes_around_the_loop() -> None:
    search = NoReverseSearch(RING)

    # At (1, 2) having moved RIGHT, the tile behind, (1, 1), is 1 step back but
    # the mover may not reverse: it must go all the way round.
    path = search.find_path((1, 2), R, (1, 1))

    assert path == [R, D, D, L, L, U, U]
    assert BreadthFirstSearch().find_path(RING, (1, 2), (1, 1)) == [L]


def test_no_heading_allows_any_first_move() -> None:
    assert NoReverseSearch(RING).find_path((1, 2), None, (1, 1)) == [L]


def test_dead_end_allows_the_reverse() -> None:
    search = NoReverseSearch(CORRIDOR)

    assert search.legal_moves((2, 5), R) == (L,)
    assert search.find_path((2, 4), R, (2, 1)) == [R, L, L, L, L]


def test_legal_moves_exclude_the_reverse_only() -> None:
    search = NoReverseSearch(RING)

    # Corner (1, 1): exits DOWN and RIGHT. Entered moving LEFT, it may not go RIGHT.
    assert search.legal_moves((1, 1), L) == (D,)
    assert search.legal_moves((1, 1), None) == (D, R)


def test_ties_go_to_movements_order() -> None:
    # From the top-middle with no heading, the bottom-middle is 4 steps either way
    # round: LEFT comes before RIGHT in MOVEMENTS order.
    assert NoReverseSearch(RING).find_path((1, 2), None, (3, 2))[0] == L


def test_start_is_goal() -> None:
    assert NoReverseSearch(RING).find_path((1, 1), R, (1, 1)) == []


@pytest.mark.parametrize("maze_name", ["classic", "small"])
def test_paths_are_legal_and_never_shorter_than_bfs(maze_name) -> None:
    maze = create_maze_registry().create(maze_name)
    search = NoReverseSearch(maze)
    bfs = BreadthFirstSearch()
    positions = maze.walkable_positions()

    for start in positions[::7]:
        for heading in (None, *maze.get_valid_movements(start)):
            for goal in positions[::11]:
                path = search.find_path(start, heading, goal)

                assert path is not None
                assert walk(maze, start, path) == goal
                assert len(path) >= len(bfs.find_path(maze, start, goal))

                previous = heading

                for action in path:
                    if previous is not None and action == reverse(previous):
                        position_before = walk(maze, start, path[: path.index(action)])
                        assert search.legal_moves(position_before, previous) == (action,)

                    previous = action
