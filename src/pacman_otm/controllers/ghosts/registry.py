"""Ghost kinds by name, and the ghosts of a run."""

from collections.abc import Sequence
from itertools import cycle, islice

from pacman_otm.controllers.ghosts.blinky import Blinky
from pacman_otm.controllers.ghosts.clyde import Clyde
from pacman_otm.controllers.ghosts.ghost import GhostController
from pacman_otm.controllers.ghosts.inky import Inky
from pacman_otm.controllers.ghosts.pinky import Pinky
from pacman_otm.mazes.maze import Maze

# Also the default lineup order: --ghosts N cycles through it.
GHOST_KINDS: frozendict[str, type[GhostController]] = frozendict(
    {"blinky": Blinky, "pinky": Pinky, "inky": Inky, "clyde": Clyde}
)


def default_lineup(count: int) -> tuple[str, ...]:
    """`count` ghosts cycling Blinky, Pinky, Inky, Clyde (5 -> a second Blinky)."""
    return tuple(islice(cycle(GHOST_KINDS), count))


def ghost_lineup(maze: Maze) -> tuple[str, ...]:
    """
    The ghost kinds for a maze's own spawns, in spawn order (ghost i on spawn i):
    a spawn marked for a kind gets that kind; unmarked spawns get, in order, the
    kinds no spawn is marked for, then the default cycle again.
    """
    marked = {kind for kind in maze.ghost_spawn_kinds if kind is not None}
    fill = iter([*(kind for kind in GHOST_KINDS if kind not in marked), *default_lineup(len(maze.ghost_spawns))])
    return validate_lineup(tuple(kind if kind is not None else next(fill) for kind in maze.ghost_spawn_kinds))


def validate_lineup(kinds: Sequence[str]) -> tuple[str, ...]:
    """Known kinds, and a Blinky for every Inky to work with; the lineup as a tuple."""

    unknown = sorted(set(kinds) - set(GHOST_KINDS))

    if unknown:
        raise ValueError(f"Unknown ghost kind(s) {unknown}; known are {', '.join(GHOST_KINDS)}.")

    if Inky.kind in kinds and Blinky.kind not in kinds:
        raise ValueError(
            "Inky aims relative to Blinky, so a lineup with Inky needs a Blinky: "
            "add one to --ghost-kinds (e.g. blinky,inky)."
        )

    return tuple(kinds)


def parse_lineup(text: str) -> tuple[str, ...]:
    """'blinky,pinky' -> ('blinky', 'pinky'), validated."""
    return validate_lineup(tuple(part.strip().lower() for part in text.split(",") if part.strip()))


def create_ghosts(maze: Maze, kinds: Sequence[str]) -> list[GhostController]:
    """One controller per ghost, in spawn order (ghost i controls state.ghosts[i])."""

    validate_lineup(kinds)
    return [GHOST_KINDS[kind](maze, index) for index, kind in enumerate(kinds)]
