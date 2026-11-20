import numpy as np

from pacman_otm.controllers.base import Controller
from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.state import SimulationState


class RandomController(Controller):

    def __init__(self, maze: Maze, seed: int | None = None):
        super().__init__()
        self.maze = maze
        self.rng = np.random.default_rng(seed)

        self.movements = {
            Action.UP: (-1, 0),
            Action.DOWN: (1, 0),
            Action.LEFT: (0, -1),
            Action.RIGHT: (0, 1),
        }

    def select_action(self, state: SimulationState) -> Action:

        valid_actions = list(
            self.maze.get_valid_movements(state.pacman_position).keys()
        )

        if not valid_actions:
            raise RuntimeError("Pac-Man has no valid movements.")

        return self.rng.choice(valid_actions)
