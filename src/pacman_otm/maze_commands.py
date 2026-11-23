"""
The 'mazes' command family and the maze options shared by every command:

    --maze SPEC  --maze-seed N  --maze-set KEY=VALUE ...

Wiring and printing only; mazes, rules and recipes do the work.
"""

import argparse
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from pacman_otm.cli_types import non_negative_int, positive_int
from pacman_otm.mazes.analysis import analyze
from pacman_otm.mazes.layout import LAYOUTS_DIR, format_layout
from pacman_otm.mazes.maze import Maze
from pacman_otm.mazes.origin import MazeOrigin
from pacman_otm.mazes.registry import (
    DEFAULT_MAZE,
    SAVED_DIR,
    MazeSource,
    MazeSpecError,
    create_maze_registry,
    resolve_maze_source,
    save_maze,
)
from pacman_otm.mazes.rules.base import RuleSet, Violation
from pacman_otm.mazes.rules.hard import HARD_RULES
from pacman_otm.mazes.rules.registry import RuleConfigError, rules_from_toml


RANDOM_SEED_HELP = (
    "Seed for a recipe maze. Default: a random seed, printed so the maze can be "
    "repeated. Ignored by layouts and saved mazes."
)


def add_maze_options(
    parser: argparse.ArgumentParser,
    seed_default: int | None = None,
    seed_help: str = RANDOM_SEED_HELP,
) -> None:
    """--maze-seed and --maze-set, for any command that takes a maze."""

    parser.add_argument(
        "--maze-seed",
        type=non_negative_int,
        default=seed_default,
        help=seed_help,
    )
    parser.add_argument(
        "--maze-set",
        metavar="KEY=VALUE",
        action="append",
        default=[],
        help=(
            "Override a recipe value, e.g. size=41x41, topography.extra_loops=0.3, "
            "rules.max_block.wall.size=4, rules.max_dead_ends=off. Repeatable."
        ),
    )


def add_maze_argument(parser: argparse.ArgumentParser, **seed_options) -> None:
    parser.add_argument(
        "--maze",
        metavar="SPEC",
        default=DEFAULT_MAZE,
        help=(
            f"Maze name ({', '.join(create_maze_registry().names())}) or a path to a .txt "
            f"layout, .toml recipe or .json saved maze. Default: {DEFAULT_MAZE}. "
            f"See 'mazes list'."
        ),
    )
    add_maze_options(parser, **seed_options)


def random_maze_seed() -> int:
    """A fresh seed from the OS. Only ever used when no seed was given, and always printed."""
    return secrets.randbelow(2**32)


def choose_maze_seed(source: MazeSource, seed: int | None) -> int:
    """The given seed, or for a recipe without one, a random seed that is announced."""

    if seed is not None:
        return seed

    if not source.generated:
        return 0

    seed = random_maze_seed()
    print(f"Maze seed: {seed}  (repeat this maze with --maze-seed {seed})")
    return seed


def load_maze(spec: str, args: argparse.Namespace) -> tuple[MazeSource, Maze, int]:
    """The maze of --maze/--maze-seed/--maze-set, and the seed it was built from."""

    source = resolve_maze_source(spec, args.maze_set)
    seed = choose_maze_seed(source, args.maze_seed)
    return source, source.build(seed), seed


def maze_label(source: MazeSource, maze: Maze, seed: int) -> str:
    """Used in result file names: a recipe maze is named with its seed."""
    return f"{maze.name}-seed{seed}" if source.generated else maze.name


@dataclass(frozen=True)
class ExperimentMazes:
    """The mazes of an experiment: a factory from the run's maze seed, and how to describe them."""

    factory: Callable[[int], Maze]
    label: str
    per_run: bool
    # Written once into results.json.
    info: dict[str, Any]


