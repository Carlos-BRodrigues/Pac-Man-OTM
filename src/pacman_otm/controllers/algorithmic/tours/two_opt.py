from typing import Any

import numpy as np

from pacman_otm.algorithms.tours.nearest_neighbour import nearest_neighbour_tour
from pacman_otm.algorithms.tours.tour import tour_length
from pacman_otm.algorithms.tours.two_opt import two_opt
from pacman_otm.controllers.algorithmic.tours.tour_controller import TourController


class TwoOptController(TourController):
    """Nearest-neighbour tour over the metric closure, improved with 2-opt."""

    def plan_tour(self, distances: np.ndarray) -> list[int]:
        nearest = nearest_neighbour_tour(distances)
        self.nearest_neighbour_length = tour_length(distances, nearest)
        return two_opt(distances, nearest)

    def tour_stats(self, distances: np.ndarray) -> dict[str, Any]:
        nn_length = self.nearest_neighbour_length
        improvement = 0.0 if nn_length == 0 else (nn_length - self.planned_length) / nn_length * 100

        return {
            "nn_length": nn_length,
            "improvement_percent": improvement,
            **self.lower_bound_stats(distances),
        }
