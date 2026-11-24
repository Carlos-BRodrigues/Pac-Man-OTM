"""
Compact text forms for saved results: a move is one letter (U, L, D, R) and a
path of adjacent tiles is its first tile plus its moves, e.g. "11,13:LLUR".
Lossless: decoding gives back exactly what was encoded.
"""

from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.actions import Action

Position = tuple[int, int]

_LETTERS: frozendict[Action, str] = frozendict(
    {Action.UP: "U", Action.LEFT: "L", Action.DOWN: "D", Action.RIGHT: "R"}
)
_ACTIONS: frozendict[str, Action] = frozendict({letter: action for action, letter in _LETTERS.items()})
_OFFSETS: frozendict[tuple[int, int], str] = frozendict(
    {offset: _LETTERS[action] for action, offset in Maze.MOVEMENTS.items()}
)


def encode_moves(actions: list[Action] | tuple[Action, ...]) -> str:
    return "".join(_LETTERS[action] for action in actions)


def decode_moves(text: str) -> list[Action]:
    try:
        return [_ACTIONS[letter] for letter in text]
    except KeyError as error:
        raise ValueError(f"Unknown move letter {error.args[0]!r} in {text!r}.") from None


def encode_move(action: Action | None) -> str | None:
    return _LETTERS[action] if action is not None else None


def decode_move(letter: str | None) -> Action | None:
    return _ACTIONS[letter] if letter is not None else None


def encode_path(path: tuple[Position, ...]) -> str:
    """'' for no path, 'r,c:MOVES' for adjacent tiles, else 'r,c|r,c|...'."""

    if not path:
        return ""

    letters = []

    for (row, col), (next_row, next_col) in zip(path, path[1:]):
        letter = _OFFSETS.get((next_row - row, next_col - col))

        if letter is None:
            return "|".join(f"{r},{c}" for r, c in path)

        letters.append(letter)

    row, col = path[0]
    return f"{row},{col}:{''.join(letters)}"


def decode_path(text: str) -> tuple[Position, ...]:
    if not text:
        return ()

    if ":" not in text:
        return tuple(_position(part) for part in text.split("|"))

    start, _, moves = text.partition(":")
    positions = [_position(start)]

    for action in decode_moves(moves):
        row, col = positions[-1]
        d_row, d_col = Maze.MOVEMENTS[action]
        positions.append((row + d_row, col + d_col))

    return tuple(positions)


def _position(text: str) -> Position:
    row, _, col = text.partition(",")
    return int(row), int(col)
