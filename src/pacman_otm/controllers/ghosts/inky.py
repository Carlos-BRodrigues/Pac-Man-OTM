from pacman_otm.controllers.ghosts.blinky import Blinky
from pacman_otm.controllers.ghosts.ghost import GhostController, Position
from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.state import SimulationState

# Tiles ahead of Pac-Man for the pivot point.
INKY_LEAD = 2


class Inky(GhostController):
    """
    The cyan ghost: works with Blinky. P is 2 tiles ahead of Pac-Man (in the
    direction he faces, straight up when facing up) and B is Blinky's tile; the
    target is P + (P - B) = 2P - B, so the two close in from opposite sides.
    Blinky is the first `blinky` in the state, read from the state, never from
    Blinky's controller. A run needs one (registry.validate_lineup).
    """

    kind = "inky"
    scatter_corner = (1, 1)

    def target(self, state: SimulationState) -> Position:
        blinky = next((index for index, ghost in enumerate(state.ghosts) if ghost.kind == Blinky.kind), None)

        if blinky is None:
            raise RuntimeError("Inky needs a Blinky in the run; the lineup should have been rejected.")

        row, col = state.pacman_occupied
        d_row, d_col = Maze.MOVEMENTS[state.pacman_facing]
        pivot_row, pivot_col = row + INKY_LEAD * d_row, col + INKY_LEAD * d_col
        blinky_row, blinky_col = state.ghost_occupied(blinky)
        return 2 * pivot_row - blinky_row, 2 * pivot_col - blinky_col
