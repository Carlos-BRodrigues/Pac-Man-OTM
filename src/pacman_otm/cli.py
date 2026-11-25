import argparse
from datetime import datetime
from pathlib import Path

from pacman_otm.cli_types import non_negative_int, positive_int
from pacman_otm.maze_commands import (
    add_maze_argument,
    add_mazes_parser,
    experiment_mazes,
    ghost_kinds_from_args,
    load_maze,
    maze_label,
)
from pacman_otm.algorithms.tours.held_karp import TourTooLargeError
from pacman_otm.mazes.analysis import analyze
from pacman_otm.mazes.config import ConfigError
from pacman_otm.mazes.generation.errors import GenerationError
from pacman_otm.mazes.registry import MazeSpecError
from pacman_otm.controllers.ghosts.ghost import GhostController
from pacman_otm.controllers.ghosts.registry import create_ghosts, ghost_lineup
from pacman_otm.controllers.manual.manual import ManualController
from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.ghosts import CAUGHT_REASON
from pacman_otm.simulation.speeds import DEFAULT_SPEEDS, SPEED_PRESETS, SpeedRules
from pacman_otm.simulation.runner import DEFAULT_MAX_STEPS, run_simulation
from pacman_otm.experiments.runner import ExperimentRunner

from pacman_otm.controllers.registry import DEFAULT_CONTROLLER, create_controller_registry


from pacman_otm.simulation.result import SimulationResult
from pacman_otm.simulation.replay import ResultSequence
from pacman_otm.visualization.pygame_renderer import PygameRenderer
from pacman_otm.visualization.experiment import ExperimentVisualizer
from pacman_otm.visualization.live import LivePygameVisualizer
from pacman_otm.visualization.replay import ReplayPygameVisualizer
from pacman_otm.visualization.keyboard import PygameKeyboardInput
from pacman_otm.visualization.sprite_preview import run_sprite_preview
from pacman_otm.visualization.export import FORMAT_DEFAULTS, ExportError, ExportSettings, export_run

RESULTS_DIR = Path("results")

# experiment --runs without a maze set (a set defaults to one run per maze).
DEFAULT_EXPERIMENT_RUNS = 10


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


def describe_tour(tour: dict | None) -> str:
    """One line about a tour controller's plan, e.g. its gap to the lower bound."""

    if not tour:
        return ""

    text = f"Tour: {tour['pellets']} pellets, length {tour['tour_length']:g}"

    if "lower_bound" in tour:
        text += (
            f", lower bound {tour['lower_bound']:g}"
            f" (at most {tour['gap_percent']:.1f}% above optimal)"
        )

    if "nn_length" in tour:
        text += (
            f"; 2-opt improved nearest neighbour ({tour['nn_length']:g}) "
            f"by {tour['improvement_percent']:.1f}%"
        )

    return text


def create_engine_and_ghosts(maze: Maze, speeds: SpeedRules) -> tuple[SimulationEngine, list[GhostController]]:
    """The maze's ghosts (one per spawn, kinds from ghost_lineup): an engine that places them and their controllers."""
    kinds = ghost_lineup(maze)
    return SimulationEngine(maze, kinds, speeds), create_ghosts(maze, kinds)


def add_speeds_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--speeds",
        choices=list(SPEED_PRESETS),
        default=DEFAULT_SPEEDS,
        help=(
            "Movement speeds. easy: ghosts at 15/16 of Pac-Man, no pellet slowdown. "
            "arcade: ghosts at 15/16 of Pac-Man, and every pellet Pac-Man eats slows him "
            "(a corridor of dots at 16/18). equal: everyone one tile per tick, no pellet slowdown. "
            f"Default: {DEFAULT_SPEEDS}."
        ),
    )


def run_simulate(args: argparse.Namespace) -> None:
    source, maze, maze_seed = load_maze(args.maze, args)
    engine, ghosts = create_engine_and_ghosts(maze, SPEED_PRESETS[args.speeds])
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
            ghosts=ghosts,
        )

        if visualizer is not None and visualizer.renderer.is_open:
            visualizer.wait_until_closed()

    finally:
        if visualizer is not None:
            visualizer.close()

    print(result.metrics)

    tour_text = describe_tour((result.controller or {}).get("tour"))

    if tour_text:
        print(tour_text)

    if args.show_history:
        for entry in result.history_summary():
            print(entry)

    save_result(result, args, label=f"{args.controller}_{maze_label(source, maze, maze_seed)}")


