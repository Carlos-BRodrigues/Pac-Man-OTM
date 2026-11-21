from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RunSeeds:
    maze_seed: int
    controller_seed: int


def derive_run_seeds(experiment_seed: int, run_index: int) -> RunSeeds:
    """
    Split one experiment seed into independent seeds for each run.

    The maze seed depends only on (experiment_seed, run_index), never on the
    controller, so every controller run with the same experiment seed sees the
    same sequence of mazes. SeedSequence keeps the two streams statistically
    independent, unlike seed + run_index.
    """
    if experiment_seed < 0:
        raise ValueError("The experiment seed must be non-negative.")

    if run_index < 0:
        raise ValueError("The run index must be non-negative.")

    sequence = np.random.SeedSequence(experiment_seed, spawn_key=(run_index,))
    maze_sequence, controller_sequence = sequence.spawn(2)

    return RunSeeds(
        maze_seed=int(maze_sequence.generate_state(1)[0]),
        controller_seed=int(controller_sequence.generate_state(1)[0]),
    )
