import argparse
from datetime import datetime
from pathlib import Path

from pacman_otm.cli_types import non_negative_int, positive_int
from pacman_otm.maze_commands import (
    add_maze_argument,
    add_mazes_parser,
    load_maze,
    maze_label,
)
from pacman_otm.mazes.config import ConfigError
from pacman_otm.mazes.generation.errors import GenerationError
from pacman_otm.mazes.registry import MazeSpecError
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
    source, maze = load_maze(args.maze, args)
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

    save_result(result, args, label=f"{args.controller}_{maze_label(source, maze, args.maze_seed)}")


def run_play(args: argparse.Namespace) -> None:
    source, maze = load_maze(args.maze, args)
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
    save_result(result, args, label=f"manual_{maze_label(source, maze, args.maze_seed)}")


def run_experiment(args: argparse.Namespace) -> None:
    # One fixed maze for every run (a recipe maze from --maze-seed); per-run mazes come in step 8.
    source, maze = load_maze(args.maze, args)
    label = maze_label(source, maze, args.maze_seed)
    name = args.name or f"{args.controller}_{label}"

    print(
        f"Experiment '{name}': controller={args.controller}  maze={label}  "
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
        maze_label=label,
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


def create_controller(name, maze, seed=42):
    registry = create_controller_registry()
    return registry.create(name, maze, seed)


def add_scale_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--scale",
        type=positive_int,
        default=None,
        help="Pixel scale of the 8x8 tiles (whole number). Default: the largest that fits the screen.",
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
    add_mazes_parser(subparsers, add_scale_argument)

    args = parser.parse_args()

    try:
        args.func(args)
    except (MazeSpecError, ConfigError, GenerationError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