def run_play(args: argparse.Namespace) -> None:
    source, maze, maze_seed = load_maze(args.maze, args)
    engine, ghosts = create_engine_and_ghosts(maze, SPEED_PRESETS[args.speeds])

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
            ghosts=ghosts,
        )

        if renderer.is_open:
            visualizer.wait_until_closed()

    finally:
        visualizer.close()

    print(result.metrics)
    save_result(result, args, label=f"manual_{maze_label(source, maze, maze_seed)}")


def run_experiment(args: argparse.Namespace) -> None:
    mazes = experiment_mazes(args.maze, args.maze_set, args.maze_seed, ghost_kinds_from_args(args))
    name = args.name or f"{args.controller}_{mazes.label}"

    if args.runs is None:
        args.runs = mazes.set_size if mazes.set_size is not None else DEFAULT_EXPERIMENT_RUNS

    if mazes.set_size is not None:
        per_run = f" (a set of {mazes.set_size} mazes, run i plays maze i)"
    else:
        per_run = " (a new maze per run)" if mazes.per_run else ""

    print(
        f"Experiment '{name}': controller={args.controller}  maze={mazes.label}"
        f"{per_run}  runs={args.runs}  seed={args.seed}  speeds={args.speeds}"
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

        tour = (result.controller or {}).get("tour") or {}

        if "gap_percent" in tour:
            maze_text += f"  gap<={tour['gap_percent']:.1f}%"

        if mazes.set_size is not None:
            maze_text += f"  maze={result.maze.name}"
        elif mazes.per_run:
            maze_metrics = analyze(result.maze)
            maze_text += (
                f"  maze seed={result.maze.origin.seed} walkable={maze_metrics.walkable_tiles} "
                f"loops={maze_metrics.loops}"
            )

        print(
            f"  run {run_index + 1:>{width}}/{args.runs}  "
            f"ticks={metrics.total_steps:>5}  moves={metrics.pacman_moves:>5}  "
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
        speeds=SPEED_PRESETS[args.speeds],
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

    if any(run.metrics.ghosts for run in results.runs):
        caught = sum(1 for run in results.runs if run.metrics.termination_reason == CAUGHT_REASON)
        print(f"Caught by a ghost: {caught}/{len(results.runs)}")
    print(f"Mean ticks: {mean_steps:.1f}")
    print(f"Output directory: {results.output_dir}")


def run_replay(args: argparse.Namespace) -> None:
    input_path = Path(args.input)

    if not input_path.exists() and (RESULTS_DIR / input_path).exists():
        input_path = RESULTS_DIR / input_path

    try:
        runs = ResultSequence.from_path(input_path)
    except ValueError as error:
        raise MazeSpecError(str(error)) from error

    if args.export is not None or args.output is not None:
        export_replay(args, input_path, runs)
        return

    if args.run:
        raise MazeSpecError("--run selects runs to export; add --export mp4 or --export gif.")

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


OVERLAY_LETTERS = frozendict({"T": "show_target", "P": "show_planned_path", "G": "show_ghost_overlays"})


def export_replay(args: argparse.Namespace, input_path: Path, runs: ResultSequence) -> None:
    """
    Write videos instead of opening a window: every run of an experiment folder (or
    the --run ones) into EXP/videos/run_NNNN.<format>, a single result file next
    to itself. --output is a file for one run or a folder for several.
    """
    output = Path(args.output) if args.output is not None else None
    fmt = args.export or (output.suffix.lstrip(".").lower() if output is not None else None)

    if fmt not in FORMAT_DEFAULTS:
        raise MazeSpecError(f"Choose the video format with --export ({', '.join(FORMAT_DEFAULTS)}).")

    selected = sorted(set(args.run)) if args.run else list(range(1, len(runs) + 1))
    invalid = [number for number in selected if not 1 <= number <= len(runs)]

    if invalid:
        raise MazeSpecError(f"--run {invalid[0]}: '{runs.title}' has runs 1 to {len(runs)}.")

    overlays = (
        set()
        if args.no_overlays
        else {letter.strip().upper() for letter in args.overlays.split(",") if letter.strip()}
        if args.overlays is not None
        else set(OVERLAY_LETTERS)
    )

    if overlays - set(OVERLAY_LETTERS):
        raise MazeSpecError(f"--overlays takes letters from {','.join(OVERLAY_LETTERS)}, e.g. --overlays T,G.")

    subframes, scale = FORMAT_DEFAULTS[fmt]
    settings = ExportSettings(
        format=fmt,
        fps=args.fps,
        subframes=args.subframes if args.subframes is not None else subframes,
        scale=args.scale if args.scale is not None else scale,
        **{field: letter in overlays for letter, field in OVERLAY_LETTERS.items()},
    )

    if fmt == "gif" and 100 % settings.video_fps:
        print(
            f"Note: {settings.video_fps} pictures/s is not a whole number of GIF hundredths; "
            f"timing will be approximate (e.g. --fps 10 with --subframes 2 or 5)."
        )

    for number in selected:
        path = _export_path(input_path, runs, number, fmt, output, single=len(selected) == 1)

        try:
            result = runs.load(number - 1)
        except ValueError as error:
            raise MazeSpecError(f"{runs.paths[number - 1]}: {error}") from error

        print(f"Exporting {runs.label(number - 1)} to {path} ({settings.video_fps} pictures/s, scale {settings.scale}) ...")

        try:
            summary = export_run(
                result,
                path,
                settings,
                on_progress=lambda count: print(f"  {count} pictures", end="\r", flush=True),
            )
        except ExportError as error:
            raise MazeSpecError(str(error)) from error

        print(
            f"\r  {summary.path}: {summary.pictures} pictures, {summary.seconds:.1f} s, "
            f"{summary.size_bytes / 1_000_000:.1f} MB"
        )


def _export_path(
    input_path: Path,
    runs: ResultSequence,
    number: int,
    fmt: str,
    output: Path | None,
    single: bool,
) -> Path:
    result_path = runs.paths[number - 1]
    folder_input = input_path.is_dir()
    name = f"{result_path.parent.name}.{fmt}" if folder_input else f"{result_path.stem}.{fmt}"

    if output is None:
        return (input_path / "videos" / name) if folder_input else result_path.with_suffix(f".{fmt}")

    if single and output.suffix:
        return output

    return output / name


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
        default=DEFAULT_MAX_STEPS,
        help=f"Stop a run after this many ticks. Default: {DEFAULT_MAX_STEPS}.",
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
        default=DEFAULT_CONTROLLER,
    )

    simulate_parser.add_argument(
        "--visualize",
        action="store_true",
        help="Show the simulation live in Pygame.",
    )

    add_speeds_argument(simulate_parser)
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
        default=DEFAULT_MAX_STEPS,
        help=f"Stop a run after this many ticks. Default: {DEFAULT_MAX_STEPS}.",
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
    add_speeds_argument(play_parser)
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
        allow_sets=True,
        seed_default=None,
        seed_help=(
            "Fix one recipe maze for every run. Without it, a recipe gives each run its own "
            "maze, from the run's maze seed (the same sequence for every controller)."
        ),
    )
    experiment_parser.add_argument(
        "--runs",
        type=positive_int,
        default=None,
        help=(
            f"Number of runs. Default: the number of mazes for a maze set, "
            f"{DEFAULT_EXPERIMENT_RUNS} otherwise."
        ),
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
        default=DEFAULT_MAX_STEPS,
        help=f"Stop a run after this many ticks. Default: {DEFAULT_MAX_STEPS}.",
    )
    experiment_parser.add_argument(
        "--controller",
        choices=create_controller_registry().names(),
        default=DEFAULT_CONTROLLER,
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
    add_speeds_argument(experiment_parser)
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
        help="Replay speed in ticks per second (the window's starting speed, and an export's). Default: 10.",
    )
    replay_parser.add_argument(
        "--export",
        choices=list(FORMAT_DEFAULTS),
        default=None,
        help=(
            "Write a video of each run instead of opening a window (needs ffmpeg on PATH). "
            "An experiment folder gives EXP/videos/run_NNNN.<format>; a result file x.json gives x.<format>."
        ),
    )
    replay_parser.add_argument(
        "--output",
        default=None,
        metavar="PATH",
        help="Export: the video file (one run) or the folder for the videos (several runs).",
    )
    replay_parser.add_argument(
        "--run",
        type=positive_int,
        action="append",
        default=[],
        metavar="N",
        help="Export only run N of an experiment folder (1-based). Repeatable. Default: every run.",
    )
    replay_parser.add_argument(
        "--subframes",
        type=positive_int,
        default=None,
        metavar="N",
        help="Export: pictures per tick (video rate = fps x subframes). Default: 5 for mp4, 2 for gif.",
    )
    replay_parser.add_argument(
        "--overlays",
        default=None,
        metavar="T,P,G",
        help="Export: the overlays to draw (T target, P path, G ghosts). Default: all, as the window starts.",
    )
    replay_parser.add_argument(
        "--no-overlays",
        action="store_true",
        help="Export: no overlays.",
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
    except (MazeSpecError, ConfigError, GenerationError, TourTooLargeError) as error:
        # Not a mistake in the arguments' syntax, so no usage text.
        parser.exit(2, f"{parser.prog}: error: {error}\n")


if __name__ == "__main__":
    main()
