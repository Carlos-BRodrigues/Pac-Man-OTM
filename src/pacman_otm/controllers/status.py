from dataclasses import dataclass

from pacman_otm.simulation.actions import Action

Position = tuple[int, int]


@dataclass(frozen=True)
class ControllerStatus:
    """
    Optional snapshot of a controller's current intentions.
    """

    target: Position | None = None
    planned_path: tuple[Position, ...] = ()
    path_index: int = 0


@dataclass(frozen=True)
class GhostStatus(ControllerStatus):
    """
    A ghost's intentions after one decision. planned_path runs from the
    ghost's tile through decision_tile (path_index 0) along the shortest legal
    path to the target, beginning with the committed exit.
    """

    # The exit committed for decision_tile (the tile the ghost is moving to, or
    # its spawn for the first move); it cannot be changed.
    decision: Action | None = None
    decision_tile: Position | None = None
    # The legal exits at decision_tile.
    options: tuple[Action, ...] = ()
    # True when decision_tile is a junction (two or more options), so the
    # decision was a real choice; False when it was forced (corridor, turn, dead end).
    decided: bool = False
