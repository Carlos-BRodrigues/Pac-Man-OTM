"""Ghost kinds by name, and the ghosts of a run."""

from collections.abc import Sequence

from pacman_otm.controllers.ghosts.blinky import Blinky
from pacman_otm.controllers.ghosts.ghost import GhostController
from pacman_otm.mazes.maze import Maze

GHOST_KINDS: frozendict[str, type[GhostController]] = frozendict({"blinky": Blinky})


def ghost_lineup(maze: Maze) -> tuple[str, ...]:
    """The ghost kinds of a run on this maze: one Blinky per ghost spawn."""
    return (Blinky.kind,) * len(maze.ghost_spawns)


def create_ghosts(maze: Maze, kinds: Sequence[str]) -> list[GhostController]:
    """One controller per ghost, in spawn order (ghost i controls state.ghosts[i])."""

    unknown = sorted(set(kinds) - set(GHOST_KINDS))

    if unknown:
        raise ValueError(f"Unknown ghost kind(s) {unknown}; known are {', '.join(GHOST_KINDS)}.")

    return [GHOST_KINDS[kind](maze, index) for index, kind in enumerate(kinds)]
