import pygame

from pacman_otm.simulation.frame import SimulationFrame
from pacman_otm.visualization.pygame_renderer import PygameRenderer


class LivePygameVisualizer:

    def __init__(
        self,
        renderer: PygameRenderer,
        fps: int = 10,
        ready_seconds: float = 0.0,
    ) -> None:

        if fps <= 0:
            raise ValueError("FPS must be greater than zero.")

        if ready_seconds < 0:
            raise ValueError("ready_seconds cannot be negative.")

        self.renderer = renderer
        self.fps = fps
        self.ready_seconds = ready_seconds
        self.clock = pygame.time.Clock()
        self._ready_shown = False

    def __call__(self, frame: SimulationFrame) -> bool:

        if not self.renderer.is_open:
            return False

        if not self._ready_shown:
            self._ready_shown = True

            if self.ready_seconds > 0:
                return self._show_ready(frame)

        if not self.renderer.process_events():
            return False

        self.renderer.draw(frame)

        # Limit the simulation to the requested visualization speed.
        self.clock.tick(self.fps)

        return True

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

            self.renderer.draw(frame, message="READY!")
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
