"""
Dead-end branches: parts of a maze with only one way in and out.

Repeatedly removing tiles with at most one remaining neighbour strips off
every tree hanging from the maze's loops. The removed tiles are the branches;
each hangs from one remaining tile, its entrance. A mover inside a branch can
only leave through that entrance, which is what makes branches traps.

A measuring tool: whether a branch is worth entering is the controller's call.
"""

from collections import deque
from dataclasses import dataclass

from pacman_otm.mazes.maze import Maze

Position = tuple[int, int]


@dataclass(frozen=True)
class Branch:
    # The tile on a loop that the branch hangs from: the only way out.
    entrance: Position
    # Moves from this tile to the entrance.
    depth: int


def dead_end_branches(maze: Maze) -> dict[Position, Branch]:
    """
    Every tile inside a dead-end branch, with its entrance and depth. A maze
    without any loop (a tree) has nothing to hang branches from: {}.
    """
    positions = maze.walkable_positions()
    degree = {position: len(maze.get_valid_movements(position)) for position in positions}
    pruned: set[Position] = set()
    leaves = deque(position for position in positions if degree[position] <= 1)

    while leaves:
        tile = leaves.popleft()

        if tile in pruned:
            continue

        pruned.add(tile)

        for neighbour in maze.get_valid_movements(tile).values():
            if neighbour not in pruned:
                degree[neighbour] -= 1

                if degree[neighbour] == 1:
                    leaves.append(neighbour)

    if len(pruned) == len(positions):
        return {}

    # From each entrance (a kept tile next to a pruned one), walk into its branch.
    branches: dict[Position, Branch] = {}

    for entrance in positions:
        if entrance in pruned:
            continue

        for start in maze.get_valid_movements(entrance).values():
            if start not in pruned or start in branches:
                continue

            branches[start] = Branch(entrance=entrance, depth=1)
            frontier = deque([start])

            while frontier:
                tile = frontier.popleft()

                for neighbour in maze.get_valid_movements(tile).values():
                    if neighbour in pruned and neighbour not in branches:
                        branches[neighbour] = Branch(entrance=entrance, depth=branches[tile].depth + 1)
                        frontier.append(neighbour)

    return branches
