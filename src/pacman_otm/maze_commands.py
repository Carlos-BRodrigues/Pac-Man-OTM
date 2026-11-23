"""
The 'mazes' command family and the maze options shared by every command:

    --maze SPEC  --maze-seed N  --maze-set KEY=VALUE ...

Wiring and printing only; mazes, rules and recipes do the work.
"""

import argparse
from dataclasses import replace
from pathlib import Path

from pacman_otm.cli_types import non_negative_int, positive_int
from pacman_otm.mazes.analysis import analyze
from pacman_otm.mazes.layout import format_layout
from pacman_otm.mazes.maze import Maze
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


def add_maze_options(parser: argparse.ArgumentParser, seed_help: str | None = None) -> None:
    """--maze-seed and --maze-set, for any command that takes a maze."""

    parser.add_argument(
        "--maze-seed",
        type=non_negative_int,
        default=0,
        help=seed_help or "Seed for a recipe maze (ignored by layouts and saved mazes). Default: 0.",
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


def add_maze_argument(parser: argparse.ArgumentParser) -> None:
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
    add_maze_options(parser)


def load_maze(spec: str, args: argparse.Namespace) -> tuple[MazeSource, Maze]:
    source = resolve_maze_source(spec, args.maze_set)
    return source, source.build(args.maze_seed)


def maze_label(source: MazeSource, maze: Maze, seed: int) -> str:
    """Used in result file names: a recipe maze is named with its seed."""
    return f"{maze.name}-seed{seed}" if source.generated else maze.name


# mazes list


def run_mazes_list(args: argparse.Namespace) -> None:
    registry = create_maze_registry()

    print(f"{'name':<16}{'kind':<8}{'size':>7}{'pellets':>9}  description")

    for source in registry.sources():
        try:
            if source.generated:
                recipe = source.recipe()
                size = f"{recipe.height}x{recipe.width}"
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
    source, maze = load_maze(args.spec, args)
    print(describe(source, maze, args.maze_seed))
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
    source, maze = load_maze(args.spec, args)
    rules = rules_to_check(source, args.rules)

    print(describe(source, maze, args.maze_seed))
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

    source, maze = load_maze(args.spec, args)
    violations = rules_to_check(source, args.rules).violations(maze.topography)
    highlights = {position for violation in violations for position in violation.positions}

    status = (
        f"{maze.name}: {len(violations)} rule violation(s)"
        if violations
        else f"{maze.name}: all rules hold"
    )
    print(describe(source, maze, args.maze_seed))

    for violation in violations:
        print_violation(violation, 10)

    run_maze_preview(maze, highlights, status, scale=args.scale)


# mazes generate


def run_mazes_generate(args: argparse.Namespace) -> None:
    source = resolve_maze_source(args.recipe, args.maze_set)

    if not source.generated:
        raise MazeSpecError(f"'{args.recipe}' is a {source.kind}; 'mazes generate' needs a recipe.")

    registry = create_maze_registry()
    seeds = range(args.seed, args.seed + args.count)

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
            name = args.save if args.count == 1 else f"{args.save}-{seed}"
            save_generated(maze, name, registry, force=args.force)


def save_generated(maze: Maze, name: str, registry, force: bool) -> None:
    path = SAVED_DIR / f"{name}.json"

    if name in registry.names():
        existing = registry.source(name)

        if existing.kind != "saved":
            raise MazeSpecError(f"Cannot save as '{name}': that name is a {existing.kind} ({existing.path}).")

        if not force:
            raise MazeSpecError(f"Saved maze '{name}' already exists ({path}); use --force to replace it.")

    # Saved under its own name; the origin keeps the recipe (with its name) and the seed.
    saved = Maze(
        topography=maze.topography,
        pacman_start=maze.pacman_start,
        pellets=maze.initial_pellets,
        origin=replace(maze.origin, name=name),
    )
    save_maze(saved, path)
    print(f"Saved maze '{name}' to {path}")


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
    generate.add_argument("--seed", type=non_negative_int, default=0, help="First maze seed. Default: 0.")
    generate.add_argument("--count", type=positive_int, default=1, help="Number of seeds. Default: 1.")
    generate.add_argument(
        "--save",
        metavar="NAME",
        default=None,
        help="Save as mazes/saved/NAME.json (NAME-SEED.json with --count > 1).",
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


def add_rules_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--rules",
        metavar="FILE|RECIPE",
        default=None,
        help="Extra rules: a TOML file's [[rules]] tables, or a recipe name.",
    )
