from pacman_otm.controllers.stochastic.stochastic import StochasticController
from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.state import SimulationState


class RandomWalkController(StochasticController):
    """
    Picks uniformly among the walkable moves at each step. A lower bound to compare against.
    """

    def __init__(self, maze: Maze, seed: int | None = 42) -> None:
        self.maze = maze
        super().__init__(seed=seed)

    def select_action(self, state: SimulationState) -> Action:

        # Maze.MOVEMENTS order (UP, LEFT, DOWN, RIGHT) fixes which action each draw maps to
        valid_actions = list(self.maze.get_valid_movements(state.pacman_position))

        if not valid_actions:
            raise RuntimeError("Pac-Man has no valid movements.")

        return self.rng.choice(valid_actions)
