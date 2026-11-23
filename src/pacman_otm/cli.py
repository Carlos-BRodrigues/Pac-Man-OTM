import argparse
from datetime import datetime
from pathlib import Path

from pacman_otm.mazes.analysis import analyze
from pacman_otm.mazes.layout import format_layout
from pacman_otm.mazes.rules.hard import HARD_RULES
from pacman_otm.mazes.rules.registry import RuleConfigError, rules_from_toml
from pacman_otm.mazes.registry import (
    DEFAULT_MAZE,
    MazeSpecError,
    create_maze_registry,
    resolve_maze,
)
from pacman_otm.controllers.manual.manual import ManualController
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.runner import run_simulation
from pacman_otm.experiments.runner import ExperimentRunner

from pacman_otm.controllers.registry import create_controller_registry


from pacman_otm.simulation.result import SimulationResult
from pacman_otm.simulation.replay import ReplayPlayer
from pacman_otm.visualization.pygame_renderer import PygameRenderer
from pacman_otm.visualization.live import LivePygameVisualizer
from pacman_otm.visualization.replay import ReplayPygameVisualizer
from pacman_otm.visualization.keyboard import PygameKeyboardInput
from pacman_otm.visualization.sprite_preview import run_sprite_preview

RESULTS_DIR = Path("results")


def resolve_output_path(output: str | None, label: str) -> Path:
    """
    No --output: an auto-named file in results/. A bare file name goes into
    results/; a path with a directory is used as given.
    """
    if output is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return RESULTS_DIR / f"{label}_{timestamp}.json"

    path = Path(output)

    if path.parent == Path("."):
        return RESULTS_DIR / path

    return path


def save_result(
    result: SimulationResult,
    args: argparse.Namespace,
    label: str,
) -> None:
    if args.no_save:
        return

    path = resolve_output_path(args.output, label)
    result.save_json(path)
    print(f"Saved result to {path}")


def run_simulate(args: argparse.Namespace) -> None:
    maze = resolve_maze(args.maze)
    engine = SimulationEngine(maze)
    controller = create_controller(args.controller, maze, args.seed)

    visualizer = None

    if args.visualize:
        renderer = PygameRenderer(maze, scale=args.scale)
        visualizer = LivePygameVisualizer(renderer)

    try:
        result = run_simulation(
            engine=engine,
            controller=controller,
            max_steps=args.max_steps,
            on_frame=visualizer if visualizer is not None else None,
        )

        if visualizer is not None and visualizer.renderer.is_open:
            visualizer.wait_until_closed()

    finally:
        if visualizer is not None:
            visualizer.close()

    print(result.metrics)

    if args.show_history:
        for entry in result.history_summary():
            print(entry)

    save_result(result, args, label=f"{args.controller}_{maze.name}")


def run_play(args: argparse.Namespace) -> None:
    maze = resolve_maze(args.maze)
    engine = SimulationEngine(maze)

    renderer = PygameRenderer(maze, scale=args.scale)
    # Arcade-style "READY!" hold before Pac-Man starts moving
    visualizer = LivePygameVisualizer(renderer, ready_seconds=2.0)
    controller = ManualController(
        maze=maze,
        direction_source=PygameKeyboardInput(renderer),
    )

    try:
        result = run_simulation(
            engine=engine,
            controller=controller,
            max_steps=args.max_steps,
            on_frame=visualizer,
        )

        if renderer.is_open:
            visualizer.wait_until_closed()

    finally:
        visualizer.close()

    print(result.metrics)
    save_result(result, args, label=f"manual_{maze.name}")


def run_experiment(args: argparse.Namespace) -> None:
    maze = resolve_maze(args.maze)
    name = args.name or f"{args.controller}_{maze.name}"

    print(
        f"Experiment '{name}': controller={args.controller}  maze={maze.name}  "
        f"runs={args.runs}  seed={args.seed}"
    )

    width = len(str(args.runs))

    def report_run(run_index: int, result: SimulationResult) -> None:
        metrics = result.metrics
        print(
            f"  run {run_index + 1:>{width}}/{args.runs}  "
            f"steps={metrics.total_steps:>5}  "
            f"collected={metrics.completion_rate:>7.1%}  "
            f"{metrics.termination_reason}"
        )

    experiment = ExperimentRunner(
        # One fixed maze for now; the maze seed is recorded for generated mazes later.
        maze_factory=lambda maze_seed: maze,
        controller_factory=lambda maze, seed: create_controller(
            args.controller,
            maze,
            seed,
        ),
        controller_name=args.controller,
        experiment_name=name,
        maze_label=maze.name,
        output_root=args.output_dir,
        seed=args.seed,
        max_steps=args.max_steps,
        on_run=report_run,
    )

    results = experiment.run(args.runs)

    completed = sum(1 for run in results.runs if run.metrics.completed)
    mean_steps = sum(run.metrics.total_steps for run in results.runs) / len(results.runs)

    print("=" * 40)
    print(f"Completed runs: {completed}/{len(results.runs)}")
    print(f"Mean steps: {mean_steps:.1f}")
    print(f"Output directory: {results.output_dir}")


