"""
Every maze a command can name. One resolver serves all commands:

    classic                 layout in mazes/layouts/
    open-lattice            recipe in mazes/recipes/ (built from a maze seed)
    my-favourite            saved maze in mazes/saved/
    path/to/file.txt        one-off layout
    path/to/file.toml       one-off recipe
    path/to/file.json       one-off saved maze

Drop a file into one of the folders to register it under its file stem.
A name in two folders is an error.
"""

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from pacman_otm.mazes.config import ConfigError
from pacman_otm.mazes.generation.errors import GenerationError
from pacman_otm.mazes.generation.pipeline import build_maze
from pacman_otm.mazes.generation.recipe import MazeRecipe, apply_overrides, load_recipe
from pacman_otm.mazes.layout import LAYOUTS_DIR, load_layout
from pacman_otm.mazes.maze import Maze
from pacman_otm.mazes.serialization import maze_from_dict, maze_to_dict

RECIPES_DIR = Path(__file__).parent / "recipes"
# Written by 'mazes generate --save'; part of the source tree with an editable install.
SAVED_DIR = Path(__file__).parent / "saved"

DEFAULT_MAZE = "classic"

SAVED_MAZE_VERSION = 1

MazeKind = Literal["layout", "recipe", "saved"]
SUFFIX_KINDS: frozendict[str, MazeKind] = frozendict(
    {".txt": "layout", ".toml": "recipe", ".json": "saved"}
)

__all__ = [
    "DEFAULT_MAZE",
    "LAYOUTS_DIR",
    "RECIPES_DIR",
    "SAVED_DIR",
    "MazeRegistry",
    "MazeSource",
    "MazeSpecError",
    "create_maze_registry",
    "load_saved_maze",
    "resolve_maze",
    "resolve_maze_source",
    "save_maze",
]


class MazeSpecError(ValueError):
    """A --maze value that names no maze, or a maze file that cannot be used."""


class MazeGenerationFailed(MazeSpecError):
    """A recipe that cannot make a maze from one particular seed (another seed may work)."""

    def __init__(self, name: str, seed: int, reason: str) -> None:
        super().__init__(f"Cannot generate '{name}' with seed {seed}: {reason}")
        self.seed = seed
        self.reason = reason


@dataclass(frozen=True)
class MazeSource:
    """Where a maze comes from. A recipe needs a seed to become a maze; the others ignore it."""

    kind: MazeKind
    name: str
    path: Path
    overrides: tuple[str, ...] = ()

    @property
    def generated(self) -> bool:
        return self.kind == "recipe"

    def recipe(self) -> MazeRecipe:
        if self.kind != "recipe":
            raise MazeSpecError(f"'{self.name}' is a {self.kind}, not a recipe.")

        try:
            return apply_overrides(load_recipe(self.path), self.overrides)
        except ConfigError as error:
            raise MazeSpecError(str(error)) from error

    def build(self, seed: int = 0) -> Maze:
        try:
            if self.kind == "layout":
                return load_layout(self.path)

            if self.kind == "saved":
                return load_saved_maze(self.path)

            return build_maze(self.recipe(), seed)
        except MazeSpecError:
            raise
        except GenerationError as error:
            raise MazeGenerationFailed(self.name, seed, str(error)) from error
        except (ValueError, OSError) as error:
            raise MazeSpecError(f"Invalid {self.kind} file '{self.path}': {error}") from error


class MazeRegistry:

    def __init__(self) -> None:
        self._sources: dict[str, MazeSource] = {}

    def register(self, source: MazeSource) -> None:
        if source.name in self._sources:
            other = self._sources[source.name]
            raise MazeSpecError(
                f"Maze name '{source.name}' is used twice: {other.kind} '{other.path}' and "
                f"{source.kind} '{source.path}'. Rename one of the files."
            )

        self._sources[source.name] = source

    def source(self, name: str) -> MazeSource:
        if name not in self._sources:
            raise MazeSpecError(f"Unknown maze '{name}'. Available: {', '.join(self.names())}")

        return self._sources[name]

    def create(self, name: str, seed: int = 0) -> Maze:
        return self.source(name).build(seed)

    def names(self) -> list[str]:
        return sorted(self._sources)

    def sources(self) -> list[MazeSource]:
        return [self._sources[name] for name in self.names()]


def create_maze_registry(
    layouts_dir: Path = LAYOUTS_DIR,
    recipes_dir: Path = RECIPES_DIR,
    saved_dir: Path = SAVED_DIR,
) -> MazeRegistry:
    registry = MazeRegistry()

    for kind, directory, pattern in (
        ("layout", layouts_dir, "*.txt"),
        ("recipe", recipes_dir, "*.toml"),
        ("saved", saved_dir, "*.json"),
    ):
        for path in sorted(directory.glob(pattern)):
            registry.register(MazeSource(kind=kind, name=path.stem, path=path))

    return registry


def resolve_maze_source(
    spec: str,
    overrides: list[str] | tuple[str, ...] = (),
    registry: MazeRegistry | None = None,
) -> MazeSource:
    """A registered name, or a path to a .txt layout, .toml recipe or .json saved maze."""

    registry = registry if registry is not None else create_maze_registry()

    if spec in registry.names():
        source = registry.source(spec)
    else:
        path = Path(spec)

        if path.suffix not in SUFFIX_KINDS and path.parent == Path("."):
            raise MazeSpecError(
                f"Unknown maze '{spec}'. Available: {', '.join(registry.names())} "
                f"(or a path to a .txt layout, .toml recipe or .json saved maze)."
            )

        if path.suffix not in SUFFIX_KINDS:
            raise MazeSpecError(
                f"Maze file '{path}' must end in {', '.join(SUFFIX_KINDS)}."
            )

        if not path.is_file():
            raise MazeSpecError(f"Maze file '{path}' does not exist.")

        source = MazeSource(kind=SUFFIX_KINDS[path.suffix], name=path.stem, path=path)

    if overrides:
        if not source.generated:
            raise MazeSpecError(
                f"--maze-set only applies to recipes; '{source.name}' is a {source.kind}."
            )

        source = replace(source, overrides=tuple(overrides))

    return source


def resolve_maze(
    spec: str,
    maze_seed: int = 0,
    overrides: list[str] | tuple[str, ...] = (),
    registry: MazeRegistry | None = None,
) -> Maze:
    return resolve_maze_source(spec, overrides, registry).build(maze_seed)


# Saved mazes: the full maze (tiles, start, pellets, origin), so a saved maze
# never depends on the generator version that made it.


def save_maze(maze: Maze, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"saved_maze_version": SAVED_MAZE_VERSION, "maze": maze_to_dict(maze)}
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")


def load_saved_maze(path: Path) -> Maze:
    data = json.loads(path.read_text(encoding="utf-8"))
    version = data.get("saved_maze_version") if isinstance(data, dict) else None

    if version != SAVED_MAZE_VERSION:
        raise MazeSpecError(
            f"'{path}' is not a saved maze of version {SAVED_MAZE_VERSION} "
            f"(found {version!r}); save it again with 'mazes generate --save'."
        )

    return maze_from_dict(data["maze"])
