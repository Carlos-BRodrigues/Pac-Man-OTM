from pacman_otm.controllers.ghosts.ghost import GhostController, Position
from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.state import SimulationState

# Tiles ahead of Pac-Man, in the direction he faces.
PINKY_LEAD = 4


class Pinky(GhostController):
    """
    The pink ghost: ambushes, aiming 4 tiles ahead of Pac-Man in the direction
    he faces. Facing up means straight up (the arcade's extra left offset was an
    overflow bug, not kept).
    """

    kind = "pinky"
    scatter_corner = (0, 0)

    def target(self, state: SimulationState) -> Position:
        row, col = state.pacman_occupied
        d_row, d_col = Maze.MOVEMENTS[state.pacman_facing]
        return row + PINKY_LEAD * d_row, col + PINKY_LEAD * d_col
