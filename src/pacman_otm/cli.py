import argparse
from datetime import datetime
from pathlib import Path

from pacman_otm.cli_types import non_negative_int, positive_int
from pacman_otm.maze_commands import (
    add_maze_argument,
    add_mazes_parser,
    experiment_mazes,
    load_maze,
    maze_label,
)
from pacman_otm.mazes.analysis import analyze
from pacman_otm.mazes.config import ConfigError
from pacman_otm.mazes.generation.errors import GenerationError
from pacman_otm.mazes.registry import MazeSpecError
from pacman_otm.controllers.manual.manual import ManualController
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.runner import run_simulation
from pacman_otm.experiments.runner import ExperimentRunner

from pacman_otm.controllers.registry import create_controller_registry


from pacman_otm.simulation.result import SimulationResult
from pacman_otm.simulation.replay import ResultSequence
from pacman_otm.visualization.pygame_renderer import PygameRenderer
from pacman_otm.visualization.experiment import ExperimentVisualizer
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
    # Not saved unless asked for: --save (auto-named) or --output NAME.
    if not args.save and args.output is None:
        return

    path = resolve_output_path(args.output, label)
    result.save_json(path)
    print(f"Saved result to {path}")


def run_simulate(args: argparse.Namespace) -> None:
    source, maze, maze_seed = load_maze(args.maze, args)
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

    save_result(result, args, label=f"{args.controller}_{maze_label(source, maze, maze_seed)}")


def run_play(args: argparse.Namespace) -> None:
    source, maze, maze_seed = load_maze(args.maze, args)
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
    save_result(result, args, label=f"manual_{maze_label(source, maze, maze_seed)}")


def run_experiment(args: argparse.Namespace) -> None:
    mazes = experiment_mazes(args.maze, args.maze_set, args.maze_seed)
    name = args.name or f"{args.controller}_{mazes.label}"

    print(
        f"Experiment '{name}': controller={args.controller}  maze={mazes.label}"
        f"{' (a new maze per run)' if mazes.per_run else ''}  runs={args.runs}  seed={args.seed}"
    )

    width = len(str(args.runs))

    visualizer = (
        ExperimentVisualizer(total_runs=args.runs, scale=args.scale, fps=args.fps)
        if args.visualize
        else None
    )

    def report_run(run_index: int, result: SimulationResult) -> None:
        metrics = result.metrics
        maze_text = ""

        if mazes.per_run:
            maze_metrics = analyze(result.maze)
            maze_text = (
                f"  maze seed={result.maze.origin.seed} walkable={maze_metrics.walkable_tiles} "
                f"loops={maze_metrics.loops}"
            )

        print(
            f"  run {run_index + 1:>{width}}/{args.runs}  "
            f"steps={metrics.total_steps:>5}  "
            f"collected={metrics.completion_rate:>7.1%}  "
            f"{metrics.termination_reason}{maze_text}"
        )

    experiment = ExperimentRunner(
        maze_factory=mazes.factory,
        controller_factory=lambda maze, seed: create_controller(
            args.controller,
            maze,
            seed,
        ),
        controller_name=args.controller,
        experiment_name=name,
        maze_label=mazes.label,
        maze_info=mazes.info,
        output_root=args.output_dir,
        seed=args.seed,
        max_steps=args.max_steps,
        on_run=report_run,
        on_run_start=visualizer,
    )

    try:
        results = experiment.run(args.runs)

        if visualizer is not None:
            visualizer.wait_until_closed()
    finally:
        if visualizer is not None:
            visualizer.close()

    completed = sum(1 for run in results.runs if run.metrics.completed)
    mean_steps = sum(run.metrics.total_steps for run in results.runs) / len(results.runs)

    print("=" * 40)

    if results.stopped_early:
        print(f"Stopped after {len(results.runs)} of {args.runs} runs: the window was closed.")

    print(f"Completed runs: {completed}/{len(results.runs)}")
    print(f"Mean steps: {mean_steps:.1f}")
    print(f"Output directory: {results.output_dir}")


def run_replay(args: argparse.Namespace) -> None:
    input_path = Path(args.input)

    if not input_path.exists() and (RESULTS_DIR / input_path).exists():
        input_path = RESULTS_DIR / input_path

    try:
        runs = ResultSequence.from_path(input_path)
    except ValueError as error:
        raise MazeSpecError(str(error)) from error

    if len(runs) > 1:
        print(
            f"Replaying {len(runs)} runs of '{runs.title}'. "
            f"PageDown/] next run, PageUp/[ previous run, A toggles auto-advance."
        )

    visualizer = ReplayPygameVisualizer.for_runs(
        runs,
        fps=args.fps,
        scale=args.scale,
        auto_advance=not args.no_auto_advance,
    )

    try:
        visualizer.run()
    finally:
        visualizer.close()


def run_sprites(args: argparse.Namespace) -> None:
    run_sprite_preview(scale=args.scale if args.scale is not None else 6)


def create_controller(name, maze, seed=42):
    registry = create_controller_registry()
    return registry.create(name, maze, seed)


def add_scale_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--scale",
        type=positive_int,
        default=None,
        help="Pixel scale of the 8x8 tiles (whole number). Default: the window fills 85%% of the screen's height or width, at any maze size.",
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
        help="Save the result to this file (implies --save). A bare name goes into results/.",
    )
    simulate_parser.add_argument(
        "--save",
        action="store_true",
        help="Save the result, auto-named in results/ (<controller>_<maze>_<timestamp>.json). Default: not saved.",
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
        help="Save the result to this file (implies --save). A bare name goes into results/.",
    )
    play_parser.add_argument(
        "--save",
        action="store_true",
        help="Save the result, auto-named in results/ (manual_<maze>_<timestamp>.json). Default: not saved.",
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
    add_maze_argument(
        experiment_parser,
        seed_default=None,
        seed_help=(
            "Fix one recipe maze for every run. Without it, a recipe gives each run its own "
            "maze, from the run's maze seed (the same sequence for every controller)."
        ),
    )
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
    experiment_parser.add_argument(
        "--visualize",
        action="store_true",
        help="Watch every run live in one window (closing it stops the experiment).",
    )
    experiment_parser.add_argument(
        "--fps",
        type=positive_int,
        default=30,
        help="Steps per second while visualizing. Default: 30.",
    )
    add_scale_argument(experiment_parser)
    experiment_parser.set_defaults(func=run_experiment)

    # REPLAY

    replay_parser = subparsers.add_parser(
        "replay",
        help="Replay a previously saved simulation.",
    )

    replay_parser.add_argument(
        "input",
        type=str,
        help="A saved result .json, or an experiment folder to replay all its runs (both also looked up in results/).",
    )

    replay_parser.add_argument(
        "--fps",
        type=positive_int,
        default=10,
        help="Initial replay speed.",
    )

    replay_parser.add_argument(
        "--no-auto-advance",
        action="store_true",
        help="Experiment folders: stop at the end of each run instead of going on to the next (toggle with A).",
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
    add_mazes_parser(subparsers, add_scale_argument)

    args = parser.parse_args()

    try:
        args.func(args)
    except (MazeSpecError, ConfigError, GenerationError) as error:
        # Not a mistake in the arguments' syntax, so no usage text.
        parser.exit(2, f"{parser.prog}: error: {error}\n")


if __name__ == "__main__":
    main()