def run_replay(args: argparse.Namespace) -> None:
    input_path = Path(args.input)

    if not input_path.exists() and (RESULTS_DIR / input_path).exists():
        input_path = RESULTS_DIR / input_path

    result = SimulationResult.load_json(input_path)

    if result.maze is None:
        raise ValueError("The saved result does not contain a maze.")

    replay = ReplayPlayer(result)
    renderer = PygameRenderer(result.maze, scale=args.scale)
    visualizer = ReplayPygameVisualizer(
        renderer=renderer,
        replay=replay,
        fps=args.fps,
    )

    try:
        visualizer.run()
    finally:
        visualizer.close()


def run_sprites(args: argparse.Namespace) -> None:
    run_sprite_preview(scale=args.scale if args.scale is not None else 6)


def print_metrics(maze) -> None:
    for key, value in analyze(maze).to_dict().items():
        shown = f"{value:.3f}" if isinstance(value, float) else value
        print(f"  {key:<24}{shown}")


def run_mazes_show(args: argparse.Namespace) -> None:
    maze = resolve_maze(args.spec)
    print(
        f"{maze.name}: {maze.height}x{maze.width}, "
        f"{len(maze.initial_pellets)} pellets, start {maze.pacman_start}"
    )
    print(format_layout(maze), end="")
    print("metrics:")
    print_metrics(maze)


def run_mazes_check(args: argparse.Namespace) -> None:
    maze = resolve_maze(args.spec)
    rules = HARD_RULES

    if args.rules is not None:
        path = Path(args.rules)

        if not path.is_file():
            raise RuleConfigError(f"Rules file '{path}' does not exist.")

        rules = rules + rules_from_toml(path)

    print(f"{maze.name}: {maze.height}x{maze.width}")
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
        print(f"  {violation.rule}: {violation.message}")

        if violation.positions:
            shown = ", ".join(str(position) for position in violation.positions[:args.max_positions])
            more = len(violation.positions) - args.max_positions
            suffix = f" ... and {more} more" if more > 0 else ""
            print(f"    at {shown}{suffix}")

    raise SystemExit(1)


def run_mazes_list(args: argparse.Namespace) -> None:
    registry = create_maze_registry()

    print(f"{'name':<16}{'size':>8}{'walkable':>10}{'pellets':>9}")

    for name in registry.names():
        maze = registry.create(name)
        size = f"{maze.height}x{maze.width}"
        default = "  (default)" if name == DEFAULT_MAZE else ""
        print(
            f"{name:<16}{size:>8}{len(maze.walkable_positions()):>10}"
            f"{len(maze.initial_pellets):>9}{default}"
        )


def create_controller(name, maze, seed=42):
    registry = create_controller_registry()
    return registry.create(name, maze, seed)


def non_negative_int(text: str) -> int:
    value = int(text)

    if value < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {value}")

    return value


def positive_int(text: str) -> int:
    value = int(text)

    if value <= 0:
        raise argparse.ArgumentTypeError(f"must be > 0, got {value}")

    return value


def add_scale_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--scale",
        type=positive_int,
        default=None,
        help="Pixel scale of the 8x8 tiles (whole number). Default: the largest that fits the screen.",
    )


