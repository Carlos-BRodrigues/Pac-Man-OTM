"""
Recipes: how to make a maze, as data. A recipe names a size, a shape, a
topography generator with its parameters, a set of rules, and content placers.
The same recipe and seed always give the same maze (see pipeline.build_maze).

Hand-written recipes are TOML files (mazes/recipes/*.toml); recipes saved into
results are the JSON form of `MazeRecipe.to_dict()`, which lists every value,
defaults included, so a result says exactly how its maze was made.
"""

import tomllib
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, get_type_hints

from pacman_otm.mazes.config import ConfigError, check_keys, convert, keyword_params
from pacman_otm.mazes.generation.content import PELLET_PLACERS, START_PLACERS
from pacman_otm.mazes.generation.errors import GenerationError
from pacman_otm.mazes.generation.registry import GENERATORS, SHAPES
from pacman_otm.mazes.grid import MAX_MAZE_SIZE, MIN_MAZE_SIZE, TILE_KINDS
from pacman_otm.mazes.origin import deep_freeze, deep_thaw
from pacman_otm.mazes.rules.base import Rule, RuleSet
from pacman_otm.mazes.rules.registry import rule_from_config

TOP_LEVEL_KEYS = ("name", "description", "size", "shape", "topography", "rules", "content")
CONTENT_KEYS = ("pellets", "start")

DEFAULT_SHAPE = "rectangle"
DEFAULT_GENERATOR = "lattice"
DEFAULT_PELLETS = "all_corridors"
DEFAULT_START = "center"


class RecipeError(ConfigError):
    """A recipe that cannot be used; the message names the file and field."""


@dataclass(frozen=True)
class Component:
    """A named implementation (shape, placer) and its keyword parameters."""

    name: str
    params: frozendict[str, Any]

    def to_dict(self, key: str) -> dict[str, Any]:
        return {key: self.name, **deep_thaw(self.params)}


# An inclusive (min, max) range; min == max for a fixed size.
SizeRange = tuple[int, int]


@dataclass(frozen=True)
class MazeRecipe:
    name: str
    description: str
    # Each maze's size is drawn from these ranges with the maze seed.
    heights: SizeRange
    widths: SizeRange
    shape: Component
    generator: str
    # The generator's parameter dataclass, e.g. LatticeParams.
    topography: Any
    rules: tuple[Rule, ...]
    pellets: Component
    start: Component

    @property
    def rule_set(self) -> RuleSet:
        return RuleSet(self.rules)

    @property
    def fixed_size(self) -> tuple[int, int] | None:
        """(height, width) when the size is not a range, else None."""

        if self.heights[0] == self.heights[1] and self.widths[0] == self.widths[1]:
            return self.heights[0], self.widths[0]

        return None

    def describe_size(self) -> str:
        """'31x31', or '10..50x20..50' for ranges."""

        def text(low: int, high: int) -> str:
            return str(low) if low == high else f"{low}..{high}"

        return f"{text(*self.heights)}x{text(*self.widths)}"

    def to_dict(self) -> dict[str, Any]:
        # asdict also turns nested parameter dataclasses (sculpt's lattice) into tables.
        topography = asdict(self.topography)

        return deep_thaw(
            {
                "name": self.name,
                "description": self.description,
                "size": {"height": _size_value(self.heights), "width": _size_value(self.widths)},
                "shape": self.shape.to_dict("kind"),
                "topography": {"generator": self.generator, **topography},
                "rules": [rule.to_dict() for rule in self.rules],
                "content": {
                    "pellets": self.pellets.to_dict("placer"),
                    "start": self.start.to_dict("placer"),
                },
            }
        )


def recipe_from_dict(data: dict[str, Any], default_name: str = "recipe") -> MazeRecipe:
    """Validate plain recipe data (from TOML or JSON). Errors name the field."""

    try:
        return _recipe_from_dict(data, default_name)
    except RecipeError:
        raise
    except ConfigError as error:
        raise RecipeError(str(error)) from error


