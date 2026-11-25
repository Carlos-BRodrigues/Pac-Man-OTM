"""
Replay export: a recorded run rendered offscreen, frame by frame, and encoded
as an MP4 or GIF by the `ffmpeg` executable (raw RGB frames piped to its
stdin: no temporary frame files, no Python dependency). Reads a
SimulationResult only; draws exactly what the replay window draws (frames.py).

Timing is exact: `fps` ticks per second, `subframes` pictures per tick, so the
video runs at fps x subframes pictures per second; the ghost hem follows the
video's own clock (picture k at k / video fps seconds), so exporting the same
result twice gives identical pictures.
"""

import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from pacman_otm.simulation.result import SimulationResult
from pacman_otm.visualization.animation import ghost_frame_at
from pacman_otm.visualization.frames import replay_steps


class ExportError(RuntimeError):
    """The export cannot run (no ffmpeg, bad options) or the encoder failed."""


@dataclass(frozen=True)
class ExportSettings:
    format: str
    # Ticks per second, as the replay window's --fps.
    fps: int = 10
    # Pictures per tick; the video runs at fps * subframes.
    subframes: int = 5
    scale: int = 3
    show_target: bool = True
    show_planned_path: bool = True
    show_ghost_overlays: bool = True
    # The last picture (end banner) is held this long.
    hold_seconds: float = 1.0

    @property
    def video_fps(self) -> int:
        return self.fps * self.subframes


# Per format: (subframes, scale). GIFs are big, so fewer, smaller pictures: 10 ticks/s x 2 = 20
# pictures/s, a 5/100 s frame delay (GIF delays are in hundredths of a second).
FORMAT_DEFAULTS = frozendict({"mp4": (5, 3), "gif": (2, 2)})


@dataclass(frozen=True)
class ExportSummary:
    path: Path
    pictures: int
    seconds: float
    size_bytes: int


def find_ffmpeg() -> str:
    executable = shutil.which("ffmpeg")

    if executable is None:
        raise ExportError(
            "Video export needs the 'ffmpeg' executable on PATH, and none was found. "
            "Install it (on Windows: winget install Gyan.FFmpeg), open a new terminal and try again."
        )

    return executable


def render_pictures(result: SimulationResult, settings: ExportSettings) -> Iterator[bytes]:
    """Every picture of the video as raw RGB bytes, rendered offscreen (no window opens)."""

    # Before pygame starts its display: never open a window, even by accident.
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

    import pygame

    from pacman_otm.visualization.pygame_renderer import PygameRenderer

    renderer = PygameRenderer(
        result.maze,
        scale=settings.scale,
        show_target=settings.show_target,
        show_planned_path=settings.show_planned_path,
        show_ghost_overlays=settings.show_ghost_overlays,
        headless=True,
    )

    steps = replay_steps(
        result,
        subframes=settings.subframes,
        fps=settings.video_fps,
        hold_seconds=settings.hold_seconds,
    )

    for index, step in enumerate(steps):
        renderer.draw_step(step, ghost_frame=ghost_frame_at(index * 1000 // settings.video_fps))
        yield pygame.image.tobytes(renderer.screen, "RGB")


def picture_size(result: SimulationResult, settings: ExportSettings) -> tuple[int, int]:
    # The renderer's own arithmetic, without starting pygame: whole tiles plus the HUD.
    from pacman_otm.visualization.pygame_renderer import PygameRenderer
    from pacman_otm.visualization.theme import DEFAULT_THEME

    tile = DEFAULT_THEME.tile * settings.scale
    width = max(PygameRenderer.MIN_WINDOW_WIDTH, result.maze.width * tile)
    height = DEFAULT_THEME.hud_height * settings.scale + result.maze.height * tile
    return width, height


def export_run(
    result: SimulationResult,
    path: Path,
    settings: ExportSettings,
    on_progress=None,
) -> ExportSummary:
    """Write one run as a video at `path`; on_progress(pictures_done) is called now and then."""

    if settings.format not in FORMAT_DEFAULTS:
        raise ExportError(f"Unknown export format '{settings.format}'; use {', '.join(FORMAT_DEFAULTS)}.")

    ffmpeg = find_ffmpeg()
    path.parent.mkdir(parents=True, exist_ok=True)
    size = picture_size(result, settings)

    if settings.format == "gif":
        with tempfile.TemporaryDirectory() as folder:
            palette = Path(folder) / "palette.png"
            # Pass 1: a palette from a sample of the pictures (every colour appears often).
            _encode(
                ffmpeg,
                _sample(render_pictures(result, settings), every=10),
                size,
                settings.video_fps,
                ["-vf", "palettegen=max_colors=256:stats_mode=full", "-update", "1", str(palette)],
            )
            pictures = _encode(
                ffmpeg,
                render_pictures(result, settings),
                size,
                settings.video_fps,
                ["-i", str(palette), "-lavfi", "[0:v][1:v]paletteuse=dither=none", "-loop", "0", str(path)],
                on_progress,
            )
    else:
        pictures = _encode(
            ffmpeg,
            render_pictures(result, settings),
            size,
            settings.video_fps,
            [
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "18",
                "-tune", "animation",
                "-pix_fmt", "yuv420p",
                # H.264 needs even sizes (they always are: tiles are 8 px times the scale).
                "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                "-movflags", "+faststart",
                str(path),
            ],
            on_progress,
        )

    return ExportSummary(
        path=path,
        pictures=pictures,
        seconds=pictures / settings.video_fps,
        size_bytes=path.stat().st_size,
    )


def _sample(pictures: Iterator[bytes], every: int) -> Iterator[bytes]:
    for index, picture in enumerate(pictures):
        if index % every == 0:
            yield picture


def _encode(
    ffmpeg: str,
    pictures: Iterator[bytes],
    size: tuple[int, int],
    fps: int,
    output_args: list[str],
    on_progress=None,
) -> int:
    """Pipe raw RGB pictures into ffmpeg; the number of pictures written."""

    width, height = size
    command = [
        ffmpeg,
        "-y",
        "-loglevel", "error",
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", f"{width}x{height}",
        "-r", str(fps),
        "-i", "-",
        *output_args,
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    count = 0

    try:
        for picture in pictures:
            process.stdin.write(picture)
            count += 1

            if on_progress is not None and count % 500 == 0:
                on_progress(count)
    except BrokenPipeError:
        pass
    finally:
        process.stdin.close()

    error = process.stderr.read().decode("utf-8", errors="replace").strip()
    process.wait()

    if process.returncode != 0:
        raise ExportError(f"ffmpeg failed (exit code {process.returncode}): {error or 'no message'}")

    return count
