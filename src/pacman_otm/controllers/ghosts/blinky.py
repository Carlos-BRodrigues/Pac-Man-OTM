from pacman_otm.controllers.ghosts.ghost import GhostController, Position
from pacman_otm.simulation.state import SimulationState


class Blinky(GhostController):
    """The red ghost: chases Pac-Man directly, targeting his current tile."""

    kind = "blinky"

    def target(self, state: SimulationState) -> Position:
        return state.pacman_position
