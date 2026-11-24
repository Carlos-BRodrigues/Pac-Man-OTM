"""
Maze sets: a named, fixed list of mazes to reuse across experiments.

A set is a TOML file in mazes/sets/, registered under its file stem:

    description = "Hand-picked mazes."
    mazes = ["classic", "classic-sparse", "grotto1"]

Entries are maze specs (layout or saved-maze names, or .txt/.json paths). Recipes
are not allowed: a set must name the same mazes every time, so save a recipe maze
first ('mazes save RECIPE NAME --maze-seed N'). A set name may not also be a maze name.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from pacman_otm.mazes.maze import Maze
from pacman_otm.mazes.registry import (
    MazeRegistry,
    MazeSource,
    MazeSpecError,
    create_maze_registry,
    resolve_maze_source,
)

SETS_DIR = Path(__file__).parent / "sets"


@dataclass(frozen=True)
class MazeSet:
    name: str
    description: str
    specs: tuple[str, ...]
    path: Path

    def sources(
        self,
        registry: MazeRegistry | None = None,
        ghost_count: int | None = None,
    ) -> list[MazeSource]:
        registry = registry if registry is not None else create_maze_registry()
        sources = []

        for spec in self.specs:
            try:
                source = resolve_maze_source(spec, registry=registry, ghost_count=ghost_count)
            except MazeSpecError as error:
                raise MazeSpecError(f"Maze set '{self.name}': {error}") from error

            if source.generated:
                raise MazeSpecError(
                    f"Maze set '{self.name}' lists the recipe '{spec}'. A set needs fixed mazes: "
                    f"save one with 'mazes save {spec} NAME --maze-seed N' and list NAME instead."
                )

            sources.append(source)

        return sources

    def build(self, registry: MazeRegistry | None = None, ghost_count: int | None = None) -> list[Maze]:
        """The set's mazes; ghost_count (--ghosts) gives each that many ghost spawns."""
        return [source.build() for source in self.sources(registry, ghost_count)]


def load_maze_set(path: Path) -> MazeSet:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise MazeSpecError(f"Invalid maze set '{path}': {error}") from error

    unknown = set(data) - {"description", "mazes"}

    if unknown:
        raise MazeSpecError(
            f"Maze set '{path}': unknown key(s) {', '.join(sorted(unknown))} "
            f"(expected 'description' and 'mazes')."
        )

    specs = data.get("mazes")

    if not isinstance(specs, list) or not specs or not all(isinstance(s, str) for s in specs):
        raise MazeSpecError(f"Maze set '{path}': 'mazes' must be a non-empty list of maze names.")

    description = data.get("description", "")

    if not isinstance(description, str):
        raise MazeSpecError(f"Maze set '{path}': 'description' must be a string.")

    return MazeSet(name=path.stem, description=description, specs=tuple(specs), path=path)


def maze_sets(
    sets_dir: Path = SETS_DIR,
    registry: MazeRegistry | None = None,
) -> dict[str, MazeSet]:
    """Every set in sets_dir, by name. A set named like a maze is an error."""

    registry = registry if registry is not None else create_maze_registry()
    maze_names = set(registry.names())
    sets = {}

    for path in sorted(sets_dir.glob("*.toml")):
        if path.stem in maze_names:
            source = registry.source(path.stem)
            raise MazeSpecError(
                f"Name '{path.stem}' is used by maze set '{path}' and {source.kind} "
                f"'{source.path}'. Rename one of the files."
            )

        sets[path.stem] = load_maze_set(path)

    return sets
