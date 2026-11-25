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
    # The tile it is on, or leaving while progress > 0.
    position: Position
    # The move in progress out of `position`; None only at the spawn before the first decision.
    heading: Action | None = None
    # The exit already chosen for the tile it is moving to (position + heading). Ghosts
    # decide one tile ahead and cannot change it; None until that decision is made.
    next_heading: Action | None = None
    # Units of the move done (see SpeedRules.move_cost).
    progress: int = 0

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "position": self.position,
            "heading": self.heading.value if self.heading is not None else None,
            "next_heading": self.next_heading.value if self.next_heading is not None else None,
            "progress": self.progress,
        }
