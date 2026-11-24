import numpy as np

from pacman_otm.algorithms.tours.held_karp import check_held_karp_size, held_karp_tour
from pacman_otm.controllers.algorithmic.tours.tour_controller import TourController
from pacman_otm.mazes.maze import Maze


class HeldKarpController(TourController):
    """Walks the optimal tour (Held-Karp). Only for mazes with few pellets."""

    def __init__(self, maze: Maze) -> None:
        # Fail before the run starts, not on its first step.
        check_held_karp_size(len(set(maze.initial_pellets) - {maze.pacman_start}))
        super().__init__(maze)

    def plan_tour(self, distances: np.ndarray) -> list[int]:
        return held_karp_tour(distances)
