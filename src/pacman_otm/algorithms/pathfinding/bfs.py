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
        The closest goal and the shortest path to it, or None if no goal is reachable.
        Ties between equally close goals are broken by lowest (row, col), so results
        are deterministic: the search finishes the whole distance level in which the
        first goal appears before choosing.
        """
        if not goals:
            return None

        maze.validate_position(start)

        if start in goals:
            return start, []

        parents: dict[Position, tuple[Position, Action] | None] = {start: None}
        level = [start]
        nearest_goal: Position | None = None

        while level and nearest_goal is None:

            next_level = []

            for current in level:

                for action, neighbor in maze.get_valid_movements(current).items():

                    if neighbor in parents:
                        continue

                    parents[neighbor] = (current, action)
                    next_level.append(neighbor)

            reached = [position for position in next_level if position in goals]

            if reached:
                nearest_goal = min(reached)

            level = next_level

        if nearest_goal is None:
            return None

        path = []
        current = nearest_goal

        while current != start:

            previous, action = parents[current]

            path.append(action)
            current = previous

        path.reverse()

        return nearest_goal, path
