from collections import deque

from pacman_otm.algorithms.pathfinding.bfs import BreadthFirstSearch
from pacman_otm.controllers.algorithmic.base import AlgorithmicController
from pacman_otm.controllers.controller import ControllerStatus
from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.state import SimulationState

Position = tuple[int, int]


class NearestPelletController(AlgorithmicController):

    def __init__(self, maze: Maze) -> None:
        super().__init__()
        self.maze = maze
        self.pathfinder = BreadthFirstSearch()
        self.reset()

    def reset(self) -> None:
        self.current_target: Position | None = None
        self.current_plan: deque[Action] = deque()
        self.planned_path: tuple[Position, ...] = ()
        self.path_index = 0
        self.clear_status()

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

        found = self.pathfinder.find_path_to_nearest(
            self.maze, state.pacman_position, state.remaining_pellets
        )

        if found is None:
            self.current_target = None
            self.current_plan = deque()
            self.planned_path = ()
            return

        # Kept so the plan is followed to this pellet instead of replanned every step.
        self.current_target, path = found
        self.current_plan = deque(path)
        self.path_index = 0

        # Build the position sequence only when status is enabled.
        if self._status_collection_enabled:
            position = state.pacman_position
            positions = []

            for action in path:
                position = self.maze.get_destination(position, action)
                positions.append(position)

            self.planned_path = tuple(positions)
        else:
            self.planned_path = ()
