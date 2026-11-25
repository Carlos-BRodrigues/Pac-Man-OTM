from collections.abc import Callable

from pacman_otm.controllers.controller import Controller
from pacman_otm.controllers.algorithmic.simple.nearest_pellet import (
    NearestPelletController,
)
from pacman_otm.controllers.algorithmic.tours.held_karp import HeldKarpController
from pacman_otm.controllers.algorithmic.tours.nearest_pellet_tour import (
    NearestPelletTourController,
)
from pacman_otm.controllers.algorithmic.tours.two_opt import TwoOptController
from pacman_otm.controllers.algorithmic.tours.two_opt_avoid import TwoOptAvoidController
from pacman_otm.controllers.algorithmic.tours.two_opt_safe import TwoOptSafeController
from pacman_otm.controllers.stochastic.random_walk import RandomWalkController
from pacman_otm.mazes.maze import Maze

ControllerFactory = Callable[[Maze, int], Controller]

# What simulate and experiment run without --controller.
DEFAULT_CONTROLLER = "two-opt-safe"


class ControllerRegistry:

    def __init__(self) -> None:
        self._factories: dict[str, ControllerFactory] = {}

    def register(
        self,
        name: str,
        factory: ControllerFactory,
    ) -> None:
        if name in self._factories:
            raise ValueError(f"Controller '{name}' is already registered.")

        self._factories[name] = factory

    def create(
        self,
        name: str,
        maze: Maze,
        seed: int = 42,
    ) -> Controller:
        if name not in self._factories:
            available = ", ".join(self.names())
            raise ValueError(f"Unknown controller '{name}'. Available: {available}")

        return self._factories[name](maze, seed)

    def names(self) -> list[str]:
        return sorted(self._factories)


def create_controller_registry() -> ControllerRegistry:
    """
    All controllers that can be built from (maze, seed) alone.
    Manual play needs a keyboard source, so the `play` command builds it instead.
    """
    registry = ControllerRegistry()

    registry.register(
        "nearest-pellet",
        lambda maze, seed: NearestPelletController(maze),
    )

    registry.register(
        "nearest-pellet-tour",
        lambda maze, seed: NearestPelletTourController(maze),
    )

    registry.register(
        "held-karp",
        lambda maze, seed: HeldKarpController(maze),
    )

    registry.register(
        "two-opt",
        lambda maze, seed: TwoOptController(maze),
    )

    registry.register(
        "two-opt-avoid",
        lambda maze, seed: TwoOptAvoidController(maze),
    )

    registry.register(
        "two-opt-safe",
        lambda maze, seed: TwoOptSafeController(maze),
    )

    registry.register(
        "random-walk",
        lambda maze, seed: RandomWalkController(maze, seed=seed),
    )

    return registry
