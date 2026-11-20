from dataclasses import dataclass

Position = tuple[int, int]


@dataclass(frozen=True)
class ControllerStatus:
    """
    Optional snapshot of a controller's current intentions.
    """

    target: Position | None = None
    planned_path: tuple[Position, ...] = ()
    path_index: int = 0
