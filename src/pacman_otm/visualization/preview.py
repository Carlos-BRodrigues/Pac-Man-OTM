"""'mazes preview': show one maze, with chosen tiles (rule violations) highlighted."""

from collections.abc import Iterable

import pygame

from pacman_otm.mazes.maze import Maze
from pacman_otm.visualization.pygame_renderer import PygameRenderer

Position = tuple[int, int]


def run_maze_preview(
    maze: Maze,
    highlights: Iterable[Position],
    status: str,
    scale: int | None = None,
) -> None:
    """Open a window until it is closed (or Esc). Draws data only."""

    renderer = PygameRenderer(maze, scale=scale)
    clock = pygame.time.Clock()
    highlights = list(highlights)

    try:
        while renderer.is_open:
            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    renderer.is_open = False
                else:
                    renderer.handle_event(event)

            if renderer.is_open:
                renderer.draw_preview(highlights, status)
                clock.tick(30)
    finally:
        renderer.close()
