from collections import deque

from pacman_otm.algorithms.pathfinding.bfs import BreadthFirstSearch
from pacman_otm.controllers.algorithms.base import AlgorithmicController
from pacman_otm.controllers.base import ControllerStatus
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

        candidates: list[tuple[int, Position, list[Action]]] = []

        for pellet in sorted(state.remaining_pellets):
            path = self.pathfinder.find_path(
                maze=self.maze,
                start=state.pacman_position,
                goal=pellet,
            )

            if path is not None:
                candidates.append((len(path), pellet, path))

        if not candidates:
            self.current_target = None
            self.current_plan.clear()
            self.planned_path = ()
            self.path_index = 0
            self.clear_status()
            return

        _, self.current_target, best_path = min(
            candidates,
            key=lambda candidate: (candidate[0], candidate[1]),
        )

        self.current_plan = deque(best_path)
        self.path_index = 0

        # Build the position sequence only when status is enabled.
        if self._status_collection_enabled:
            position = state.pacman_position
            positions = []

            for action in best_path:
                position = self.maze.get_destination(position, action)
                positions.append(position)

            self.planned_path = tuple(positions)
        else:
            self.planned_path = ()
