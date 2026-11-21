"""
Frozen copy of the maze factories as they were before text layouts (Step 2),
returning raw (topography, start, pellets) so the reference does not depend on Maze.
The only intended change since then: 'H' and '-' became ghost-house (3) and gate (4)
tiles instead of walls (Step 1).
"""

WALL, CORRIDOR, GHOST_HOUSE, GHOST_GATE = 1, 0, 3, 4


def reference_small():

    topography = [
        [1, 1, 1, 1, 1, 1, 1],
        [1, 0, 0, 0, 0, 0, 1],
        [1, 0, 1, 1, 1, 0, 1],
        [1, 0, 0, 0, 0, 0, 1],
        [1, 0, 1, 1, 0, 1, 1],
        [1, 0, 0, 0, 0, 0, 1],
        [1, 1, 1, 1, 1, 1, 1],
    ]

    pacman_start = (1, 1)

    pellets = {
        (1, 2),
        (1, 3),
        (1, 4),
        (1, 5),
        (3, 1),
        (3, 2),
        (3, 3),
        (3, 4),
        (3, 5),
        (5, 1),
        (5, 2),
        (5, 3),
        (5, 4),
        (5, 5),
    }

    return dict(
        topography=topography,
        pacman_start=pacman_start,
        pellets=pellets,
    )


def reference_classic():
    """Create the classic 28x31 Pac-Man maze."""

    layout = [
        "############################",
        "#............##............#",
        "#.####.#####.##.#####.####.#",
        "#o####.#####.##.#####.####o#",
        "#.####.#####.##.#####.####.#",
        "#..........................#",
        "#.####.##.########.##.####.#",
        "#.####.##.########.##.####.#",
        "#......##....##....##......#",
        "######.##### ## #####.######",
        "######.##### ## #####.######",
        "######.##          ##.######",
        "######.## ###--### ##.######",
        "######.## #HHHHHH# ##.######",
        "      .   #HHHHHH#   .      ",
        "######.## #HHHHHH# ##.######",
        "######.## ######## ##.######",
        "######.##          ##.######",
        "######.## ######## ##.######",
        "######.## ######## ##.######",
        "#............##............#",
        "#.####.#####.##.#####.####.#",
        "#.####.#####.##.#####.####.#",
        "#o..##.......  .......##..o#",
        "###.##.##.########.##.##.###",
        "###.##.##.########.##.##.###",
        "#......##....##....##......#",
        "#.##########.##.##########.#",
        "#.##########.##.##########.#",
        "#..........................#",
        "############################",
    ]

    if len(layout) != 31 or any(len(row) != 28 for row in layout):
        raise ValueError("Classic maze must be exactly 28x31.")

    topography: list[list[int]] = []
    pellets: set[tuple[int, int]] = set()

    for row, line in enumerate(layout):
        topography_row = []

        for col, tile in enumerate(line):
            if tile == "#":
                topography_row.append(WALL)
            elif tile == "H":
                topography_row.append(GHOST_HOUSE)
            elif tile == "-":
                topography_row.append(GHOST_GATE)
            else:
                # Dots, energizers, and empty spaces are walkable.
                topography_row.append(CORRIDOR)

                if tile in (".", "o"):
                    pellets.add((row, col))

        topography.append(topography_row)

    return dict(
        topography=topography,
        pacman_start=(23, 13),
        pellets=pellets,
    )
