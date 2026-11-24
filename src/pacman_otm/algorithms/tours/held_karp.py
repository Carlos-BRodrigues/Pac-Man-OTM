import numpy as np

MAX_HELD_KARP_PELLETS = 16


class TourTooLargeError(ValueError):
    """A tour problem too big for an exact algorithm."""


def check_held_karp_size(pellet_count: int) -> None:
    if pellet_count > MAX_HELD_KARP_PELLETS:
        raise TourTooLargeError(
            f"Held-Karp handles at most {MAX_HELD_KARP_PELLETS} pellets; this maze has "
            f"{pellet_count}. Try a sparse maze such as classic-sparse."
        )


def held_karp_tour(distances: np.ndarray) -> list[int]:
    """
    The shortest open path from node 0 through every other node (exact).

    Dynamic programming over subsets of pellets. Pellet k (0-based) is node k + 1,
    and a subset is a bitmask: bit k set means pellet k is in it.

        cost[S, j]   = length of the shortest path that starts at node 0, visits
                       exactly the pellets in S and ends at pellet j (j in S)
        parent[S, j] = the pellet visited just before j on that path

    cost[{j}, j] = distance from the start to j, and for larger S:

        cost[S, j] = min over k in S - {j} of cost[S - {j}, k] + distance(k, j)

    Subsets are filled in increasing order, so S - {j} (a smaller number) is
    always done before S. Ties go to the lowest pellet index.
    """
    pellet_count = len(distances) - 1
    check_held_karp_size(pellet_count)

    if pellet_count == 0:
        return [0]

    between_pellets = distances[1:, 1:]
    subsets = 1 << pellet_count

    cost = np.full((subsets, pellet_count), np.inf)
    parent = np.full((subsets, pellet_count), -1, dtype=int)

    for j in range(pellet_count):
        cost[1 << j, j] = distances[0, j + 1]

    for subset in range(1, subsets):
        for j in range(pellet_count):
            if not subset & (1 << j):
                continue

            previous = subset ^ (1 << j)

            if previous == 0:
                continue  # single-pellet subsets were filled above

            # cost[previous, k] is infinite for any k not in previous, so the
            # minimum only ever picks a pellet that is really in the subset.
            candidates = cost[previous] + between_pellets[:, j]
            k = int(np.argmin(candidates))

            cost[subset, j] = candidates[k]
            parent[subset, j] = k

    # The best path through all pellets may end anywhere; then walk the parents back.
    full = subsets - 1
    last = int(np.argmin(cost[full]))
    reversed_pellets = []
    subset = full

    while last != -1:
        reversed_pellets.append(last)
        previous_pellet = int(parent[subset, last])
        subset ^= 1 << last
        last = previous_pellet

    return [0, *(pellet + 1 for pellet in reversed(reversed_pellets))]
