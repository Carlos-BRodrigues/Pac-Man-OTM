"""The avoidance benchmark itself: its mazes and its determinism (slow)."""

import pytest

from bench_avoidance import benchmark_mazes, run_matrix, summarize

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("ghosts", [1, 2])
def test_benchmark_has_26_distinct_mazes(ghosts) -> None:
    mazes = benchmark_mazes(ghosts)

    assert len(mazes) == 26
    assert len({(maze.topography.tobytes(), maze.topography.shape) for maze in mazes.values()}) == 26
    assert all(len(maze.ghost_spawns) == ghosts for maze in mazes.values())


def test_tiny_matrix_is_deterministic() -> None:
    specs = [("classic", 0), ("organic", 3)]
    first = run_matrix(["two-opt", "two-opt-avoid"], ["easy"], [1], specs)
    second = run_matrix(["two-opt", "two-opt-avoid"], ["easy"], [1], specs)

    strip = lambda rows: [row.__dict__ | {"controller_seconds": 0} for row in rows]
    assert strip(first) == strip(second)
    assert [line["runs"] for line in summarize(first)] == [2, 2]
