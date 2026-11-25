"""
What to draw, frame by frame, from recorded frames only: shared by the live
window, the replay window and video export, so an export shows exactly what a
window shows. No pygame, no clock: timing is the caller's (ticks per second,
in-between frames per tick).
"""

from collections.abc import Iterator
from dataclasses import dataclass

from pacman_otm.simulation.frame import SimulationFrame
from pacman_otm.simulation.replay import ReplayPlayer
from pacman_otm.simulation.result import SimulationResult
from pacman_otm.visualization.animation import (
    DEATH_FPS,
    SUBFRAMES,
    PlayerPose,
    ends_in_death,
    pacman_track,
    poses_for_states,
    step_poses,
)
from pacman_otm.visualization.sprites import DEATH_FRAMES


@dataclass(frozen=True)
class DrawStep:
    """One picture: a frame (part-way from previous_frame at `progress`), or a death frame."""

    frame: SimulationFrame
    pose: PlayerPose
    previous_frame: SimulationFrame | None = None
    progress: float = 1.0
    # Set: Pac-Man's death sequence at this index (renderer.draw_death) instead of the frame.
    death_index: int | None = None
    message: str | None = None


def tick_steps(
    previous: SimulationFrame,
    frame: SimulationFrame,
    pose: PlayerPose,
    subframes: int = SUBFRAMES,
) -> list[DrawStep]:
    """The in-between frames of one tick, 1/subframes ... 1 of the way; the last is `frame` itself."""

    poses = step_poses(pose, pacman_track(previous.state, frame.state), subframes)
    return [
        DrawStep(frame=frame, pose=step_pose, previous_frame=previous, progress=index / subframes)
        for index, step_pose in enumerate(poses, start=1)
    ]


def death_steps(frame: SimulationFrame, pose: PlayerPose, fps: int = DEATH_FPS) -> list[DrawStep]:
    """
    The death sequence at `fps` pictures per second: each death frame repeated so
    the sequence keeps DEATH_FPS timing exactly on the whole (cumulative rounding).
    """
    steps = []

    for index in range(DEATH_FRAMES):
        repeats = (index + 1) * fps // DEATH_FPS - index * fps // DEATH_FPS
        steps.extend([DrawStep(frame=frame, pose=pose, death_index=index)] * repeats)

    return steps


def replay_steps(
    result: SimulationResult,
    subframes: int = SUBFRAMES,
    fps: int | None = None,
    hold_seconds: float = 1.0,
) -> Iterator[DrawStep]:
    """
    A whole recorded run as the replay window plays it: the first frame still,
    `subframes` in-between frames per tick, the death sequence if Pac-Man was
    caught, then the last picture held (with its end banner). `fps` is the
    pictures per second the steps will be shown at (default: one tick per
    second's worth of subframes, i.e. fps = subframes), for the death and the hold.
    """
    fps = fps if fps is not None else subframes
    player = ReplayPlayer(result)
    poses = poses_for_states(result.states)

    previous = player.get_frame(0)
    last = DrawStep(frame=previous, pose=poses[0])
    yield last

    for index in range(1, player.total_frames):
        frame = player.get_frame(index)

        for step in tick_steps(previous, frame, poses[index - 1], subframes):
            last = step
            yield step

        previous = frame

    if ends_in_death(previous.state):
        for step in death_steps(previous, poses[-1], fps):
            last = step
            yield step

    for _ in range(round(hold_seconds * fps)):
        yield last
