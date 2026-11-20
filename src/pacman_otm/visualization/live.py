import pygame

from pacman_otm.simulation.frame import SimulationFrame
from pacman_otm.visualization.pygame_renderer import PygameRenderer


class LivePygameVisualizer:

    def __init__(
        self,
        renderer: PygameRenderer,
        fps: int = 8,
    ) -> None:

        if fps <= 0:
            raise ValueError("FPS must be greater than zero.")

        self.renderer = renderer
        self.fps = fps
        self.clock = pygame.time.Clock()

    def __call__(self, frame: SimulationFrame) -> bool:

        if not self.renderer.is_open:
            return False

        if not self.renderer.process_events():
            return False

        self.renderer.draw(frame)

        # Limit the simulation to the requested visualization speed.
        self.clock.tick(self.fps)

        return True

    def close(self) -> None:
        self.renderer.close()

    def wait_until_closed(self) -> None:
        """Keep the final rendered frame visible until the window closes."""

        while self.renderer.is_open:
            self.renderer.process_events()
            self.clock.tick(30)
