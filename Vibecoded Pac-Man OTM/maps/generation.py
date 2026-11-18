import random
from game.model import Maze


def generate_connected_maze(
    width,
    height,
    corridor_fraction=0.65,
    min_edges=0,
    min_average_degree=1.8,
    seed=None,
):
    """Generate a connected grid graph with minimum edge-count and degree targets.

    Corridors are grown from a seed through adjacent frontier cells, so the
    initial graph is connected. Additional cells are opened only when they
    touch at least two existing corridors, adding cycles and increasing
    connectivity. Impossible requests raise ValueError rather than silently
    returning a map that violates the requested bounds.
    """
    if width < 2 or height < 2:
        raise ValueError("width and height must be >= 2")
    if not 0 < corridor_fraction <= 1:
        raise ValueError("corridor_fraction must be in (0, 1]")
    if min_edges < 0 or min_average_degree < 0:
        raise ValueError("edge and degree targets cannot be negative")
    rng = random.Random(seed)
    cells = {(x, y) for y in range(height) for x in range(width)}
    target = max(1, min(len(cells), round(len(cells) * corridor_fraction)))
    corridors = {(rng.randrange(width), rng.randrange(height))}

    def adjacent(p):
        x, y = p
        return [
            (x + dx, y + dy)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            if (x + dx, y + dy) in cells
        ]

    while len(corridors) < target:
        frontier = list({q for p in corridors for q in adjacent(p)} - corridors)
        if not frontier:
            break
        corridors.add(rng.choice(frontier))
    grid = [
        [2 if (x, y) in corridors else 1 for x in range(width)] for y in range(height)
    ]
    maze = Maze.from_rows(grid)
    while (
        len(maze.edges()) < min_edges
        or maze.average_degree() + 1e-9 < min_average_degree
    ):
        candidates = [
            p
            for p in cells - corridors
            if sum(q in corridors for q in adjacent(p)) >= 2
        ]
        if not candidates:
            raise ValueError(
                f"Requested min_edges={min_edges} and average_degree={min_average_degree:.2f} "
                f"cannot be met; achieved edges={len(maze.edges())}, "
                f"average_degree={maze.average_degree():.2f}. Increase density or dimensions."
            )
        best_degree = max(sum(q in corridors for q in adjacent(p)) for p in candidates)
        best = [
            p
            for p in candidates
            if sum(q in corridors for q in adjacent(p)) == best_degree
        ]
        p = rng.choice(best)
        corridors.add(p)
        grid[p[1]][p[0]] = 2
        maze = Maze.from_rows(grid)
    if not maze.connected():
        raise RuntimeError("Generator produced disconnected corridors")
    return maze
