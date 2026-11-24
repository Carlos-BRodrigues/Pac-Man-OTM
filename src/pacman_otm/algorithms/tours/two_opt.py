import numpy as np

# Gains this small are rounding noise, not an improvement.
MIN_GAIN = 1e-9


def two_opt(distances: np.ndarray, order: list[int]) -> list[int]:
    """
    Improve an open-path tour with 2-opt moves until none helps.

    A move reverses the segment order[i..j] (1 <= i < j, so node 0 stays first).
    Only two edges change: a-b and c-e become a-c and b-e, where

        a = order[i-1], b = order[i], c = order[j], e = order[j+1]

    When j is the last node there is no e: the path simply ends at b after the move,
    so only edge a-b becomes a-c. That is the open-path case.

    For each i, the gain of every j is computed at once with numpy; the first
    improving j is applied. Passes repeat until a full pass changes nothing.
    """
    tour = np.array(order)
    node_count = len(tour)
    improved = True

    while improved:
        improved = False

        for i in range(1, node_count - 1):
            a, b = tour[i - 1], tour[i]
            c = tour[i + 1 :]  # every candidate end of the segment, j = i+1 .. last
            e = tour[i + 2 :]  # the node after each end; the last j has none

            # Edges removed minus edges added, for each j.
            # The last entry of each pair is the open-path case: no edge after c.
            removed = distances[a, b] + np.append(distances[c[:-1], e], 0.0)
            added = distances[a, c] + np.append(distances[b, e], 0.0)
            gains = removed - added

            better = np.flatnonzero(gains > MIN_GAIN)

            if better.size:
                j = i + 1 + int(better[0])
                tour[i : j + 1] = tour[i : j + 1][::-1].copy()
                improved = True

    return [int(node) for node in tour]
