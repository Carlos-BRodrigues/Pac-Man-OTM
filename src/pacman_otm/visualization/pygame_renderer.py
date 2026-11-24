from collections.abc import Iterable

import math

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

    With an explicit scale the window shows those pixels exactly. By default the
    window fills the same share of the screen for every maze (whichever of width
    or height runs out first), so similar mazes get similar windows: frames are
    drawn at the next whole scale up and smoothly scaled down to the window.
    A whole scale alone jumps (a 52-row maze gets twice the window of a 61-row one).
    """

    MAX_SCALE = 6
    # Share of the desktop the window uses, leaving room for the title bar and taskbar.
    SCREEN_FRACTION = 0.85
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

        # None: fit the screen (see the class docstring); the window is display_factor
        # times the size of the frames drawn at self.scale.
        if scale is None:
            self.scale, display_factor = self._fit_scale()
        else:
            self.scale, display_factor = scale, 1.0

        if self.scale < 1:
            raise ValueError("The scale must be at least 1.")

        self.tile_px = theme.tile * self.scale
        self.hud_px = theme.hud_height * self.scale

        self.width = max(self.MIN_WINDOW_WIDTH, maze.width * self.tile_px)
        self.height = self.hud_px + maze.height * self.tile_px
        # Narrow mazes are centred in a window kept wide enough for the HUD.
        self.maze_x = (self.width - maze.width * self.tile_px) // 2

        window_size = (round(self.width * display_factor), round(self.height * display_factor))
        self.window = pygame.display.set_mode(window_size)
        # Everything is drawn on self.screen; _present shows it in the window.
        self.screen = self.window if window_size == (self.width, self.height) else pygame.Surface(
            (self.width, self.height)
        )

        self.caption = f"Pac-Man OTM | {maze.name}"
        pygame.display.set_caption(self.caption)

        self.font = pygame.font.Font(None, max(12, round(self.hud_px * 0.9)))
        self.message_font = pygame.font.Font(None, max(16, self.tile_px * 2))

        self.background = render_maze(maze, theme, self.scale)
        self.sprites = SpriteSet(theme, self.scale)

        # Overlay settings
        self.show_target = show_target
        self.show_planned_path = show_planned_path

        # Optional text in the middle of the HUD, e.g. "RUN 3/20" in an experiment replay.
        self.hud_label: str | None = None

        self.is_open = True

    def _fit_scale(self) -> tuple[int, float]:
        """The whole scale to draw at, and the factor from it to the window size."""

        desktop_sizes = pygame.display.get_desktop_sizes()
        screen_width, screen_height = desktop_sizes[0] if desktop_sizes else (1280, 800)

        base_width = self.maze.width * self.theme.tile
        base_height = self.maze.height * self.theme.tile + self.theme.hud_height

        # The exact scale that fills the screen share; small mazes stop at MAX_SCALE.
        fit = min(
            screen_width * self.SCREEN_FRACTION / base_width,
            screen_height * self.SCREEN_FRACTION / base_height,
            self.MAX_SCALE,
        )
        # Draw at the next whole scale up, so the window only ever shrinks the frames.
        scale = max(1, math.ceil(fit - 1e-9))
        return scale, fit / scale

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

        self._present()

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

        if self.hud_label:
            label_text = self.font.render(self.hud_label, True, self.theme.text)
            self.screen.blit(label_text, label_text.get_rect(center=(self.width // 2, self.hud_px // 2)))

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

    def draw_preview(self, highlights: Iterable[Position], status: str) -> None:
        """A maze without a run: pellets, Pac-Man at the start, highlighted tiles and a status line."""

        self.screen.fill(self.theme.background)
        self.screen.blit(self.background, (self.maze_x, self.hud_px))
        self._draw_pellets(set(self.maze.initial_pellets))

        tint = pygame.Surface((self.tile_px, self.tile_px), pygame.SRCALPHA)
        tint.fill((*self.theme.highlight, self.theme.highlight_alpha))

        for position in highlights:
            self.screen.blit(tint, self._tile_pixel(position))

        sprite = self.sprites.player(INITIAL_POSE.mouth, INITIAL_POSE.facing)
        self._blit_sprite(sprite, self._tile_pixel(self.maze.pacman_start))

        text = self.font.render(status, True, self.theme.text)
        self.screen.blit(text, text.get_rect(midleft=(self.scale * 2, self.hud_px // 2)))

        self._present()

    def _present(self) -> None:
        if self.screen is not self.window:
            pygame.transform.smoothscale(self.screen, self.window.get_size(), self.window)

        pygame.display.flip()

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