def _recipe_from_dict(data: dict[str, Any], default_name: str) -> MazeRecipe:
    if not isinstance(data, dict):
        raise RecipeError("A recipe must be a table of keys.")

    check_keys(data, TOP_LEVEL_KEYS, "recipe", "a recipe")

    name = convert(data.get("name", default_name), str, "name")
    description = convert(data.get("description", ""), str, "description")

    size = _table(data.get("size"), "size", required=True)
    check_keys(size, ("height", "width"), "size", "size")

    for key in ("height", "width"):
        if key not in size:
            raise RecipeError(f"size.{key}: missing.")

    heights = _size_range(size["height"], "size.height")
    widths = _size_range(size["width"], "size.width")

    shape = _component(data.get("shape"), "shape", "kind", DEFAULT_SHAPE, SHAPES, skip=3)

    topography_data = dict(_table(data.get("topography"), "topography"))
    generator = convert(topography_data.pop("generator", DEFAULT_GENERATOR), str, "topography.generator")

    if generator not in GENERATORS:
        raise RecipeError(
            f"topography.generator: unknown generator '{generator}'; "
            f"known generators are {', '.join(GENERATORS)}."
        )

    topography = _params_dataclass(GENERATORS[generator][0], topography_data, "topography", f"generator '{generator}'")

    rules_data = data.get("rules", [])

    if not isinstance(rules_data, list):
        raise RecipeError("rules: expected a list of rule tables ([[rules]] in TOML).")

    rules = tuple(rule_from_config(rule, f"rules[{index}]") for index, rule in enumerate(rules_data))

    content = _table(data.get("content"), "content")
    check_keys(content, CONTENT_KEYS, "content", "content")

    pellets = _component(content.get("pellets"), "content.pellets", "placer", DEFAULT_PELLETS, PELLET_PLACERS, skip=3)
    start = _component(content.get("start"), "content.start", "placer", DEFAULT_START, START_PLACERS, skip=2)

    if start.name == "layout" and "path" not in start.params and shape.name != "layout":
        raise RecipeError(
            "content.start: placer 'layout' needs content.start.path, or a shape of kind 'layout'."
        )

    return MazeRecipe(
        name=name,
        description=description,
        heights=heights,
        widths=widths,
        shape=shape,
        generator=generator,
        topography=topography,
        rules=rules,
        pellets=pellets,
        start=start,
    )


def load_recipe(path: Path) -> MazeRecipe:
    """Read a TOML recipe. Relative layout paths are taken relative to the recipe file."""

    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
    except tomllib.TOMLDecodeError as error:
        raise RecipeError(f"{path.name}: invalid TOML: {error}") from error

    _resolve_relative_paths(data, path.parent)

    try:
        return recipe_from_dict(data, default_name=path.stem)
    except ConfigError as error:
        raise RecipeError(f"{path.name}: {error}") from error


def apply_overrides(recipe: MazeRecipe, overrides: list[str] | tuple[str, ...]) -> MazeRecipe:
    """
    Apply KEY=VALUE overrides, in order, then validate the result. Examples:

        size=41x41                      size.height=41
        size=11x21..51x51 (a range)     size.width=[21, 51]
        shape.kind=ellipse              topography.extra_loops=0.3
        content.pellets.placer=density  content.pellets.p=0.4
        rules.max_dead_ends.count=2     rules.max_block.wall.size=4
        rules.max_dead_ends=off

    Setting shape.kind, topography.generator or a placer clears that table's
    other parameters. Setting a parameter of a rule the recipe lacks adds it.
    Values are read as TOML (numbers, true/false, [lists], "text") or as plain text.
    """
    if not overrides:
        return recipe

    data = recipe.to_dict()

    for override in overrides:
        key, separator, raw = override.partition("=")

        if not separator or not key.strip():
            raise RecipeError(f"--maze-set '{override}': expected KEY=VALUE.")

        try:
            _apply(data, key.strip().split("."), _parse_value(raw.strip()))
        except RecipeError as error:
            raise RecipeError(f"--maze-set '{override}': {error}") from None

    try:
        return recipe_from_dict(data, default_name=recipe.name)
    except ConfigError as error:
        raise RecipeError(f"after --maze-set: {error}") from error


# Validation helpers


def _size_range(value: Any, where: str) -> SizeRange:
    """A fixed size (31) or an inclusive range ([10, 50]), within the maze bounds."""

    if isinstance(value, list | tuple):
        low, high = convert(value, tuple[int, int], where)
    else:
        low = high = convert(value, int, where)

    for bound in (low, high):
        if not MIN_MAZE_SIZE <= bound <= MAX_MAZE_SIZE:
            raise RecipeError(f"{where}: sizes must be between {MIN_MAZE_SIZE} and {MAX_MAZE_SIZE}, got {bound}.")

    if low > high:
        raise RecipeError(f"{where}: the range [{low}, {high}] runs backwards; use [{high}, {low}].")

    return low, high


def _size_value(sizes: SizeRange) -> int | list[int]:
    return sizes[0] if sizes[0] == sizes[1] else list(sizes)


def _table(value: Any, where: str, required: bool = False) -> dict[str, Any]:
    if value is None:
        if required:
            raise RecipeError(f"{where}: missing.")
        return {}

    if not isinstance(value, dict):
        raise RecipeError(f"{where}: expected a table, got {value!r}.")

    return value


def _component(value: Any, where: str, key: str, default: str, implementations, skip: int) -> Component:
    table = dict(_table(value, where))
    name = convert(table.pop(key, default), str, f"{where}.{key}")

    if name not in implementations:
        raise RecipeError(
            f"{where}.{key}: unknown {key} '{name}'; known are {', '.join(implementations)}."
        )

    params = keyword_params(implementations[name], table, where, f"{key} '{name}'", skip=skip)
    return Component(name=name, params=deep_freeze(params))


