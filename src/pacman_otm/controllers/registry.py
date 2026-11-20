from collections.abc import Callable

from pacman_otm.controllers.base import Controller
from pacman_otm.mazes.maze import Maze

ControllerFactory = Callable[[Maze, int], Controller]


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
