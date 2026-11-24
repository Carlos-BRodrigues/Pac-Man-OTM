"""What a ghost is at one moment of a run. Decisions live in ghost controllers."""

from dataclasses import dataclass

from pacman_otm.simulation.actions import Action

Position = tuple[int, int]

# The termination reason when a ghost catches Pac-Man.
CAUGHT_REASON = "caught"


@dataclass(frozen=True)
class GhostState:
    # Which ghost this is, e.g. "blinky": decides its controller and its colour.
    kind: str
    position: Position
    # The move that brought it here; None at the spawn, before its first move.
    direction: Action | None = None

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "position": self.position,
            "direction": self.direction.value if self.direction is not None else None,
        }
