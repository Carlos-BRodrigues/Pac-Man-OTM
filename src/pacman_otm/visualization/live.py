import pygame

from pacman_otm.simulation.frame import SimulationFrame
from pacman_otm.visualization.animation import (
    DEATH_FPS,
    INITIAL_POSE,
    SUBFRAMES,
    ends_in_death,
    pacman_track,
    step_poses,
)
from pacman_otm.visualization.pygame_renderer import PygameRenderer
from pacman_otm.visualization.sprites import DEATH_FRAMES


class LivePygameVisualizer:
    """
    The runner's on_frame callback. Each new frame is shown as SUBFRAMES
    in-between frames, so the player glides between tiles at the same step rate.
    """

    def __init__(
        self,
        renderer: PygameRenderer,
        fps: int = 10,
        ready_seconds: float = 0.0,
        subframes: int = SUBFRAMES,
    ) -> None:

        if fps <= 0:
            raise ValueError("FPS must be greater than zero.")

        if ready_seconds < 0:
            raise ValueError("ready_seconds cannot be negative.")

        if subframes <= 0:
            raise ValueError("subframes must be greater than zero.")

        self.renderer = renderer
        self.fps = fps
        self.ready_seconds = ready_seconds
        self.subframes = subframes
        self.clock = pygame.time.Clock()

        self._previous_frame: SimulationFrame | None = None
        self._pose = INITIAL_POSE

    def __call__(self, frame: SimulationFrame) -> bool:

        if not self.renderer.is_open:
            return False

        if self._previous_frame is None:
            self._previous_frame = frame

            if self.ready_seconds > 0:
                return self._show_ready(frame)

            if not self.renderer.process_events():
                return False

            self.renderer.draw(frame, self._pose)
            self.clock.tick(self.fps)
            return True

        # Events are read once per step, as before the in-between frames existed.
        # In-between frames only pump the queue, so key presses stay queued for the
        # keyboard input of `play`, which reads them when the controller decides.
        if not self.renderer.process_events():
            return False

        previous = self._previous_frame
        poses = step_poses(self._pose, pacman_track(previous.state, frame.state), self.subframes)

        for index, pose in enumerate(poses, start=1):
            if index > 1:
                pygame.event.pump()

            self.renderer.draw(
                frame,
                pose,
                previous_frame=previous,
                progress=index / self.subframes,
            )
            self.clock.tick(self.fps * self.subframes)

        self._pose = poses[-1]
        self._previous_frame = frame

        if ends_in_death(frame.state):
            self._play_death(frame)

        return self.renderer.is_open

    def _play_death(self, frame: SimulationFrame) -> None:
        for index in range(DEATH_FRAMES):
            if not self.renderer.process_events():
                return

            self.renderer.draw_death(frame, index)
            self.clock.tick(DEATH_FPS)

    def _show_ready(self, frame: SimulationFrame) -> bool:
        """
        Hold the starting frame with "READY!" for a fixed time, as in the arcade.
        Purely presentational: no step is taken, so history is unaffected.
        Key presses don't shorten it; they are re-queued so a direction pressed
        during READY becomes the first turn. Esc or closing the window quits.
        """

        end_ms = pygame.time.get_ticks() + int(self.ready_seconds * 1000)
        held_keys: list[pygame.event.Event] = []

        while pygame.time.get_ticks() < end_ms:
            for event in pygame.event.get():

                if event.type != pygame.KEYDOWN:
                    # Window close (and anything else the renderer tracks)
                    self.renderer.handle_event(event)

                elif event.key == pygame.K_ESCAPE:
                    self.renderer.is_open = False

                else:
                    held_keys.append(event)

            if not self.renderer.is_open:
                return False

            self.renderer.draw(frame, self._pose, message="READY!")
            self.clock.tick(30)

        # Re-queued untouched, so their normal handler (e.g. overlay toggles) sees them once
        for event in held_keys:
            pygame.event.post(event)

        return True

    def close(self) -> None:
        self.renderer.close()

    def wait_until_closed(self) -> None:
        """Keep the final rendered frame visible until the window closes."""

        while self.renderer.is_open:
            self.renderer.process_events()
            self.clock.tick(30)
