import csv
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median, pstdev
from collections.abc import Callable
from typing import Any

from pacman_otm.mazes.maze import Maze
from pacman_otm.controllers.controller import Controller
from pacman_otm.experiments.seeding import RunSeeds, derive_run_seeds
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.runner import run_simulation
from pacman_otm.simulation.result import SimulationResult
from pacman_otm.statistics_.serialization import pretty_json

ControllerFactory = Callable[[Maze, int], Controller]

# maze seed -> maze. A fixed maze ignores the seed; a generator will use it.
MazeFactory = Callable[[int], Maze]

# Called after each run with (run index, result), e.g. to print progress.
RunCallback = Callable[[int, SimulationResult], None]


@dataclass
class ExperimentResults:
    name: str
    output_dir: Path
    runs: list[SimulationResult]
    seeds: list[RunSeeds]


class ExperimentRunner:
    """
    Runs one controller over a sequence of mazes. Run i uses the seeds
    derive_run_seeds(seed, i), so the maze sequence depends only on the
    experiment seed and is identical for every controller.
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
        max_steps: int = 1000,
        on_run: RunCallback | None = None,
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

            maze = self.maze_factory(seeds.maze_seed)
            engine = SimulationEngine(maze)
            controller = self.controller_factory(maze, seeds.controller_seed)

            result = run_simulation(
                engine=engine,
                controller=controller,
                max_steps=self.max_steps,
            )

            run_dir = runs_dir / f"run_{run_index + 1:04d}"
            run_dir.mkdir()

            result.save_json(run_dir / "result.json")

            results.append(result)

            if self.on_run is not None:
                self.on_run(run_index, result)

        experiment_results = ExperimentResults(
            name=self.experiment_name,
            output_dir=output_dir,
            runs=results,
            seeds=run_seeds,
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

        return {
            "number_of_runs": len(results),
            "completed_runs": completed_runs,
            "failed_or_incomplete_runs": len(results) - completed_runs,
            "run_completion_rate": completed_runs / len(results),
            "metrics": aggregates,
        }

    def _export_results(
        self,
        experiment: ExperimentResults,
    ) -> None:

        run_records = []

        for index, (result, seeds) in enumerate(zip(experiment.runs, experiment.seeds)):

            # The full maze lives in each run's result.json; here only what identifies it.
            run_records.append(
                {
                    "run": index + 1,
                    "maze": result.maze.name if result.maze is not None else None,
                    "maze_seed": seeds.maze_seed,
                    "controller_seed": seeds.controller_seed,
                    **result.metrics.to_dict(),
                }
            )

        data = {
            "experiment": {
                "name": experiment.name,
                "controller": self.controller_name,
                "controller_type": (experiment.runs[0].controller or {}).get("type"),
                "maze": self.maze_label,
                "number_of_runs": len(experiment.runs),
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
