"""
Text layouts: one character per tile, one line per row.

    #  wall                 _  void (padding outside the maze)
    .  corridor with pellet H  ghost house (ghosts only)
    o  corridor with pellet -  ghost gate (one way out of the house)
       (space) corridor     P  Pac-Man start (corridor, no pellet)

Ghost spawns, upper case without a pellet, lower case with one:

    G g  any ghost          B b  Blinky
    K k  Pinky (P is Pac-Man)  I i  Inky
    C c  Clyde

`o` is a normal pellet: there are no power pellets. Spawns are listed in reading
order (row by row); a run assigns them to its ghosts (generation/pipeline.py).
A spawn letter 4-adjacent to an `H`, or to a spawn letter that is in the house,
is a house tile (upper case only: no pellets in the house); otherwise it is a
corridor. The house is enclosed by walls and the gate, so this is unambiguous.
"""

from pathlib import Path

from pacman_otm.mazes.maze import Maze
from pacman_otm.mazes.origin import MazeOrigin
from pacman_otm.mazes.tiles import Tile

Position = tuple[int, int]

# Every *.txt in this directory is a named maze (see mazes/registry.py).
LAYOUTS_DIR = Path(__file__).parent / "layouts"

GHOST_SPAWNS_LETTERS = "GgBbKkIiCc"

# character -> (tile, has pellet); spawn letters inside the house become house tiles (parse_layout)
LEGEND: frozendict[str, tuple[Tile, bool]] = frozendict(
    {
        "#": (Tile.WALL, False),
        ".": (Tile.CORRIDOR, True),
        "o": (Tile.CORRIDOR, True),
        " ": (Tile.CORRIDOR, False),
        "P": (Tile.CORRIDOR, False),
        "G": (Tile.CORRIDOR, False),
        "g": (Tile.CORRIDOR, True),
        **{
            letter: (Tile.CORRIDOR, letter.islower())
            for letter in GHOST_SPAWNS_LETTERS
            if letter not in "Gg"
        },
        "_": (Tile.VOID, False),
        "H": (Tile.GHOST_HOUSE, False),
        "-": (Tile.GHOST_GATE, False),
    }
)

START = "P"
HOUSE = "H"
# Upper-case spawn letter -> the ghost kind it is for (None: any ghost). Lower case adds a pellet.
SPAWN_KINDS: frozendict[str, str | None] = frozendict(
    {"G": None, "B": "blinky", "K": "pinky", "I": "inky", "C": "clyde"}
)
_SPAWN_LETTERS: frozendict[str | None, str] = frozendict({kind: letter for letter, kind in SPAWN_KINDS.items()})
GHOST_SPAWNS = tuple(letter for upper in SPAWN_KINDS for letter in (upper, upper.lower()))

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
    house_spawns = _house_spawns(lines)

    for row, line in enumerate(lines):
        topography_row = []

        for col, character in enumerate(line):
            if character not in LEGEND:
                raise ValueError(
                    f"Layout '{name}': unknown character {character!r} "
                    f"at row {row}, column {col}."
                )

            tile, has_pellet = LEGEND[character]

            if (row, col) in house_spawns:
                if has_pellet:
                    raise ValueError(
                        f"Layout '{name}': spawn {character!r} at row {row}, column {col} is in the ghost house, "
                        f"where pellets are not allowed; use {character.upper()!r}."
                    )

                tile = Tile.GHOST_HOUSE

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
        ghost_spawn_kinds=[SPAWN_KINDS[lines[row][col].upper()] for row, col in ghost_spawns],
    )


def _house_spawns(lines: list[str]) -> set[Position]:
    """Spawn letters joined to an `H` through 4-adjacent spawn letters: they lie in the house."""

    spawns = {
        (row, col)
        for row, line in enumerate(lines)
        for col, character in enumerate(line)
        if character in GHOST_SPAWNS
    }
    house: set[Position] = set()
    changed = True

    while changed:
        changed = False

        for row, col in spawns - house:
            for n_row, n_col in ((row - 1, col), (row, col - 1), (row + 1, col), (row, col + 1)):
                inside = 0 <= n_row < len(lines) and 0 <= n_col < len(lines[n_row])

                if inside and (lines[n_row][n_col] == HOUSE or (n_row, n_col) in house):
                    house.add((row, col))
                    changed = True
                    break

    return house


def load_layout(path: Path) -> Maze:
    """Read a layout file; the maze is named after the file stem."""

    return parse_layout(path.read_text(encoding="utf-8"), name=path.stem)


def format_layout(maze: Maze) -> str:
    """The inverse of parse_layout (pellets are written as '.')."""

    lines = []
    spawns = dict(zip(maze.ghost_spawns, maze.ghost_spawn_kinds))

    for row in range(maze.height):
        characters = []

        for col in range(maze.width):
            position = (row, col)

            if position == maze.pacman_start:
                characters.append(START)
            elif position in spawns:
                letter = _SPAWN_LETTERS[spawns[position]]
                characters.append(letter.lower() if position in maze.initial_pellets else letter)
            elif position in maze.initial_pellets:
                characters.append(".")
            else:
                characters.append(_TILE_CHARACTERS[Tile(maze.topography[row, col])])

        lines.append("".join(characters))

    return "\n".join(lines) + "\n"
