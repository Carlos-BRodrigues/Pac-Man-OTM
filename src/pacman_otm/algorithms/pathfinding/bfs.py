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

    def find_path_to_nearest(
        self,
        maze: Maze,
        start: Position,
        goals: set[Position],
    ) -> tuple[Position, list[Action]] | None:
        """
        Shortest path to the closest goal. Ties between equally close
        goals are broken by lowest (row, col), so results are deterministic.
        """
        if not goals:
            return

        maze.validate_position(start)

        frontier = deque([start])

        parents: dict[Position, tuple[Position, Action] | None] = {start: None}

        stop = False

        while frontier and not stop:

            current = frontier.popleft()

            movements = maze.get_valid_movements(current)

            for action, neighbor in movements.items():

                if neighbor in parents:
                    continue

                parents[neighbor] = (current, action)
                frontier.append(neighbor)

                if neighbor in goals:
                    stop = True
                    break

        nearest_goal = set(parents.keys()).intersection(goals)

        if not nearest_goal:
            return None

        path = []
        current = nearest_goal.pop()

        while current != start:

            previous, action = parents[current]

            path.append(action)
            current = previous

        path.reverse()

        return path
