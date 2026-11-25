"""The measuring tools behind two-opt-safe: safe routes, dead-end branches, BFS distances."""

import pytest

from pacman_otm.algorithms.graph.dead_ends import Branch, dead_end_branches
from pacman_otm.algorithms.pathfinding.bfs import BreadthFirstSearch
from pacman_otm.algorithms.pathfinding.safe_route import safe_routes
from pacman_otm.mazes.layout import parse_layout
from pacman_otm.mazes.registry import resolve_maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.speeds import ARCADE, EASY

R = Action.RIGHT

# A ring with a spur of two tiles hanging down from (3, 3).
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


@pytest.mark.parametrize("maze_name", ["classic", "small"])
def test_bfs_distances_match_find_path(maze_name) -> None:
    maze = resolve_maze(maze_name, ghost_count=0)
    bfs = BreadthFirstSearch()
    start = maze.pacman_start
    distances = bfs.distances_from(maze, start)

    assert set(distances) == set(maze.walkable_positions())

    for goal in maze.walkable_positions()[::5]:
        assert distances[goal] == len(bfs.find_path(maze, start, goal))


def test_safe_routes_without_ghosts_are_shortest_paths() -> None:
    maze = resolve_maze("classic", ghost_count=0)
    start = maze.pacman_start
    routes = safe_routes(maze, start, 0, set(), EASY, {}, margin=1)
    distances = BreadthFirstSearch().distances_from(maze, start)

    assert set(routes.units) == set(distances)

    for tile, distance in list(distances.items())[::7]:
        assert routes.units[tile] == distance * EASY.move_cost
        assert len(routes.route_to(tile)) == distance


def test_safe_routes_count_pellet_pauses() -> None:
    corridor = parse_layout("#######\n#P....#\n#######\n#######\n#######\n", name="dots")
    routes = safe_routes(corridor, (1, 1), 0, set(corridor.initial_pellets), ARCADE, {}, margin=1)

    # Three pellets are left behind on the way to (1, 5).
    assert routes.units[(1, 5)] == 4 * 16 + 3 * 2


def test_safe_routes_avoid_tiles_a_ghost_reaches_first() -> None:
    corridor = parse_layout("#########\n#P      #\n#########\n#########\n#########\n", name="corridor")
    # A ghost can occupy (1, 5) at tick 2: Pac-Man would only get there at tick 4.
    routes = safe_routes(corridor, (1, 1), 0, set(), EASY, {(1, 5): 2}, margin=1)

    assert routes.route_to((1, 4)) == [R, R, R]
    assert not routes.reachable((1, 5))
    assert not routes.reachable((1, 7))


def test_dead_end_branches() -> None:
    branches = dead_end_branches(SPUR)

    assert branches == {(4, 3): Branch(entrance=(3, 3), depth=1), (5, 3): Branch(entrance=(3, 3), depth=2)}


def test_no_branches_on_a_ring_or_a_tree() -> None:
    ring = parse_layout("#####\n#P  #\n# # #\n#   #\n#####\n", name="ring")
    tree = parse_layout("#######\n#P    #\n###.###\n#######\n#######\n", name="tree")

    assert dead_end_branches(ring) == {}
    assert dead_end_branches(tree) == {}


def test_a_comb_has_one_branch_per_tooth() -> None:
    comb = parse_layout(
        "#########\n"
        "#P      #\n"
        "# ##### #\n"
        "#       #\n"
        "##.#.#.##\n"
        "##.#.#.##\n"
        "#########\n",
        name="comb",
    )
    branches = dead_end_branches(comb)

    assert {branch.entrance for branch in branches.values()} == {(3, 2), (3, 4), (3, 6)}
    assert max(branch.depth for branch in branches.values()) == 2
    assert len(branches) == 6
