import numpy as np

from pacman_otm.simulation.actions import Action


class Maze:

    MOVEMENTS = frozendict(
        {
            Action.UP: (-1, 0),
            Action.DOWN: (1, 0),
            Action.LEFT: (0, -1),
            Action.RIGHT: (0, 1),
        }
    )

    CORRIDOR = 0
    WALL = 1
    VOID = 2
    GHOST_INTERIOR = 3
    GHOST_GATE = 4

    def __init__(self, topography, pacman_start, pellets):

        self.topography = np.array(topography, dtype=np.uint8)

        self.pacman_start = tuple(pacman_start)

        self.initial_pellets = set(pellets)

        self._validate()

    @property
    def height(self):
        return self.topography.shape[0]

    @property
    def width(self):
        return self.topography.shape[1]

    def is_walkable(self, position):
        row, col = position

        if not (0 <= row < self.height and 0 <= col < self.width):
            return False

        return self.topography[row, col] == 0

    def _validate(self):

        if self.topography.ndim != 2:
            raise ValueError("Maze topography must be two-dimensional.")

        if self.topography.size == 0:
            raise ValueError("Maze cannot be empty.")

        if not np.isin(self.topography, [0, 1, 2]).all():
            raise ValueError("Topography must contain only 0, 1, or 2.")

        if not self.is_walkable(self.pacman_start):
            raise ValueError("Pac-Man starting position must be walkable.")

        for pellet in self.initial_pellets:
            if not self.is_walkable(pellet):
                raise ValueError(f"Pellet position {pellet} must be walkable.")

    def debug_print(self) -> None:
        print("MAZE TOPOGRAPHY")
        print("-" * 25)
        print(self.topography)
        print(f"Dimensions: {self.height} x {self.width}")
        print(f"Initial pellets: {len(self.initial_pellets)}")

    def validate_position(self, position: tuple[int, int]) -> None:
        if not self.is_walkable(position):
            raise ValueError(f"Position {position} is not walkable.")

    def get_destination(
        self,
        position: tuple[int, int],
        action: Action,
    ) -> tuple[int, int]:

        row, col = position
        d_row, d_col = self.MOVEMENTS[action]

        return row + d_row, col + d_col

    def get_valid_movements(
        self,
        position: tuple[int, int],
    ) -> dict[Action, tuple[int, int]]:

        self.validate_position(position)

        valid_movements = {}

        for action in self.MOVEMENTS:
            destination = self.get_destination(position, action)

            if self.is_walkable(destination):
                valid_movements[action] = destination

        return valid_movements
