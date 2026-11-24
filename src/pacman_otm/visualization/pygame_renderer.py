import pygame

from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.frame import SimulationFrame
from pacman_otm.visualization.animation import INITIAL_POSE, PlayerPose, move_direction
from pacman_otm.visualization.maze_art import render_maze
from pacman_otm.visualization.sprites import SpriteSet
from pacman_otm.visualization.theme import DEFAULT_THEME, Theme

Position = tuple[int, int]


class PygameRenderer:
    """
    Draws SimulationFrames on a pixel grid: 8x8 base-pixel tiles scaled up by a
    whole number. The maze background is rendered once; each frame adds pellets,
    overlays and the player sprite. Draws only; no game rules.
    """

    MAX_SCALE = 6
    # Share of the desktop the window may use, leaving room for the title bar and taskbar.
    SCREEN_FRACTION = 0.9
    MIN_WINDOW_WIDTH = 200

    def __init__(
        self,
        maze: Maze,
        scale: int | None = None,
        theme: Theme = DEFAULT_THEME,
        show_target: bool = True,
        show_planned_path: bool = True,
    ) -> None:

        pygame.init()

        self.maze = maze
        self.theme = theme

        # None: the largest whole-number scale that keeps the window on screen.
        self.scale = scale if scale is not None else self._fit_scale()

        if self.scale < 1:
            raise ValueError("The scale must be at least 1.")

        self.tile_px = theme.tile * self.scale
        self.hud_px = theme.hud_height * self.scale

        self.width = max(self.MIN_WINDOW_WIDTH, maze.width * self.tile_px)
        self.height = self.hud_px + maze.height * self.tile_px
        # Narrow mazes are centred in a window kept wide enough for the HUD.
        self.maze_x = (self.width - maze.width * self.tile_px) // 2

        self.screen = pygame.display.set_mode((self.width, self.height))

        self.caption = f"Pac-Man OTM | {maze.name}"
        pygame.display.set_caption(self.caption)

        self.font = pygame.font.Font(None, max(12, round(self.hud_px * 0.9)))
        self.message_font = pygame.font.Font(None, max(16, self.tile_px * 2))

        self.background = render_maze(maze, theme, self.scale)
        self.sprites = SpriteSet(theme, self.scale)

        # Overlay settings
        self.show_target = show_target
        self.show_planned_path = show_planned_path

        self.is_open = True

    def _fit_scale(self) -> int:
        desktop_sizes = pygame.display.get_desktop_sizes()
        screen_width, screen_height = desktop_sizes[0] if desktop_sizes else (1280, 800)

        base_width = self.maze.width * self.theme.tile
        base_height = self.maze.height * self.theme.tile + self.theme.hud_height

        fit = int(min(
            screen_width * self.SCREEN_FRACTION // base_width,
            screen_height * self.SCREEN_FRACTION // base_height,
        ))

        return max(1, min(self.MAX_SCALE, fit))

    # Drawing

    def draw(
        self,
        frame: SimulationFrame,
        pose: PlayerPose = INITIAL_POSE,
        previous_frame: SimulationFrame | None = None,
        progress: float = 1.0,
        message: str | None = None,
    ) -> None:
        """
        Draw a frame. With previous_frame and progress < 1, the player is drawn
        part-way between the two positions (display only).
        """

        self._draw_scene(frame, previous_frame, progress)

        ghost_pos = self._ghost_position(frame, previous_frame, progress)
        if ghost_pos is not None:
            self._draw_ghost(ghost_pos, frame.state.ghost_direction)

        position = self._player_position(frame, previous_frame, progress)
        self._blit_sprite(self.sprites.player(pose.mouth, pose.facing), position)

        self._finish(frame, message)

    def draw_death(
        self,
        frame: SimulationFrame,
        death_index: int,
        message: str | None = None,
    ) -> None:
        self._draw_scene(frame, None, 1.0)

        if frame.state.ghost_position is not None:
            self._draw_ghost(
                self._tile_pixel(frame.state.ghost_position),
                frame.state.ghost_direction,
            )

        position = self._tile_pixel(frame.state.pacman_position)
        self._blit_sprite(self.sprites.death[death_index], position)

        self._finish(frame, message)

    def _draw_scene(
        self,
        frame: SimulationFrame,
        previous_frame: SimulationFrame | None,
        progress: float,
    ) -> None:
        self.screen.fill(self.theme.background)
        self.screen.blit(self.background, (self.maze_x, self.hud_px))

        # The pellet on the destination tile is eaten halfway through the move.
        if previous_frame is not None and progress < 0.5:
            pellets = previous_frame.state.remaining_pellets
        else:
            pellets = frame.state.remaining_pellets

        self._draw_pellets(pellets)
        self._draw_planned_path(frame)
        self._draw_target(frame)

    def _finish(self, frame: SimulationFrame, message: str | None) -> None:
        self._draw_hud(frame)

        if message is not None:
            self._draw_message(message)

        pygame.display.flip()

    def _tile_pixel(self, position: Position | tuple[float, float]) -> tuple[float, float]:
        """Screen position of a tile's top-left corner (accepts fractional tiles)."""
        row, col = position
        return self.maze_x + col * self.tile_px, self.hud_px + row * self.tile_px

    def _tile_center(self, position: Position) -> tuple[int, int]:
        x, y = self._tile_pixel(position)
        return round(x + self.tile_px / 2), round(y + self.tile_px / 2)

    def _player_position(
        self,
        frame: SimulationFrame,
        previous_frame: SimulationFrame | None,
        progress: float,
    ) -> tuple[float, float]:
        current = frame.state.pacman_position

        if previous_frame is None or progress >= 1.0:
            return self._tile_pixel(current)

        previous = previous_frame.state.pacman_position

        # Only a one-tile move is interpolated; anything else is drawn in place.
        if move_direction(previous, current) is None:
            return self._tile_pixel(current)

        row = previous[0] + (current[0] - previous[0]) * progress
        col = previous[1] + (current[1] - previous[1]) * progress
        return self._tile_pixel((row, col))

    def _ghost_position(
        self,
        frame: SimulationFrame,
        previous_frame: SimulationFrame | None,
        progress: float,
    ) -> tuple[float, float] | None:
        current = frame.state.ghost_position
        if current is None:
            return None

        if previous_frame is None or progress >= 1.0:
            return self._tile_pixel(current)

        previous = previous_frame.state.ghost_position
        if previous is None or move_direction(previous, current) is None:
            return self._tile_pixel(current)

        row = previous[0] + (current[0] - previous[0]) * progress
        col = previous[1] + (current[1] - previous[1]) * progress
        return self._tile_pixel((row, col))

    def _draw_ghost(
        self,
        tile_pixel: tuple[float, float],
        direction: tuple[int, int],
    ) -> None:
        """Draw Blinky on the 8x8 base pixel grid."""
        x = round(tile_pixel[0])
        y = round(tile_pixel[1])
        s = self.scale

        body_color = (255, 0, 0)
        eye_white = (255, 255, 255)
        eye_pupil = (33, 33, 255)

        # Rounded top + torso + wavy skirt on an 8x8 pixel grid
        pygame.draw.rect(self.screen, body_color, pygame.Rect(x + 2 * s, y + s, 4 * s, s))
        pygame.draw.rect(self.screen, body_color, pygame.Rect(x + s, y + 2 * s, 6 * s, 4 * s))
        pygame.draw.rect(self.screen, body_color, pygame.Rect(x + s, y + 6 * s, s, s))
        pygame.draw.rect(self.screen, body_color, pygame.Rect(x + 3 * s, y + 6 * s, 2 * s, s))
        pygame.draw.rect(self.screen, body_color, pygame.Rect(x + 6 * s, y + 6 * s, s, s))

        # Eyes + pupils shifted toward movement direction
        d_row, d_col = direction
        eye_shift_x = s if d_col > 0 else 0
        pupil_dx = 1 if d_col > 0 else 0
        pupil_dy = 1 if d_row > 0 else 0

        left_eye_x = x + s + eye_shift_x
        right_eye_x = x + 4 * s + eye_shift_x
        eye_y = y + 3 * s

        pygame.draw.rect(self.screen, eye_white, pygame.Rect(left_eye_x, eye_y, 2 * s, 2 * s))
        pygame.draw.rect(self.screen, eye_white, pygame.Rect(right_eye_x, eye_y, 2 * s, 2 * s))

        pygame.draw.rect(
            self.screen,
            eye_pupil,
            pygame.Rect(left_eye_x + pupil_dx * s, eye_y + pupil_dy * s, s, s),
        )
        pygame.draw.rect(
            self.screen,
            eye_pupil,
            pygame.Rect(right_eye_x + pupil_dx * s, eye_y + pupil_dy * s, s, s),
        )

    def _blit_sprite(self, sprite: pygame.Surface, tile_pixel: tuple[float, float]) -> None:
        offset = self.theme.sprite_offset * self.scale
        x, y = tile_pixel
        self.screen.blit(sprite, (round(x + offset), round(y + offset)))

    def _draw_pellets(self, pellets: set[Position]) -> None:
        size = self.theme.pellet * self.scale
        inset = (self.theme.tile - self.theme.pellet) // 2 * self.scale

        for position in pellets:
            x, y = self._tile_pixel(position)
            self.screen.fill(
                self.theme.pellet_color,
                pygame.Rect(round(x) + inset, round(y) + inset, size, size),
            )

    def _draw_message(self, message: str) -> None:
        """Draw a banner (e.g. "READY!") centred over the maze."""

        text = self.message_font.render(message, True, self.theme.player)
        center = (
            self.width // 2,
            self.hud_px + self.maze.height * self.tile_px // 2,
        )
        self.screen.blit(text, text.get_rect(center=center))

    def _draw_target(self, frame: SimulationFrame) -> None:

        if not self.show_target or frame.status is None:
            return

        target = frame.status.target

        if target is None or target == frame.state.pacman_position:
            return

        pygame.draw.circle(
            self.screen,
            self.theme.target,
            self._tile_center(target),
            self.tile_px * 3 // 4,
            width=self.scale,
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

        pygame.draw.lines(
            self.screen,
            self.theme.path,
            False,
            points,
            width=self.scale,
        )

    def _draw_hud(self, frame: SimulationFrame) -> None:
        step_text = self.font.render(
            f"STEP {frame.state.steps}",
            True,
            self.theme.text,
        )
        self.screen.blit(step_text, step_text.get_rect(midleft=(self.scale * 2, self.hud_px // 2)))

        overlay_text = self.font.render(
            f"T:{'on' if self.show_target else 'off'}  "
            f"P:{'on' if self.show_planned_path else 'off'}",
            True,
            self.theme.text,
        )
        self.screen.blit(
            overlay_text,
            overlay_text.get_rect(midright=(self.width - self.scale * 2, self.hud_px // 2)),
        )

    # Events

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