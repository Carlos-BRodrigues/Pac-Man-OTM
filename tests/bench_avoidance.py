"""
The ghost-avoidance benchmark (next.md, step 0): a fixed matrix of mazes, speeds,
ghost counts and controllers, one deterministic run per cell, summarized as a
Markdown table. Run it manually:

    python tests/bench_avoidance.py
    python tests/bench_avoidance.py --speeds easy --ghosts 2 --controllers two-opt-avoid two-opt-safe
    python tests/bench_avoidance.py --save results/bench    # every run as a replayable result JSON
"""

import argparse
import math
import os
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from pacman_otm.controllers.ghosts.registry import create_ghosts
from pacman_otm.controllers.registry import create_controller_registry
from pacman_otm.mazes.maze import Maze
from pacman_otm.mazes.registry import resolve_maze
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.ghosts import CAUGHT_REASON
from pacman_otm.simulation.result import SimulationResult
from pacman_otm.simulation.runner import run_simulation
from pacman_otm.simulation.speeds import SPEED_PRESETS

FIXED_MAZES = ("classic", "cool_1_ghost_duel")
RECIPES = ("classic-like", "open-lattice", "organic")
RECIPE_SEEDS = range(8)

SPEEDS = ("easy", "equal", "arcade")
GHOSTS = (1, 2)
# Controllers that are not registered (yet) are left out of the default list.
CONTROLLERS = ("two-opt", "two-opt-avoid", "two-opt-safe")

# Caught while moving back and forth: at most this many tiles in the last ticks.
STALL_TICKS = 8
STALL_TILES = 2


def maze_specs() -> list[tuple[str, int]]:
    """(maze spec, maze seed) of the 26 benchmark mazes, in report order."""
    return [(name, 0) for name in FIXED_MAZES] + [(recipe, seed) for recipe in RECIPES for seed in RECIPE_SEEDS]


def maze_label(spec: str, seed: int) -> str:
    return spec if spec in FIXED_MAZES else f"{spec}-{seed}"


def build_maze(spec: str, seed: int, ghosts: int) -> Maze:
    # A given maze seed is never replaced: a seed that fails to build stops the benchmark.
    try:
        return resolve_maze(spec, maze_seed=seed, ghost_count=ghosts)
    except Exception as error:
        raise RuntimeError(f"Benchmark maze {maze_label(spec, seed)} failed to build: {error}") from error


def benchmark_mazes(ghosts: int) -> dict[str, Maze]:
    return {maze_label(spec, seed): build_maze(spec, seed, ghosts) for spec, seed in maze_specs()}


@dataclass(frozen=True)
class RunRow:
    speeds: str
    ghosts: int
    controller: str
    maze: str
    termination_reason: str
    completion_rate: float
    ticks: int
    tour_length: float | None
    decisions: int
    flees: int
    controller_seconds: float
    stalled: bool


def run_cell(
    controller: str,
    spec: str,
    seed: int,
    speeds: str,
    ghosts: int,
    save_dir: str | None = None,
) -> RunRow:
    maze = build_maze(spec, seed, ghosts)
    kinds = ["blinky"] * ghosts
    result = run_simulation(
        engine=SimulationEngine(maze, kinds, SPEED_PRESETS[speeds]),
        controller=create_controller_registry().create(controller, maze, 0),
        ghosts=create_ghosts(maze, kinds),
    )

    if save_dir is not None:
        path = Path(save_dir) / f"{speeds}_{ghosts}g" / controller / f"{maze_label(spec, seed)}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        result.save_json(path)

    return row_from_result(result, speeds, ghosts, controller, maze_label(spec, seed))


def row_from_result(result: SimulationResult, speeds: str, ghosts: int, controller: str, maze: str) -> RunRow:
    description = result.controller or {}
    last = result.states[-1]
    recent = {state.pacman_occupied for state in result.states[-STALL_TICKS:]}

    return RunRow(
        speeds=speeds,
        ghosts=ghosts,
        controller=controller,
        maze=maze,
        termination_reason=last.termination_reason,
        completion_rate=result.metrics.completion_rate,
        ticks=result.metrics.total_steps,
        tour_length=description.get("tour", {}).get("tour_length"),
        decisions=sum(action is not None for action in result.actions),
        flees=description.get("avoidance", {}).get("flee_count", 0),
        controller_seconds=result.metrics.controller_time_seconds,
        stalled=last.termination_reason == CAUGHT_REASON and len(recent) <= STALL_TILES,
    )


