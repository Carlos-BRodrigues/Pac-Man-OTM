"""
Text layouts: one character per tile, one line per row.

    #  wall                 _  void (padding outside the maze)
    .  corridor with pellet H  ghost house (decorative)
    o  corridor with pellet -  ghost gate (decorative)
       (space) corridor     P  Pac-Man start (corridor, no pellet)
    G  ghost spawn          g  ghost spawn with a pellet

`o` is a normal pellet: there are no power pellets. Ghost spawns are corridor
tiles; ghost i starts on the i-th spawn in reading order (row by row).
"""

from pathlib import Path

from pacman_otm.mazes.maze import Maze
from pacman_otm.mazes.origin import MazeOrigin
from pacman_otm.mazes.tiles import Tile

Position = tuple[int, int]

# Every *.txt in this directory is a named maze (see mazes/registry.py).
LAYOUTS_DIR = Path(__file__).parent / "layouts"

# character -> (tile, has pellet)
LEGEND: frozendict[str, tuple[Tile, bool]] = frozendict(
    {
        "#": (Tile.WALL, False),
        ".": (Tile.CORRIDOR, True),
        "o": (Tile.CORRIDOR, True),
        " ": (Tile.CORRIDOR, False),
        "P": (Tile.CORRIDOR, False),
        "G": (Tile.CORRIDOR, False),
        "g": (Tile.CORRIDOR, True),
        "_": (Tile.VOID, False),
        "H": (Tile.GHOST_HOUSE, False),
        "-": (Tile.GHOST_GATE, False),
    }
)

START = "P"
GHOST_SPAWNS = ("G", "g")

# tile -> character for format_layout; pellets and the start are handled separately
_TILE_CHARACTERS: frozendict[Tile, str] = frozendict(
    {
        Tile.WALL: "#",
        Tile.CORRIDOR: " ",
        Tile.VOID: "_",
        Tile.GHOST_HOUSE: "H",
        Tile.GHOST_GATE: "-",
    }
)


def parse_layout(text: str, name: str) -> Maze:
    """Build a Maze from layout text. Errors name the row, column and character."""

    lines = text.splitlines()

    # Only trailing blank lines are dropped: leading ones would shift every row index.
    while lines and not lines[-1].strip():
        lines.pop()

    if not lines:
        raise ValueError(f"Layout '{name}' is empty.")

    width = len(lines[0])

    for row, line in enumerate(lines):
        if len(line) != width:
            raise ValueError(
                f"Layout '{name}': row {row} has length {len(line)}, expected {width} "
                f"(the length of row 0). Check for trimmed trailing spaces."
            )

    topography: list[list[int]] = []
    pellets: set[Position] = set()
    starts: list[Position] = []
    ghost_spawns: list[Position] = []

    for row, line in enumerate(lines):
        topography_row = []

        for col, character in enumerate(line):
            if character not in LEGEND:
                raise ValueError(
                    f"Layout '{name}': unknown character {character!r} "
                    f"at row {row}, column {col}."
                )

            tile, has_pellet = LEGEND[character]
            topography_row.append(tile)

            if has_pellet:
                pellets.add((row, col))

            if character == START:
                starts.append((row, col))

            if character in GHOST_SPAWNS:
                ghost_spawns.append((row, col))

        topography.append(topography_row)

    if len(starts) != 1:
        found = ", ".join(str(start) for start in starts) or "none"
        raise ValueError(
            f"Layout '{name}' needs exactly one '{START}' (Pac-Man start); found {found}."
        )

    return Maze(
        topography=topography,
        pacman_start=starts[0],
        pellets=pellets,
        origin=MazeOrigin(source="layout", name=name),
        ghost_spawns=ghost_spawns,
    )


def load_layout(path: Path) -> Maze:
    """Read a layout file; the maze is named after the file stem."""

    return parse_layout(path.read_text(encoding="utf-8"), name=path.stem)


def format_layout(maze: Maze) -> str:
    """The inverse of parse_layout (pellets are written as '.')."""

    lines = []
    spawns = set(maze.ghost_spawns)

    for row in range(maze.height):
        characters = []

        for col in range(maze.width):
            position = (row, col)

            if position == maze.pacman_start:
                characters.append(START)
            elif position in spawns:
                characters.append("g" if position in maze.initial_pellets else "G")
            elif position in maze.initial_pellets:
                characters.append(".")
            else:
                characters.append(_TILE_CHARACTERS[Tile(maze.topography[row, col])])

        lines.append("".join(characters))

    return "\n".join(lines) + "\n"
