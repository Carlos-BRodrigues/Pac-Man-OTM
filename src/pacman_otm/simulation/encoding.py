"""
Compact text forms for saved results: a move is one letter (U, L, D, R; "." for none) and a
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


# Per-tick strings, where a tick can also have no move: "." stands for None.
NO_MOVE = "."


def encode_optional_moves(actions: list[Action | None] | tuple[Action | None, ...]) -> str:
    return "".join(NO_MOVE if action is None else _LETTERS[action] for action in actions)


def decode_optional_moves(text: str) -> list[Action | None]:
    return [None if letter == NO_MOVE else decode_moves(letter)[0] for letter in text]


def encode_arrivals(positions: list[Position]) -> str:
    """One letter per tick: the move to the next position, or "." when it stayed."""

    letters = []

    for (row, col), (next_row, next_col) in zip(positions, positions[1:]):
        offset = (next_row - row, next_col - col)

        if offset == (0, 0):
            letters.append(NO_MOVE)
        elif offset in _OFFSETS:
            letters.append(_OFFSETS[offset])
        else:
            raise ValueError(f"A mover jumped from {(row, col)} to {(next_row, next_col)} in one tick.")

    return "".join(letters)


def decode_arrivals(start: Position, text: str) -> list[Position]:
    positions = [tuple(start)]

    for move in decode_optional_moves(text):
        row, col = positions[-1]

        if move is None:
            positions.append((row, col))
        else:
            d_row, d_col = Maze.MOVEMENTS[move]
            positions.append((row + d_row, col + d_col))

    return positions
