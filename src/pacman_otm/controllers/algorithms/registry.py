from pacman_otm.controllers.registry import ControllerRegistry
from pacman_otm.controllers.algorithms.nearest_pellet import (
    NearestPelletController,
)
from pacman_otm.controllers.random import RandomController


def create_controller_registry() -> ControllerRegistry:
    registry = ControllerRegistry()

    registry.register(
        "nearest-pellet",
        lambda maze, seed: NearestPelletController(maze),
    )

    registry.register(
        "random",
        lambda maze, seed: RandomController(maze, seed=seed),
    )

    return registry
