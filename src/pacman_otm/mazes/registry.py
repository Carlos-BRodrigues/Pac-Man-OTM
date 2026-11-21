from collections.abc import Callable
from functools import partial
from pathlib import Path

from pacman_otm.mazes.layout import load_layout
from pacman_otm.mazes.maze import Maze

MazeFactory = Callable[[], Maze]

# Every *.txt in this directory is a named maze: drop a file in to add one.
LAYOUTS_DIR = Path(__file__).parent / "layouts"

DEFAULT_MAZE = "classic"


class MazeSpecError(ValueError):
    """A --maze value that names no maze, or a layout file that cannot be used."""


class MazeRegistry:

    def __init__(self) -> None:
        self._factories: dict[str, MazeFactory] = {}

    def register(self, name: str, factory: MazeFactory) -> None:
        if name in self._factories:
            raise ValueError(f"Maze '{name}' is already registered.")

        self._factories[name] = factory

    def create(self, name: str) -> Maze:
        if name not in self._factories:
            available = ", ".join(self.names())
            raise ValueError(f"Unknown maze '{name}'. Available: {available}")

        return self._factories[name]()

    def names(self) -> list[str]:
        return sorted(self._factories)


def create_maze_registry() -> MazeRegistry:
    registry = MazeRegistry()

    for path in sorted(LAYOUTS_DIR.glob("*.txt")):
        registry.register(path.stem, partial(load_layout, path))

    return registry


def resolve_maze(spec: str, registry: MazeRegistry | None = None) -> Maze:
    """
    A registered maze name, or a path to a layout file for one-off mazes.
    """
    registry = registry if registry is not None else create_maze_registry()

    if spec in registry.names():
        return registry.create(spec)

    path = Path(spec)

    if path.suffix == ".txt" or path.parent != Path("."):
        if not path.is_file():
            raise MazeSpecError(f"Layout file '{path}' does not exist.")

        try:
            return load_layout(path)
        except ValueError as error:
            raise MazeSpecError(f"Invalid layout file '{path}': {error}") from error

    available = ", ".join(registry.names())
    raise MazeSpecError(
        f"Unknown maze '{spec}'. Available: {available} (or a path to a .txt layout)."
    )
