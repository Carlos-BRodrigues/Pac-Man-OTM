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
    A ghost's intentions after one decision. planned_path starts at the tile
    the ghost moves to this step (path_index 0) and is the shortest legal path
    from there to the target, beginning with the committed exit.
    """

    # The exit committed for decision_tile (the tile the ghost moves to this
    # step); it is taken on the next step and cannot be changed.
    decision: Action | None = None
    decision_tile: Position | None = None
    # The legal exits at decision_tile.
    options: tuple[Action, ...] = ()
    # True when decision_tile is a junction (two or more options), so the
    # decision was a real choice; False when it was forced (corridor, turn, dead end).
    decided: bool = False
