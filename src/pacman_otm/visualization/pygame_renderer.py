import pygame

from pacman_otm.mazes.maze import Maze
from pacman_otm.mazes.tiles import Tile
from pacman_otm.simulation.frame import SimulationFrame


class PygameRenderer:

    MAX_TILE_SIZE = 20
    MIN_TILE_SIZE = 4
    # Share of the desktop the window may use, leaving room for the title bar and taskbar.
    SCREEN_FRACTION = 0.9

    def __init__(
        self,
        maze: Maze,
        tile_size: int | None = None,
        hud_height: int = 50,
        show_target: bool = True,
        show_planned_path: bool = True,
    ) -> None:

        pygame.init()

        self.maze = maze
        self.hud_height = hud_height

        self.margin = 20

        # None: the largest tile size that keeps the whole maze on screen.
        self.tile_size = tile_size if tile_size is not None else self._fit_tile_size()
        tile_size = self.tile_size

        self.width = maze.width * tile_size + 2 * self.margin
        self.height = maze.height * tile_size + 2 * self.margin + hud_height

        self.screen = pygame.display.set_mode((self.width, self.height))

        self.caption = f"Pac-Man OTM | {maze.name}"
        pygame.display.set_caption(self.caption)

        self.font = pygame.font.Font(None, 30)
        self.small_font = pygame.font.Font(None, 22)

        # Overlay settings
        self.show_target = show_target
        self.show_planned_path = show_planned_path

        # Colors
        self.background_color = (15, 15, 25)
        self.gate_color = (255, 170, 220)

        # Every tile needs an entry: an unknown tile is an error, not silently void.
        self.tile_colors: dict[Tile, tuple[int, int, int]] = {
            Tile.CORRIDOR: (20, 20, 35),
            Tile.WALL: (35, 65, 180),
            Tile.VOID: self.background_color,
            Tile.GHOST_HOUSE: (45, 25, 55),
            # The gate tile is drawn as a ghost-house fill with a bar across it.
            Tile.GHOST_GATE: (45, 25, 55),
        }
        self.pellet_color = (245, 220, 170)
        self.pacman_color = (255, 220, 0)
        self.text_color = (240, 240, 240)

        self.target_color = (11, 252, 3)
        self.path_color = (11, 252, 3)

        self.is_open = True

    def _fit_tile_size(self) -> int:
        desktop_sizes = pygame.display.get_desktop_sizes()
        screen_width, screen_height = desktop_sizes[0] if desktop_sizes else (1280, 800)

        available_width = screen_width * self.SCREEN_FRACTION - 2 * self.margin
        available_height = (
            screen_height * self.SCREEN_FRACTION - 2 * self.margin - self.hud_height
        )

        fit = int(min(
            available_width // self.maze.width,
            available_height // self.maze.height,
        ))

        return max(self.MIN_TILE_SIZE, min(self.MAX_TILE_SIZE, fit))

    def _scaled(self, fraction: float, minimum: int = 1) -> int:
        """A size proportional to the tile, never below `minimum` on tiny tiles."""
        return max(minimum, round(self.tile_size * fraction))

    def draw(self, frame: SimulationFrame, message: str | None = None) -> None:

        self.screen.fill(self.background_color)

        self._draw_maze(frame)
        self._draw_planned_path(frame)
        self._draw_pellets(frame)
        self._draw_target(frame)
        self._draw_pacman(frame)

        self._draw_hud(frame)

        if message is not None:
            self._draw_message(message)

        pygame.display.flip()

    def _draw_message(self, message: str) -> None:
        """Draw a banner (e.g. "READY!") centred over the maze."""

        text = self.font.render(message, True, self.pacman_color)

        maze_center = (
            self.margin + self.maze.width * self.tile_size // 2,
            self.margin + self.hud_height + self.maze.height * self.tile_size // 2,
        )

        self.screen.blit(text, text.get_rect(center=maze_center))

    def _draw_maze(self, frame: SimulationFrame) -> None:

        for row in range(self.maze.height):
            for col in range(self.maze.width):

                tile = self.maze.topography[row, col]

                rect = pygame.Rect(
                    self.margin + col * self.tile_size,
                    self.margin + self.hud_height + row * self.tile_size,
                    self.tile_size,
                    self.tile_size,
                )

                try:
                    color = self.tile_colors[Tile(tile)]
                except (ValueError, KeyError):
                    raise ValueError(
                        f"No colour for tile {tile} at {(row, col)}."
                    ) from None

                pygame.draw.rect(self.screen, color, rect)

                if tile == Tile.GHOST_GATE:
                    bar = rect.inflate(0, -rect.height * 2 // 3)
                    pygame.draw.rect(self.screen, self.gate_color, bar)

    def _draw_pellets(self, frame: SimulationFrame) -> None:

        for row, col in frame.state.remaining_pellets:

            center = self._tile_center((row, col))

            pygame.draw.circle(
                self.screen,
                self.pellet_color,
                center,
                self._scaled(0.15),
            )

    def _draw_pacman(self, frame: SimulationFrame) -> None:

        center = self._tile_center(frame.state.pacman_position)

        pygame.draw.circle(
            self.screen,
            self.pacman_color,
            center,
            self._scaled(0.25, minimum=2),
        )

    def _draw_target(self, frame: SimulationFrame) -> None:

        if not self.show_target or frame.status is None:
            return

        target = frame.status.target

        if target is None or target == frame.state.pacman_position:
            return

        center = self._tile_center(target)

        pygame.draw.circle(
            self.screen,
            self.target_color,
            center,
            max(2, self.tile_size // 2 - 2),
            width=self._scaled(0.1),
        )

    def _draw_planned_path(self, frame: SimulationFrame) -> None:

        if not self.show_planned_path or frame.status is None:
            return

        if frame.status.target == frame.state.pacman_position:
            return

        path = frame.status.planned_path
        path_index = frame.status.path_index

        if not path:
            return

        # Keep only the path ahead of Pac-Man.
        remaining_path = path[path_index:]

        if len(remaining_path) < 2:
            return

        points = [self._tile_center(position) for position in remaining_path]

        # Draw the remaining path.
        pygame.draw.lines(
            self.screen,
            self.path_color,
            False,
            points,
            width=self._scaled(0.15),
        )

        # Draw an arrowhead pointing toward the next tile.
        start = points[0]
        end = points[1]

        direction = pygame.Vector2(end) - pygame.Vector2(start)

        if direction.length_squared() == 0:
            return

        direction = direction.normalize()

        perpendicular = pygame.Vector2(-direction.y, direction.x)

        arrow_length = max(2, self.tile_size // 3)
        arrow_width = max(1, self.tile_size // 5)

        tip = pygame.Vector2(end)

        left = tip - direction * arrow_length + perpendicular * arrow_width

        right = tip - direction * arrow_length - perpendicular * arrow_width

        pygame.draw.polygon(
            self.screen,
            self.path_color,
            [tip, left, right],
        )

    def _draw_hud(self, frame: SimulationFrame) -> None:

        step_text = self.font.render(
            f"Step: {frame.state.steps}",
            True,
            self.text_color,
        )

        self.screen.blit(
            step_text,
            (self.margin, 10),
        )

        target_label = "Target: ON" if self.show_target else "Target: OFF"
        path_label = "Path: ON" if self.show_planned_path else "Path: OFF"

        overlay_text = self.small_font.render(
            f"T: {target_label}    P: {path_label}",
            True,
            self.text_color,
        )

        self.screen.blit(
            overlay_text,
            (self.margin + 150, 15),
        )

    def _tile_center(
        self,
        position: tuple[int, int],
    ) -> tuple[int, int]:

        row, col = position

        x = self.margin + col * self.tile_size + self.tile_size // 2

        y = self.margin + self.hud_height + row * self.tile_size + self.tile_size // 2

        return x, y

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.is_open = False

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_t:
                self.show_target = not self.show_target

            elif event.key == pygame.K_p:
                self.show_planned_path = not self.show_planned_path

    def process_events(self) -> bool:
        for event in pygame.event.get():
            self.handle_event(event)

        return self.is_open

    def close(self) -> None:

        pygame.quit()
        self.is_open = False
