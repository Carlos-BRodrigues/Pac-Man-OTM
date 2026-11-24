import csv
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median, pstdev
from collections.abc import Callable
from typing import Any

from pacman_otm.mazes.analysis import analyze
from pacman_otm.mazes.maze import Maze
from pacman_otm.controllers.controller import Controller
from pacman_otm.controllers.ghosts.registry import create_ghosts, ghost_lineup
from pacman_otm.experiments.seeding import RunSeeds, derive_run_seeds
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.ghosts import CAUGHT_REASON
from pacman_otm.simulation.frame import SimulationFrame
from pacman_otm.simulation.runner import DEFAULT_MAX_STEPS, run_simulation
from pacman_otm.simulation.result import SimulationResult
from pacman_otm.statistics_.serialization import pretty_json

ControllerFactory = Callable[[Maze, int], Controller]

# (run index, maze seed) -> maze. A fixed maze ignores both, a recipe uses the seed,
# and a maze set uses the run index.
MazeFactory = Callable[[int, int], Maze]

# Called after each run with (run index, result), e.g. to print progress.
RunCallback = Callable[[int, SimulationResult], None]

# Called before each run with (run index, maze); returns that run's on_frame callback
# (e.g. a live visualizer) or None. A run ended by "visualization_closed" stops the experiment.
FrameCallback = Callable[[SimulationFrame], bool | None]
RunStartCallback = Callable[[int, Maze], FrameCallback | None]

# The termination reason run_simulation uses when on_frame asks to stop.
VISUALIZATION_CLOSED = "visualization_closed"

# Maze measurements copied into every run record (and results.csv), prefixed "maze_",
# so controller performance can be read against what each maze is like.
MAZE_METRIC_COLUMNS = (
    "walkable_tiles",
    "loops",
    "dead_ends",
    "junction_share",
    "longest_straight_run",
    "longest_corridor",
)


@dataclass
class ExperimentResults:
    name: str
    output_dir: Path
    runs: list[SimulationResult]
    seeds: list[RunSeeds]
    # True when the visualization was closed: fewer runs than requested.
    stopped_early: bool = False