def add_maze_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--maze",
        metavar="NAME|PATH",
        default=DEFAULT_MAZE,
        help=(
            f"Maze name ({', '.join(create_maze_registry().names())}) or a path to "
            f"a .txt layout. Default: {DEFAULT_MAZE}. See the 'mazes' command."
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pacman-otm",
        description="Pac-Man Optimization and Testing Framework",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    # SIMULATE
    simulate_parser = subparsers.add_parser(
        "simulate",
        help="Run a single simulation.",
    )
    add_maze_argument(simulate_parser)
    simulate_parser.add_argument(
        "--max-steps",
        type=positive_int,
        default=1000,
    )
    simulate_parser.add_argument(
        "--show-history",
        action="store_true",
    )
    simulate_parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Result file. A bare name is saved in results/. Default: auto-named in results/.",
    )
    simulate_parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not save the result.",
    )
    simulate_parser.add_argument(
        "--seed",
        type=non_negative_int,
        default=42,
        help="Controller seed (used by stochastic controllers).",
    )
    simulate_parser.add_argument(
        "--controller",
        choices=create_controller_registry().names(),
        default="nearest-pellet",
    )

    simulate_parser.add_argument(
        "--visualize",
        action="store_true",
        help="Show the simulation live in Pygame.",
    )

    add_scale_argument(simulate_parser)
    simulate_parser.set_defaults(func=run_simulate)

    # PLAY
    play_parser = subparsers.add_parser(
        "play",
        help="Play manually in a Pygame window (arrows/WASD, Esc to quit).",
    )
    add_maze_argument(play_parser)
    play_parser.add_argument(
        "--max-steps",
        type=positive_int,
        default=1000,
    )
    play_parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Result file. A bare name is saved in results/. Default: auto-named in results/.",
    )
    play_parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not save the result.",
    )
    add_scale_argument(play_parser)
    play_parser.set_defaults(func=run_play)

    # EXPERIMENT
    experiment_parser = subparsers.add_parser(
        "experiment",
        help="Run a batch of simulations.",
        description=(
            "Run one controller many times. The experiment seed fixes every run's "
            "maze and controller seeds, so running different controllers with the "
            "same --seed compares them on the same maze sequence."
        ),
    )
    add_maze_argument(experiment_parser)
    experiment_parser.add_argument(
        "--runs",
        type=positive_int,
        default=10,
    )
    experiment_parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Experiment directory name. Default: <controller>_<maze>.",
    )
    experiment_parser.add_argument(
        "--output-dir",
        type=str,
        default="results",
    )
    experiment_parser.add_argument(
        "--seed",
        type=non_negative_int,
        default=42,
        help=(
            "Experiment seed: fixes every run's maze and controller seeds; "
            "the same seed gives every controller the same maze sequence."
        ),
    )
    experiment_parser.add_argument(
        "--max-steps",
        type=positive_int,
        default=1000,
    )
    experiment_parser.add_argument(
        "--controller",
        choices=create_controller_registry().names(),
        default="nearest-pellet",
    )
    experiment_parser.set_defaults(func=run_experiment)

    # REPLAY

    replay_parser = subparsers.add_parser(
        "replay",
        help="Replay a previously saved simulation.",
    )

    replay_parser.add_argument(
        "input",
        type=str,
        help="Saved simulation JSON file (also looked up in results/).",
    )

    replay_parser.add_argument(
        "--fps",
        type=positive_int,
        default=10,
        help="Initial replay speed.",
    )

    add_scale_argument(replay_parser)
    replay_parser.set_defaults(func=run_replay)

    # SPRITES
    sprites_parser = subparsers.add_parser(
        "sprites",
        help="Preview the player animation and death sequence.",
    )
    add_scale_argument(sprites_parser)
    sprites_parser.set_defaults(func=run_sprites)

    # MAZES
    mazes_parser = subparsers.add_parser(
        "mazes",
        help="List, show or check mazes (default: list).",
    )
    # 'mazes' alone lists, as before.
    mazes_parser.set_defaults(func=run_mazes_list)
    mazes_subparsers = mazes_parser.add_subparsers(dest="mazes_command")

    mazes_list_parser = mazes_subparsers.add_parser(
        "list",
        help="List the available mazes.",
    )
    mazes_list_parser.set_defaults(func=run_mazes_list)

    mazes_show_parser = mazes_subparsers.add_parser(
        "show",
        help="Print a maze as layout text, with its metrics.",
    )
    mazes_show_parser.add_argument("spec", metavar="NAME|PATH")
    mazes_show_parser.set_defaults(func=run_mazes_show)

    mazes_check_parser = mazes_subparsers.add_parser(
        "check",
        help="Check a maze against the hard rules (and optional extra rules).",
        description=(
            "Print a maze's metrics and its rule violations with positions. "
            "The hard rules (size_bounds, connected, enclosed) are always checked. "
            "Exits with status 1 if any rule fails."
        ),
    )
    mazes_check_parser.add_argument("spec", metavar="NAME|PATH")
    mazes_check_parser.add_argument(
        "--rules",
        metavar="FILE.toml",
        default=None,
        help="TOML file whose [[rules]] tables are checked as well.",
    )
    mazes_check_parser.add_argument(
        "--max-positions",
        type=positive_int,
        default=10,
        help="Positions shown per violation. Default: 10.",
    )
    mazes_check_parser.set_defaults(func=run_mazes_check)

    args = parser.parse_args()

    try:
        args.func(args)
    except (MazeSpecError, RuleConfigError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