def _params_dataclass(params_class, values: dict[str, Any], where: str, owner: str):
    hints = get_type_hints(params_class)
    known = [field.name for field in fields(params_class)]
    check_keys(values, known, where, owner)

    converted = {
        key: convert(value, hints[key], f"{where}.{key}")
        for key, value in values.items()
    }

    try:
        return params_class(**converted)
    except GenerationError as error:
        # The params class already names the field (e.g. "topography.spacing: ...").
        raise RecipeError(str(error)) from None


def _resolve_relative_paths(data: dict[str, Any], base: Path) -> None:
    """A layout path relative to the recipe file, if such a file exists there."""

    tables = [data.get("shape")]

    if isinstance(data.get("content"), dict):
        tables.append(data["content"].get("start"))

    for table in tables:
        if isinstance(table, dict) and isinstance(table.get("path"), str):
            candidate = base / table["path"]

            if not Path(table["path"]).is_absolute() and candidate.is_file():
                table["path"] = str(candidate)


# Overrides


def _parse_value(raw: str) -> Any:
    try:
        return tomllib.loads(f"value = {raw}")["value"]
    except tomllib.TOMLDecodeError:
        return raw


def _apply(data: dict[str, Any], parts: list[str], value: Any) -> None:
    head, rest = parts[0], parts[1:]

    if head in ("name", "description") and not rest:
        data[head] = value
        return

    if head == "size":
        _apply_size(data, rest, value)
        return

    if head == "shape":
        _apply_table(data["shape"], rest, value, "kind", "shape")
        return

    if head == "topography":
        _apply_table(data["topography"], rest, value, "generator", "topography")
        return

    if head == "content" and len(rest) >= 2 and rest[0] in CONTENT_KEYS:
        _apply_table(data["content"][rest[0]], rest[1:], value, "placer", f"content.{rest[0]}")
        return

    if head == "rules" and rest:
        _apply_rule(data["rules"], rest, value)
        return

    raise RecipeError(
        "unknown key; use name, description, size, size.height, size.width, shape.<param>, "
        "topography.<param>, rules.<rule>.<param>, rules.<rule>=off, "
        "content.pellets.<param> or content.start.<param>."
    )


def _apply_size(data: dict[str, Any], rest: list[str], value: Any) -> None:
    if rest in (["height"], ["width"]):
        data["size"][rest[0]] = value
        return

    if rest:
        raise RecipeError("size takes HxW, or size.height / size.width.")

    if isinstance(value, int) and not isinstance(value, bool):
        data["size"] = {"height": value, "width": value}
        return

    # HxW, or a range HxW..HxW
    low, dots, high = str(value).lower().partition("..")
    low_size = _parse_size(low, value)
    high_size = _parse_size(high, value) if dots else low_size

    data["size"] = {
        "height": _size_value((low_size[0], high_size[0])),
        "width": _size_value((low_size[1], high_size[1])),
    }


def _parse_size(text: str, value: Any) -> tuple[int, int]:
    height, separator, width = text.strip().partition("x")

    if not separator or not height.isdigit() or not width.isdigit():
        raise RecipeError(
            f"size: expected HxW such as 41x41, or a range such as 11x21..51x51, got {value!r}."
        )

    return int(height), int(width)


def _apply_table(table: dict[str, Any], rest: list[str], value: Any, selector: str, where: str) -> None:
    if len(rest) != 1:
        raise RecipeError(f"expected {where}.<param>.")

    if rest[0] == selector:
        # A different implementation takes different parameters.
        table.clear()

    table[rest[0]] = value


def _apply_rule(rules: list[dict[str, Any]], rest: list[str], value: Any) -> None:
    name, rest = rest[0], rest[1:]
    match = {"rule": name}

    # max_block is picked by its tile: rules.max_block.wall.size=4
    if name == "max_block":
        if not rest:
            raise RecipeError("max_block needs its tile: rules.max_block.<tile>.size or rules.max_block.<tile>=off.")

        match["tile"], rest = rest[0], rest[1:]

        if match["tile"] not in TILE_KINDS:
            raise RecipeError(
                f"rules.max_block.<tile>: tile must be one of {', '.join(TILE_KINDS)}, "
                f"got '{match['tile']}'."
            )

    matches = [rule for rule in rules if all(rule.get(key) == item for key, item in match.items())]
    label = ".".join(match[key] for key in ("rule", "tile") if key in match)

    if not rest:
        if value != "off":
            raise RecipeError(f"use rules.{label}=off to remove it, or rules.{label}.<param>=VALUE.")

        if not matches:
            raise RecipeError(f"the recipe has no rule {label} to remove.")

        rules[:] = [rule for rule in rules if rule not in matches]
        return

    if len(rest) != 1:
        raise RecipeError(f"expected rules.{label}.<param>.")

    if len(matches) > 1:
        raise RecipeError(f"the recipe has {len(matches)} {label} rules; the key is ambiguous.")

    if matches:
        matches[0][rest[0]] = value
    else:
        rules.append({**match, rest[0]: value})
