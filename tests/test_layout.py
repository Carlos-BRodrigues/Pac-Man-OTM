import re

import pytest

from pacman_otm.mazes.layout import format_layout, load_layout, parse_layout
from pacman_otm.mazes.registry import LAYOUTS_DIR
from pacman_otm.mazes.tiles import Tile
from reference_mazes import reference_classic, reference_small


@pytest.mark.parametrize(
    ("file_name", "reference"),
    [("small.txt", reference_small), ("classic.txt", reference_classic)],
)
def test_layout_files_match_the_old_factories(file_name, reference) -> None:
    maze = load_layout(LAYOUTS_DIR / file_name)
    expected = reference()

    assert maze.topography.tolist() == expected["topography"]
    assert maze.pacman_start == expected["pacman_start"]
    assert set(maze.initial_pellets) == set(expected["pellets"])


def test_legend() -> None:
    maze = parse_layout(
        "######\n"
        "#P.o #\n"
        "# _H #\n"
        "#.-..#\n"
        "######\n",
        name="legend",
    )

    assert maze.pacman_start == (1, 1)
    assert set(maze.initial_pellets) == {(1, 2), (1, 3), (3, 1), (3, 3), (3, 4)}
    assert maze.topography[1, 4] == Tile.CORRIDOR
    assert maze.topography[2, 1] == Tile.CORRIDOR
    assert maze.topography[2, 2] == Tile.VOID
    assert maze.topography[2, 3] == Tile.GHOST_HOUSE
    assert maze.topography[3, 2] == Tile.GHOST_GATE


def test_crlf_and_trailing_blank_lines() -> None:
    maze = parse_layout("#####\r\n#P  #\r\n#   #\r\n#   #\r\n#####\r\n\r\n", name="crlf")

    assert maze.height == 5 and maze.width == 5


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("###\n#P#\n##\n", "row 2 has length 2, expected 3"),
        ("####\n#Px#\n####\n", "unknown character 'x' at row 1, column 2"),
        ("###\n#.#\n###\n", "exactly one 'P'"),
        ("####\n#PP#\n####\n", "found (1, 1), (1, 2)"),
        ("\n\n", "is empty"),
    ],
)
def test_errors_name_the_problem(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=re.escape(message)):
        parse_layout(text, name="bad")


@pytest.mark.parametrize("file_name", ["small.txt", "classic.txt"])
def test_format_round_trip(file_name: str) -> None:
    path = LAYOUTS_DIR / file_name
    maze = load_layout(path)

    # 'o' is written back as '.', which parses to the same maze
    original = path.read_text(encoding="utf-8").replace("o", ".")

    assert format_layout(maze) == original


