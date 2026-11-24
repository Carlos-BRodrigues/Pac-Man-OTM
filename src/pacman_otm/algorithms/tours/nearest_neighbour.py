import numpy as np


def nearest_neighbour_tour(distances: np.ndarray) -> list[int]:
    """
    From node 0, always go to the nearest node not visited yet.
    Ties go to the lowest index (np.argmin returns the first minimum).
    """
    node_count = len(distances)
    visited = np.zeros(node_count, dtype=bool)
    visited[0] = True
    order = [0]

    for _ in range(node_count - 1):
        candidates = np.where(visited, np.inf, distances[order[-1]])
        nearest = int(np.argmin(candidates))

        visited[nearest] = True
        order.append(nearest)

    return order