def experiment_mazes(
    spec: str,
    overrides: list[str] | tuple[str, ...],
    maze_seed: int | None,
) -> ExperimentMazes:
    """
    A recipe without --maze-seed gives every run its own maze, built from the
    run's maze seed (derive_run_seeds), so every controller sees the same maze
    sequence. A recipe with --maze-seed, a layout or a saved maze is one fixed maze.
    """
    source = resolve_maze_source(spec, overrides)

    if source.generated and maze_seed is None:
        return ExperimentMazes(
            factory=source.build,
            label=source.name,
            per_run=True,
            info={
                "maze_kind": source.kind,
                "maze_per_run": True,
                "maze_recipe": source.recipe().to_dict(),
            },
        )

    seed = maze_seed if maze_seed is not None else 0
    maze = source.build(seed)
    info: dict[str, Any] = {"maze_kind": source.kind, "maze_per_run": False}

    if source.generated:
        info["maze_seed"] = seed
        info["maze_recipe"] = source.recipe().to_dict()

    return ExperimentMazes(
        factory=lambda run_maze_seed: maze,
        label=maze_label(source, maze, seed),
        per_run=False,
        info=info,
    )


# mazes list


def run_mazes_list(args: argparse.Namespace) -> None:
    registry = create_maze_registry()

    print(f"{'name':<16}{'kind':<8}{'size':>7}{'pellets':>9}  description")

    for source in registry.sources():
        try:
            if source.generated:
                recipe = source.recipe()
                size = recipe.describe_size()
                pellets = "-"
                description = recipe.description
            else:
                maze = source.build()
                size = f"{maze.height}x{maze.width}"
                pellets = str(len(maze.initial_pellets))
                description = ""
        except MazeSpecError as error:
            size, pellets, description = "?", "?", f"ERROR: {error}"

        if source.name == DEFAULT_MAZE:
            description = f"(default) {description}".strip()

        print(f"{source.name:<16}{source.kind:<8}{size:>7}{pellets:>9}  {description}")


# mazes show / check / preview


def print_metrics(maze: Maze) -> None:
    for key, value in analyze(maze).to_dict().items():
        shown = f"{value:.3f}" if isinstance(value, float) else value
        print(f"  {key:<24}{shown}")


def describe(source: MazeSource, maze: Maze, seed: int) -> str:
    seed_text = f", seed {seed}" if source.generated else ""
    return (
        f"{maze.name} ({source.kind}{seed_text}): {maze.height}x{maze.width}, "
        f"{len(maze.initial_pellets)} pellets, start {maze.pacman_start}"
    )


def run_mazes_show(args: argparse.Namespace) -> None:
    source, maze, seed = load_maze(args.spec, args)
    print(describe(source, maze, seed))
    print(format_layout(maze), end="")
    print("metrics:")
    print_metrics(maze)


def rules_to_check(source: MazeSource, rules_spec: str | None) -> RuleSet:
    """The hard rules, a recipe's own rules, and optional extra rules (a TOML file or a recipe name)."""

    rules = HARD_RULES

    if source.generated:
        rules = rules + source.recipe().rule_set

    if rules_spec is None:
        return rules

    path = Path(rules_spec)

    if path.is_file():
        return rules + rules_from_toml(path)

    registry = create_maze_registry()

    if rules_spec in registry.names() and registry.source(rules_spec).generated:
        return rules + registry.source(rules_spec).recipe().rule_set

    raise RuleConfigError(f"--rules '{rules_spec}' is neither a TOML file nor a recipe name.")


def run_mazes_check(args: argparse.Namespace) -> None:
    source, maze, seed = load_maze(args.spec, args)
    rules = rules_to_check(source, args.rules)

    print(describe(source, maze, seed))
    print("metrics:")
    print_metrics(maze)

    print("rules:")
    violations = rules.violations(maze.topography)
    failed = {violation.rule for violation in violations}

    for rule in rules:
        print(f"  {'FAIL' if rule.describe() in failed else 'ok':<6}{rule.describe()}")

    if not violations:
        print("No violations.")
        return

    print(f"violations ({len(violations)}):")

    for violation in violations:
        print_violation(violation, args.max_positions)

    raise SystemExit(1)


def print_violation(violation: Violation, max_positions: int) -> None:
    print(f"  {violation.rule}: {violation.message}")

    if violation.positions:
        shown = ", ".join(str(position) for position in violation.positions[:max_positions])
        more = len(violation.positions) - max_positions
        suffix = f" ... and {more} more" if more > 0 else ""
        print(f"    at {shown}{suffix}")


