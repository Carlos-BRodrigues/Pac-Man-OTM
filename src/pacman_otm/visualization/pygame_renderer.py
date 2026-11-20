import pygame

from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.frame import SimulationFrame


class PygameRenderer:

    def __init__(
        self,
        maze: Maze,
        tile_size: int = 20,  # 20
        hud_height: int = 50,
        show_target: bool = True,
        show_planned_path: bool = True,
    ) -> None:

        pygame.init()

        self.maze = maze
        self.tile_size = tile_size
        self.hud_height = hud_height

        self.margin = 20

        self.width = maze.width * tile_size + 2 * self.margin
        self.height = maze.height * tile_size + 2 * self.margin + hud_height

        self.screen = pygame.display.set_mode((self.width, self.height))

        pygame.display.set_caption("Pac-Man OTM")

        self.font = pygame.font.Font(None, 30)
        self.small_font = pygame.font.Font(None, 22)

        # Overlay settings
        self.show_target = show_target
        self.show_planned_path = show_planned_path

        # Colors
        self.background_color = (15, 15, 25)
        self.wall_color = (35, 65, 180)
        self.corridor_color = (20, 20, 35)
        self.void_color = (0, 0, 0)
        self.pellet_color = (245, 220, 170)
        self.pacman_color = (255, 220, 0)
        self.text_color = (240, 240, 240)

        self.target_color = (11, 252, 3)
        self.path_color = (11, 252, 3)

        self.is_open = True

    def draw(self, frame: SimulationFrame) -> None:

        self.screen.fill(self.background_color)

        self._draw_maze(frame)
        self._draw_planned_path(frame)
        self._draw_pellets(frame)
        self._draw_target(frame)
        self._draw_pacman(frame)

        self._draw_hud(frame)

        pygame.display.flip()

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

                if tile == Maze.WALL:
                    color = self.wall_color
                elif tile == Maze.CORRIDOR:
                    color = self.corridor_color
                else:
                    color = self.void_color

                pygame.draw.rect(self.screen, color, rect)

    def _draw_pellets(self, frame: SimulationFrame) -> None:

        for row, col in frame.state.remaining_pellets:

            center = self._tile_center((row, col))

            pygame.draw.circle(
                self.screen,
                self.pellet_color,
                center,
                max(3, self.tile_size // 10),
            )

    def _draw_pacman(self, frame: SimulationFrame) -> None:

        center = self._tile_center(frame.state.pacman_position)

        pygame.draw.circle(
            self.screen,
            self.pacman_color,
            center,
            self.tile_size // 2 - 5,
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
            self.tile_size // 2 - 2,
            width=2,
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
            width=3,
        )

        # Draw an arrowhead pointing toward the next tile.
        start = points[0]
        end = points[1]

        direction = pygame.Vector2(end) - pygame.Vector2(start)

        if direction.length_squared() == 0:
            return

        direction = direction.normalize()

        perpendicular = pygame.Vector2(-direction.y, direction.x)

        arrow_length = self.tile_size // 3
        arrow_width = self.tile_size // 5

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
