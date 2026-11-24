import numpy as np


def mst_weight(distances: np.ndarray) -> float:
    """
    Total weight of a minimum spanning tree over all nodes of a complete graph
    (Prim's algorithm on the dense distance matrix, O(V^2)).

    Used as a lower bound for tours: any path that visits every node is itself a
    spanning tree, so it can never be shorter than the minimum one.
    """
    node_count = len(distances)

    if node_count <= 1:
        return 0.0

    in_tree = np.zeros(node_count, dtype=bool)
    # best[v]: the cheapest edge from the tree to v found so far.
    best = np.full(node_count, np.inf)
    best[0] = 0.0
    total = 0.0

    for _ in range(node_count):
        # The closest node not yet in the tree joins it.
        candidates = np.where(in_tree, np.inf, best)
        node = int(np.argmin(candidates))

        total += float(best[node])
        in_tree[node] = True

        # Edges from the new tree node may be cheaper ways to reach the others.
        best = np.minimum(best, distances[node])

    return total