def run_mazes_preview(args: argparse.Namespace) -> None:
    # Imported here so the text commands work without opening a display.
    from pacman_otm.visualization.preview import run_maze_preview

    source, maze, seed = load_maze(args.spec, args)
    violations = rules_to_check(source, args.rules).violations(maze.topography)
    highlights = {position for violation in violations for position in violation.positions}

    status = (
        f"{maze.name}: {len(violations)} rule violation(s)"
        if violations
        else f"{maze.name}: all rules hold"
    )
    print(describe(source, maze, seed))

    for violation in violations:
        print_violation(violation, 10)

    run_maze_preview(maze, highlights, status, scale=args.scale)


# mazes generate


def run_mazes_generate(args: argparse.Namespace) -> None:
    source = resolve_maze_source(args.recipe, args.maze_set)

    if not source.generated:
        raise MazeSpecError(f"'{args.recipe}' is a {source.kind}; 'mazes generate' needs a recipe.")

    first = args.seed if args.seed is not None else random_maze_seed()
    seeds = range(first, first + args.count)

    for seed in seeds:
        maze = source.build(seed)
        metrics = analyze(maze)

        print(
            f"{source.name} seed {seed}: {maze.height}x{maze.width}  "
            f"walkable={metrics.walkable_tiles}  loops={metrics.loops}  "
            f"dead_ends={metrics.dead_ends}  junctions={metrics.junction_share:.2f}  "
            f"longest_run={metrics.longest_straight_run}  longest_corridor={metrics.longest_corridor}"
        )

        if not args.quiet:
            print(format_layout(maze))

        if args.save is not None:
            target = args.save if args.count == 1 else _numbered(args.save, seed)
            save_named_maze(maze, target, as_layout=args.layout, force=args.force)


NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def save_named_maze(maze: Maze, target: str, as_layout: bool, force: bool) -> Path:
    """
    Save a maze. `target` is either a name, which registers the maze
    (mazes/saved/NAME.json, or mazes/layouts/NAME.txt with as_layout), or a
    path ending in .json or .txt, which writes just that file.

    A .json keeps everything, including how the maze was made. A .txt layout
    keeps tiles, pellets and start only, and can be edited by hand.
    """
    path = Path(target)

    if path.suffix in (".json", ".txt"):
        as_layout = path.suffix == ".txt"
        name = path.stem

        if path.exists() and not force:
            raise MazeSpecError(f"'{path}' already exists; use --force to replace it.")
    else:
        if not NAME_PATTERN.fullmatch(target):
            raise MazeSpecError(
                f"'{target}' is not a usable maze name: use letters, digits, '-', '_' and '.', "
                f"or give a path ending in .json or .txt."
            )

        name = target
        path = (LAYOUTS_DIR / f"{name}.txt") if as_layout else (SAVED_DIR / f"{name}.json")
        kind = "layout" if as_layout else "saved"
        registry = create_maze_registry()

        if name in registry.names():
            existing = registry.source(name)

            if existing.kind != kind:
                raise MazeSpecError(f"Cannot save as '{name}': that name is a {existing.kind} ({existing.path}).")

            if not force:
                raise MazeSpecError(f"Maze '{name}' already exists ({existing.path}); use --force to replace it.")

    if as_layout:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(format_layout(maze), encoding="utf-8")
    else:
        # Saved under its own name; the origin keeps the recipe (with its name) and the seed.
        origin = maze.origin if maze.origin is not None else MazeOrigin(source="layout", name=name)
        save_maze(
            Maze(
                topography=maze.topography,
                pacman_start=maze.pacman_start,
                pellets=maze.initial_pellets,
                origin=replace(origin, name=name),
            ),
            path,
        )

    print(f"Saved maze '{name}' to {path}" + (" (layout: edit pellets and 'P' by hand)" if as_layout else ""))
    return path


def run_mazes_save(args: argparse.Namespace) -> None:
    source, maze, seed = load_maze(args.spec, args)
    print(describe(source, maze, seed))
    save_named_maze(maze, args.target, as_layout=args.layout, force=args.force)