class ExperimentRunner:
    """
    Runs one controller over a sequence of mazes. Run i uses the seeds
    derive_run_seeds(seed, i), so the maze sequence depends only on the
    experiment seed and is identical for every controller. Each maze brings its
    ghosts: one Blinky per ghost spawn (ghosts are deterministic, so every
    controller meets the same ghosts on the same maze).
    """

    def __init__(
        self,
        maze_factory: MazeFactory,
        controller_factory: ControllerFactory,
        controller_name: str,
        experiment_name: str,
        maze_label: str,
        output_root: str | Path = "results",
        seed: int = 42,
        max_steps: int = DEFAULT_MAX_STEPS,
        on_run: RunCallback | None = None,
        maze_info: dict[str, Any] | None = None,
        on_run_start: RunStartCallback | None = None,
    ) -> None:

        self.maze_factory = maze_factory
        self.controller_factory = controller_factory
        self.controller_name = controller_name
        self.experiment_name = experiment_name
        self.maze_label = maze_label
        self.output_root = Path(output_root)
        self.seed = seed
        self.max_steps = max_steps
        self.on_run = on_run
        # Written once under "experiment" in results.json, e.g. the recipe of per-run mazes.
        self.maze_info = dict(maze_info or {})
        self.on_run_start = on_run_start

    def _create_output_dir(self) -> Path:

        self.output_root.mkdir(parents=True, exist_ok=True)

        base_dir = self.output_root / self.experiment_name
        output_dir = base_dir
        counter = 1

        while output_dir.exists():
            output_dir = Path(f"{base_dir}_{counter:03d}")
            counter += 1

        output_dir.mkdir(parents=True)

        return output_dir

    def run(self, number_of_runs: int) -> ExperimentResults:

        if number_of_runs <= 0:
            raise ValueError("number_of_runs must be positive.")

        output_dir = self._create_output_dir()
        runs_dir = output_dir / "runs"
        runs_dir.mkdir()

        results = []
        run_seeds = []

        for run_index in range(number_of_runs):

            seeds = derive_run_seeds(self.seed, run_index)
            run_seeds.append(seeds)

            maze = self.maze_factory(run_index, seeds.maze_seed)
            ghost_kinds = ghost_lineup(maze)
            engine = SimulationEngine(maze, ghost_kinds)
            controller = self.controller_factory(maze, seeds.controller_seed)

            on_frame = (
                self.on_run_start(run_index, maze) if self.on_run_start is not None else None
            )

            result = run_simulation(
                engine=engine,
                controller=controller,
                max_steps=self.max_steps,
                on_frame=on_frame,
                ghosts=create_ghosts(maze, ghost_kinds),
            )

            run_dir = runs_dir / f"run_{run_index + 1:04d}"
            run_dir.mkdir()

            result.save_json(run_dir / "result.json")

            results.append(result)

            if self.on_run is not None:
                self.on_run(run_index, result)

            # The interrupted run is kept (its termination reason says why it ended);
            # the runs after it are not started.
            if result.metrics.termination_reason == VISUALIZATION_CLOSED:
                stopped_early = run_index + 1 < number_of_runs
                break
        else:
            stopped_early = False

        experiment_results = ExperimentResults(
            name=self.experiment_name,
            output_dir=output_dir,
            runs=results,
            seeds=run_seeds,
            stopped_early=stopped_early,
        )

        self._export_results(experiment_results)

        return experiment_results

    @staticmethod
    def _describe(values: list[float]) -> dict[str, float]:

        return {
            "mean": mean(values),
            "median": median(values),
            "standard_deviation": pstdev(values),
            "minimum": min(values),
            "maximum": max(values),
        }

    def _calculate_aggregates(
        self,
        results: list[SimulationResult],
    ) -> dict[str, Any]:

        metrics = [result.metrics.to_dict() for result in results]
        maze_metrics = [self._maze_metrics(result) for result in results]

        completed_runs = sum(1 for item in metrics if item["completed"])

        numeric_fields = [
            "total_steps",
            "collected_pellets",
            "remaining_pellets",
            "completion_rate",
            "elapsed_time_seconds",
            "controller_time_seconds",
        ]

        aggregates = {
            field: self._describe([float(item[field]) for item in metrics])
            for field in numeric_fields
        }

        aggregated = {
            "number_of_runs": len(results),
            "completed_runs": completed_runs,
            "failed_or_incomplete_runs": len(results) - completed_runs,
            "caught_runs": sum(1 for item in metrics if item["termination_reason"] == CAUGHT_REASON),
            "run_completion_rate": completed_runs / len(results),
            "metrics": aggregates,
            "maze_metrics": {
                column: self._describe([float(item[column]) for item in maze_metrics])
                for column in maze_metrics[0]
            },
        }

        tour_metrics = [self._tour_metrics(result) for result in results]

        if tour_metrics[0]:
            aggregated["tour_metrics"] = {
                column: self._describe([float(item[column]) for item in tour_metrics])
                for column in tour_metrics[0]
            }

        return aggregated

    @staticmethod
    def _maze_metrics(result: SimulationResult) -> dict[str, Any]:
        measured = analyze(result.maze).to_dict()
        return {f"maze_{column}": measured[column] for column in MAZE_METRIC_COLUMNS}

    @staticmethod
    def _tour_metrics(result: SimulationResult) -> dict[str, Any]:
        """The numbers a tour controller reports about its plan, prefixed "tour_"; else nothing."""
        tour = (result.controller or {}).get("tour") or {}
        return {
            key if key.startswith("tour_") else f"tour_{key}": value
            for key, value in tour.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }

    def _export_results(
        self,
        experiment: ExperimentResults,
    ) -> None:

        run_records = []

        for index, (result, seeds) in enumerate(zip(experiment.runs, experiment.seeds)):

            origin = result.maze.origin

            # The full maze lives in each run's result.json; here what identifies and describes it.
            # maze_seed is the seed that built the maze: the run's own for per-run mazes,
            # the fixed one for a fixed recipe maze.
            run_records.append(
                {
                    "run": index + 1,
                    "maze": result.maze.name,
                    "maze_seed": (
                        origin.seed
                        if origin is not None and origin.seed is not None
                        else seeds.maze_seed
                    ),
                    "controller_seed": seeds.controller_seed,
                    **result.metrics.to_dict(),
                    **self._maze_metrics(result),
                    **self._tour_metrics(result),
                }
            )

        data = {
            "experiment": {
                "name": experiment.name,
                "controller": self.controller_name,
                "controller_type": (experiment.runs[0].controller or {}).get("type"),
                "maze": self.maze_label,
                **self.maze_info,
                "number_of_runs": len(experiment.runs),
                "stopped_early": experiment.stopped_early,
                "seed": self.seed,
                "max_steps": self.max_steps,
            },
            "aggregates": self._calculate_aggregates(experiment.runs),
            "individual_runs": run_records,
        }

        results_path = experiment.output_dir / "results.json"

        results_path.write_text(
            pretty_json(data),
            encoding="utf-8",
        )

        self._export_csv(
            experiment.output_dir / "results.csv",
            run_records,
        )

    @staticmethod
    def _export_csv(
        filepath: Path,
        records: list[dict[str, Any]],
    ) -> None:

        with filepath.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=list(records[0].keys()),
            )

            writer.writeheader()
            writer.writerows(records)