def run_matrix(
    controllers: list[str],
    speeds: list[str],
    ghosts: list[int],
    specs: list[tuple[str, int]] | None = None,
    save_dir: str | None = None,
    jobs: int = 1,
) -> list[RunRow]:
    cells = [
        (controller, spec, seed, speed, ghost, save_dir)
        for speed in speeds
        for ghost in ghosts
        for controller in controllers
        for spec, seed in (specs if specs is not None else maze_specs())
    ]

    if jobs <= 1:
        return [run_cell(*cell) for cell in cells]

    with ProcessPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(run_cell, *zip(*cells)))


def summarize(rows: list[RunRow]) -> list[dict]:
    """One line per (speeds, ghosts, controller), in the order the rows came."""

    groups: dict[tuple[str, int, str], list[RunRow]] = {}

    for row in rows:
        groups.setdefault((row.speeds, row.ghosts, row.controller), []).append(row)

    lines = []

    for (speeds, ghosts, controller), group in groups.items():
        completed = [row for row in group if row.termination_reason == "completed"]
        ratios = [row.ticks / row.tour_length for row in completed if row.tour_length]
        decisions = sum(row.decisions for row in group)

        lines.append({
            "speeds": speeds,
            "ghosts": ghosts,
            "controller": controller,
            "runs": len(group),
            "caught": sum(row.termination_reason == CAUGHT_REASON for row in group),
            "completed": len(completed),
            "max_steps": sum(row.termination_reason == "max_steps" for row in group),
            "completion": statistics.mean(row.completion_rate for row in group),
            "ticks_per_tour": statistics.mean(ratios) if ratios else math.nan,
            "flee_share": sum(row.flees for row in group) / decisions if decisions else 0.0,
            "stalled": sum(row.stalled for row in group),
            "controller_seconds": statistics.mean(row.controller_seconds for row in group),
        })

    return lines


def markdown_table(lines: list[dict]) -> str:
    header = (
        "| speeds × ghosts | controller | caught | completed | max_steps | pellets | ticks/tour | "
        "flee share | stalled | ctrl s/run |\n"
        "|---|---|---|---|---|---|---|---|---|---|"
    )
    body = [
        f"| {line['speeds']} × {line['ghosts']} | `{line['controller']}` | {line['caught']}/{line['runs']} | "
        f"{line['completed']} | {line['max_steps']} | {line['completion']:.1%} | "
        f"{'–' if math.isnan(line['ticks_per_tour']) else f'{line['ticks_per_tour']:.2f}×'} | "
        f"{line['flee_share']:.1%} | {line['stalled']} | {line['controller_seconds']:.3f} |"
        for line in lines
    ]
    return "\n".join([header, *body])


def main(argv: list[str] | None = None) -> None:
    registered = set(create_controller_registry().names())

    parser = argparse.ArgumentParser(description="The ghost-avoidance benchmark (next.md).")
    parser.add_argument("--controllers", nargs="+", default=[name for name in CONTROLLERS if name in registered])
    parser.add_argument("--speeds", nargs="+", choices=list(SPEED_PRESETS), default=list(SPEEDS))
    parser.add_argument("--ghosts", nargs="+", type=int, default=list(GHOSTS))
    parser.add_argument("--mazes", nargs="+", help="Only these maze labels, e.g. classic organic-3.")
    parser.add_argument("--save", metavar="DIR", help="Write every run's result JSON under DIR.")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    args = parser.parse_args(argv)

    specs = maze_specs()

    if args.mazes:
        specs = [(spec, seed) for spec, seed in specs if maze_label(spec, seed) in args.mazes]

    rows = run_matrix(args.controllers, args.speeds, args.ghosts, specs, args.save, args.jobs)
    print(markdown_table(summarize(rows)))


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    main()