def add_mazes_parser(subparsers, add_scale_argument) -> None:
    mazes_parser = subparsers.add_parser(
        "mazes",
        help="List, show, check, preview or generate mazes (default: list).",
    )
    # 'mazes' alone lists, as before.
    mazes_parser.set_defaults(func=run_mazes_list)
    commands = mazes_parser.add_subparsers(dest="mazes_command")

    commands.add_parser("list", help="List layouts, recipes and saved mazes.").set_defaults(func=run_mazes_list)

    show = commands.add_parser("show", help="Print a maze as layout text, with its metrics.")
    show.add_argument("spec", metavar="SPEC")
    add_maze_options(show)
    show.set_defaults(func=run_mazes_show)

    check = commands.add_parser(
        "check",
        help="Check a maze against the hard rules, its recipe's rules and optional extra rules.",
        description=(
            "Print a maze's metrics and its rule violations with positions. The hard rules "
            "(size_bounds, connected, enclosed) are always checked, plus a recipe's own rules. "
            "Exits with status 1 if any rule fails."
        ),
    )
    check.add_argument("spec", metavar="SPEC")
    add_rules_argument(check)
    check.add_argument(
        "--max-positions",
        type=positive_int,
        default=10,
        help="Positions shown per violation. Default: 10.",
    )
    add_maze_options(check)
    check.set_defaults(func=run_mazes_check)

    preview = commands.add_parser(
        "preview",
        help="Show a maze in a window, with rule violations highlighted.",
    )
    preview.add_argument("spec", metavar="SPEC")
    add_rules_argument(preview)
    add_maze_options(preview)
    add_scale_argument(preview)
    preview.set_defaults(func=run_mazes_preview)

    generate = commands.add_parser(
        "generate",
        help="Generate mazes from a recipe: print them, and optionally save them.",
        description=(
            "Build one maze per seed (--seed, --seed+1, ...), print it with a metric summary, "
            "and with --save write it to mazes/saved/, where it becomes a named maze."
        ),
    )
    generate.add_argument("recipe", metavar="RECIPE")
    generate.add_argument(
        "--seed",
        type=non_negative_int,
        default=None,
        help="First maze seed. Default: random (every maze's seed is printed).",
    )
    generate.add_argument("--count", type=positive_int, default=1, help="Number of seeds. Default: 1.")
    generate.add_argument(
        "--save",
        metavar="NAME",
        default=None,
        help="Save each maze under NAME (NAME-SEED with --count > 1), or to a .json/.txt path. See 'mazes save'.",
    )
    generate.add_argument(
        "--layout",
        action="store_true",
        help="Save as an editable .txt layout in mazes/layouts/ instead of a .json saved maze.",
    )
    generate.add_argument("--force", action="store_true", help="Replace a saved maze of the same name.")
    generate.add_argument("--quiet", action="store_true", help="Print the metric summary only.")
    generate.add_argument(
        "--maze-set",
        metavar="KEY=VALUE",
        action="append",
        default=[],
        help="Override a recipe value (see 'simulate --help'). Repeatable.",
    )
    generate.set_defaults(func=run_mazes_generate)

    save = commands.add_parser(
        "save",
        help="Give any maze a name: save it as a .json saved maze or an editable .txt layout.",
        description=(
            "Build a maze (a recipe needs --maze-seed, or a random one is picked and printed) and save it. "
            "TARGET is a name, which registers the maze (mazes/saved/NAME.json, or mazes/layouts/NAME.txt "
            "with --layout), or a path ending in .json or .txt. A .json keeps how the maze was made; "
            "a .txt layout can be edited by hand: move 'P', add or remove '.' pellets."
        ),
    )
    save.add_argument("spec", metavar="SPEC")
    save.add_argument("target", metavar="NAME|PATH")
    save.add_argument("--layout", action="store_true", help="Save as a .txt layout in mazes/layouts/.")
    save.add_argument("--force", action="store_true", help="Replace an existing maze of the same name or file.")
    add_maze_options(save)
    save.set_defaults(func=run_mazes_save)


def _numbered(target: str, seed: int) -> str:
    """NAME -> NAME-SEED; path/NAME.txt -> path/NAME-SEED.txt."""
    path = Path(target)

    if path.suffix in (".json", ".txt"):
        return str(path.with_name(f"{path.stem}-{seed}{path.suffix}"))

    return f"{target}-{seed}"


def add_rules_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--rules",
        metavar="FILE|RECIPE",
        default=None,
        help="Extra rules: a TOML file's [[rules]] tables, or a recipe name.",
    )
