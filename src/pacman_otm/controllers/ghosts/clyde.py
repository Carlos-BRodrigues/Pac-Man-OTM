from pacman_otm.controllers.ghosts.ghost import GhostController, Position
from pacman_otm.simulation.state import SimulationState

# Clyde chases only while farther than this many tiles (Euclidean), compared squared to stay exact.
CLYDE_RANGE = 8


class Clyde(GhostController):
    """
    The orange ghost: chases Pac-Man's tile while more than 8 tiles away
    (straight-line distance between their tiles); at 8 or closer he heads for his
    corner, the bottom-left of the map.
    """

    kind = "clyde"
    scatter_corner = (1, 0)

    def target(self, state: SimulationState) -> Position:
        pacman = state.pacman_occupied
        row, col = state.ghost_occupied(self.ghost_index)
        distance_squared = (row - pacman[0]) ** 2 + (col - pacman[1]) ** 2
        return pacman if distance_squared > CLYDE_RANGE**2 else self.corner
