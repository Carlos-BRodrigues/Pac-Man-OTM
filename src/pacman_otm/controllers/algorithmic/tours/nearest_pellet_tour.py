import math
from collections import deque
from typing import Any

from pacman_otm.algorithms.pathfinding.bfs import BreadthFirstSearch
from pacman_otm.algorithms.graph.metric_closure import MetricClosure
from pacman_otm.algorithms.graph.mst import mst_weight
from pacman_otm.controllers.algorithmic.base import AlgorithmicController
from pacman_otm.controllers.algorithmic.tours.tour_controller import gap_percent
from pacman_otm.controllers.controller import ControllerStatus
from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.state import SimulationState

Position = tuple[int, int]


class NearestPelletTourController(AlgorithmicController):
    """
    Greedy nearest-pellet play driven by the metric closure.

    Targets are chosen from the closure's distance matrix, one at a time: from the
    node Pac-Man stands on (the start or the pellet just eaten), go to the remaining
    pellet with the smallest closure distance. Ties go to the lowest (row, col),
    which is the lowest closure index because the closure's pellet nodes are sorted.
    The path to that target comes from one BFS, and its length must equal the
    closure distance, so this controller doubles as a check of the closure.
    """

    def __init__(self, maze: Maze) -> None:
        super().__init__()
        self.maze = maze
        self.pathfinder = BreadthFirstSearch()
        self.metric_closure = MetricClosure(maze)
        # Closure index -> node, to turn the chosen index back into a position.
        self.nodes: list[Position] = self.metric_closure.nodes
        self.reset()

    def reset(self) -> None:
        # Closure distance of every target chosen so far: the tour this run makes.
        self.tour_length = 0.0
        self.current_target: Position | None = None
        self.current_plan: deque[Action] = deque()
        self.planned_path: tuple[Position, ...] = ()
        self.path_index = 0
        self.clear_status()

    def describe(self) -> dict[str, Any]:
        lower_bound = mst_weight(self.metric_closure.distances)

        return {
            **super().describe(),
            "tour": {
                "pellets": len(self.nodes) - 1,
                "tour_length": self.tour_length,
                "lower_bound": lower_bound,
                "gap_percent": gap_percent(self.tour_length, lower_bound),
            },
        }

    def select_action(self, state: SimulationState) -> Action:

        if self.current_target not in state.remaining_pellets or not self.current_plan:
            self._select_next_target(state)

        if not self.current_plan:
            raise RuntimeError("No reachable remaining pellets.")

        action = self.current_plan.popleft()
        self.path_index += 1

        if self._status_collection_enabled:
            self._update_status(
                ControllerStatus(
                    target=self.current_target,
                    planned_path=self.planned_path,
                    path_index=self.path_index,
                )
            )

        return action

    def _select_next_target(self, state: SimulationState) -> None:

        current = state.pacman_position
        labels = self.metric_closure.labels

        # Targets are only chosen on closure nodes: the start, or the pellet
        # just reached. Anywhere else means the plan was abandoned mid-way.
        if current not in labels:
            raise RuntimeError(
                f"Position {current} is not a metric closure node; "
                "targets can only be chosen from the start or a pellet."
            )

        distances = self.metric_closure.metric_closure[labels[current]]
        target_index = min(
            (labels[pellet] for pellet in state.remaining_pellets),
            key=lambda index: (distances[index], index),
            default=None,
        )

        if target_index is None or distances[target_index] == math.inf:
            self.current_target = None
            self.current_plan = deque()
            self.planned_path = ()
            return

        target = self.nodes[target_index]
        path = self.pathfinder.find_path(self.maze, current, target)

        if path is None or len(path) != distances[target_index]:
            found = "no path" if path is None else f"a path of {len(path)} steps"
            raise RuntimeError(
                f"Metric closure says {current} -> {target} is "
                f"{distances[target_index]} steps, but BFS found {found}."
            )

        self.tour_length += distances[target_index]
        self.current_target = target
        self.current_plan = deque(path)
        self.path_index = 0

        # Build the position sequence only when status is enabled.
        if self._status_collection_enabled:
            position = current
            positions = []

            for action in path:
                position = self.maze.get_destination(position, action)
                positions.append(position)

            self.planned_path = tuple(positions)
        else:
            self.planned_path = ()
