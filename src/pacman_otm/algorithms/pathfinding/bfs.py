from collections import deque

from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.actions import Action

Position = tuple[int, int]


class BreadthFirstSearch:

    def find_path(
        self,
        maze: Maze,
        start: Position,
        goal: Position,
    ) -> list[Action] | None:

        maze.validate_position(start)
        maze.validate_position(goal)

        if start == goal:
            return []

        frontier = deque([start])

        # Stores the previous position and action used
        # to reach each discovered position.
        parents: dict[Position, tuple[Position, Action] | None] = {start: None}

        while frontier:

            current = frontier.popleft()

            if current == goal:
                break

            movements = maze.get_valid_movements(current)

            for action, neighbor in movements.items():

                if neighbor in parents:
                    continue

                parents[neighbor] = (current, action)
                frontier.append(neighbor)

        # The goal was never reached.
        if goal not in parents:
            return None

        # Reconstruct the path.
        path = []
        current = goal

        while current != start:

            previous, action = parents[current]

            path.append(action)
            current = previous

        path.reverse()

        return path
