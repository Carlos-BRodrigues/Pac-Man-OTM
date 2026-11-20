from pacman_otm.mazes.maze import Maze


def create_small_maze():

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

    return Maze(
        topography=topography,
        pacman_start=pacman_start,
        pellets=pellets,
    )


def create_medium_maze() -> Maze:
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
            if tile in ("#", "H", "-"):
                topography_row.append(Maze.WALL)
            else:
                # Dots, energizers, and empty spaces are walkable.
                topography_row.append(Maze.CORRIDOR)

                if tile in (".", "o"):
                    pellets.add((row, col))

        topography.append(topography_row)

    return Maze(
        topography=topography,
        pacman_start=(23, 13),
        pellets=pellets,
    )
