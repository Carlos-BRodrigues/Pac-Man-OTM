import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import hashlib
import shutil

import pytest

from pacman_otm.controllers.ghosts.registry import create_ghosts
from pacman_otm.controllers.registry import create_controller_registry
from pacman_otm.mazes.registry import resolve_maze
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.runner import run_simulation
from pacman_otm.visualization import export
from pacman_otm.visualization.export import ExportError, ExportSettings, export_run, render_pictures


@pytest.fixture(scope="module")
def short_run():
    maze = resolve_maze("classic", ghost_kinds=("blinky", "pinky"))
    kinds = ("blinky", "pinky")
    return run_simulation(
        engine=SimulationEngine(maze, kinds),
        controller=create_controller_registry().create("nearest-pellet", maze, 1),
        ghosts=create_ghosts(maze, kinds),
        max_steps=12,
    )


def test_the_same_result_renders_the_same_pictures(short_run) -> None:
    settings = ExportSettings(format="mp4", subframes=2, scale=1, hold_seconds=0.2)

    def digest() -> tuple[int, str]:
        pictures = list(render_pictures(short_run, settings))
        return len(pictures), hashlib.sha256(b"".join(pictures)).hexdigest()

    count, first = digest()

    # The first still, 2 pictures per tick, then the hold.
    assert count == 1 + 2 * (len(short_run.states) - 1) + 4
    assert digest() == (count, first)


def test_a_missing_ffmpeg_is_a_clear_error(short_run, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(export.shutil, "which", lambda name: None)

    with pytest.raises(ExportError, match="ffmpeg"):
        export_run(short_run, tmp_path / "x.mp4", ExportSettings(format="mp4", scale=1))


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
@pytest.mark.parametrize("fmt", ["mp4", "gif"])
def test_export_writes_a_video(short_run, tmp_path, fmt) -> None:
    settings = ExportSettings(format=fmt, subframes=2, scale=1, hold_seconds=0.2)
    summary = export_run(short_run, tmp_path / f"run.{fmt}", settings)

    assert summary.path.exists() and summary.size_bytes > 0
    assert summary.seconds == pytest.approx(summary.pictures / 20)
