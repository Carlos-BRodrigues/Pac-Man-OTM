"""
Tours over a distance matrix, shared by the tour algorithms.

A tour here is an open path: a list of node indices that starts at node 0
(Pac-Man's start), visits every other node once and does not return.
"""

import numpy as np


def tour_length(distances: np.ndarray, order: list[int]) -> float:
    """Sum of the distances between consecutive nodes of an open path."""

    return float(sum(distances[a, b] for a, b in zip(order, order[1:])))


def check_tour(order: list[int], node_count: int) -> None:
    """A tour must start at node 0 and visit every node exactly once."""

    if order[:1] != [0] or sorted(order) != list(range(node_count)):
        raise ValueError(f"Not a tour over {node_count} nodes starting at 0: {order}")
