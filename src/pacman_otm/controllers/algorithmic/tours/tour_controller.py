from abc import abstractmethod
from collections import deque
from typing import Any

import numpy as np

from pacman_otm.algorithms.graph.metric_closure import MetricClosure
from pacman_otm.algorithms.graph.mst import mst_weight
from pacman_otm.algorithms.pathfinding.bfs import BreadthFirstSearch
from pacman_otm.algorithms.tours.tour import check_tour, tour_length
from pacman_otm.controllers.algorithmic.base import AlgorithmicController
from pacman_otm.controllers.controller import ControllerStatus
from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.state import SimulationState

Position = tuple[int, int]


def gap_percent(length: float, lower_bound: float) -> float:
    """How far a tour can at most be from optimal: the optimum lies in [lower_bound, length]."""
    return 0.0 if lower_bound == 0 else (length - lower_bound) / lower_bound * 100


class TourController(AlgorithmicController):
    """
    Plans a whole tour over the metric closure, then walks it.

    Planning happens on the first decision of a run, so building the closure and
    the tour counts in controller_time_seconds like any other thinking. The tour
    is walked one target at a time with BFS; pellets eaten on the way are skipped,
    which never makes the walk longer than the planned tour (triangle inequality).

    Subclasses implement plan_tour, and may add numbers to the saved description
    with tour_stats.
    """

    def __init__(self, maze: Maze) -> None:
        super().__init__()
        self.maze = maze
        self.pathfinder = BreadthFirstSearch()
        self.reset()

    def reset(self) -> None:
        self.closure: MetricClosure | None = None
        self.order: list[int] = []
        self.order_index = 0
        self.planned_length: float | None = None
        self.current_target: Position | None = None
        self.current_plan: deque[Action] = deque()
        self.planned_path: tuple[Position, ...] = ()
        self.path_index = 0
        self.clear_status()

    @abstractmethod
    def plan_tour(self, distances: np.ndarray) -> list[int]:
        """An open path of node indices starting at 0 (the start) through every pellet."""

    def tour_stats(self, distances: np.ndarray) -> dict[str, Any]:
        """Extra numbers about the planned tour, saved under describe()['tour']."""
        return {}

    def describe(self) -> dict[str, Any]:
        description = super().describe()

        if self.closure is not None:
            description["tour"] = {
                "pellets": len(self.order) - 1,
                "tour_length": self.planned_length,
                **self.tour_stats(self.closure.distances),
            }

        return description

    def lower_bound_stats(self, distances: np.ndarray) -> dict[str, float]:
        """The MST lower bound and the gap of the planned tour against it."""
        lower_bound = mst_weight(distances)
        return {
            "lower_bound": lower_bound,
            "gap_percent": gap_percent(self.planned_length, lower_bound),
        }

    def select_action(self, state: SimulationState) -> Action:

        if self.closure is None:
            self._plan()

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

    def _plan(self) -> None:
        self.closure = MetricClosure(self.maze)
        distances = self.closure.distances

        self.order = self.plan_tour(distances)
        check_tour(self.order, len(distances))

        self.planned_length = tour_length(distances, self.order)
        self.order_index = 1  # order[0] is the start

    def _select_next_target(self, state: SimulationState) -> None:

        # The next pellet of the tour that is still there.
        while (
            self.order_index < len(self.order)
            and self.closure.nodes[self.order[self.order_index]] not in state.remaining_pellets
        ):
            self.order_index += 1

        if self.order_index == len(self.order):
            self.current_target = None
            self.current_plan = deque()
            self.planned_path = ()
            return

        target = self.closure.nodes[self.order[self.order_index]]
        self.order_index += 1

        path = self.pathfinder.find_path(self.maze, state.pacman_position, target)

        self.current_target = target
        self.current_plan = deque(path or [])
        self.path_index = 0

        # Build the position sequence only when status is enabled.
        if self._status_collection_enabled and path:
            position = state.pacman_position
            positions = []

            for action in path:
                position = self.maze.get_destination(position, action)
                positions.append(position)

            self.planned_path = tuple(positions)
        else:
            self.planned_path = ()
