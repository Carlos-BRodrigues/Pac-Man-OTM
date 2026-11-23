"""
Watching an experiment: every run shown live in one window, with a fresh maze
per run when the experiment generates them. Draws frames only.
"""

import pygame

from pacman_otm.mazes.maze import Maze
from pacman_otm.visualization.live import LivePygameVisualizer
from pacman_otm.visualization.pygame_renderer import PygameRenderer


class ExperimentVisualizer:
    """
    ExperimentRunner's on_run_start callback: returns a live visualizer for
    each run. Closing the window (or Esc) ends the current run as
    "visualization_closed", which stops the experiment.
    """

    def __init__(
        self,
        total_runs: int,
        scale: int | None = None,
        fps: int = 30,
        pause_seconds: float = 0.8,
    ) -> None:
        if pause_seconds < 0:
            raise ValueError("pause_seconds cannot be negative.")

        self.total_runs = total_runs
        self.scale = scale
        self.fps = fps
        self.pause_seconds = pause_seconds
        self.current: LivePygameVisualizer | None = None
        self.clock = pygame.time.Clock()

    def __call__(self, run_index: int, maze: Maze) -> LivePygameVisualizer:
        if self.current is not None:
            # Let the end of the previous run be seen before the next maze appears.
            self._hold(self.pause_seconds)

        # A new renderer per run: the maze, and so the window size, may change.
        renderer = PygameRenderer(maze, scale=self.scale)
        renderer.caption = f"Pac-Man OTM | {maze.name} | run {run_index + 1}/{self.total_runs}"
        pygame.display.set_caption(renderer.caption)

        if self.current is not None and not self.current.renderer.is_open:
            # Closed during the pause: the new run ends at its first frame.
            renderer.is_open = False

        self.current = LivePygameVisualizer(renderer, fps=self.fps)
        return self.current

    def _hold(self, seconds: float) -> None:
        renderer = self.current.renderer
        end = pygame.time.get_ticks() + round(seconds * 1000)

        while renderer.is_open and pygame.time.get_ticks() < end:
            renderer.process_events()
            self.clock.tick(30)

    def wait_until_closed(self) -> None:
        """Keep the last run on screen until the window is closed."""
        if self.current is not None and self.current.renderer.is_open:
            self.current.wait_until_closed()

    def close(self) -> None:
        if self.current is not None:
            self.current.close()
