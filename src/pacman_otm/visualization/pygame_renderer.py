from collections.abc import Iterable

import math

import pygame

from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.frame import SimulationFrame
from pacman_otm.visualization.animation import (
    GAME_OVER_MESSAGE,
    INITIAL_POSE,
    end_message,
    PlayerPose,
    ghost_frame_at,
    ghost_track,
    pacman_track,
    point_along,
    track_remainder,
    wrap_shift,
)
from pacman_otm.visualization.frames import DrawStep
from pacman_otm.visualization.maze_art import render_maze
from pacman_otm.visualization.sprites import DEATH_FRAMES
from pacman_otm.visualization.sprites import SpriteSet
from pacman_otm.visualization.theme import DEFAULT_THEME, Theme

Position = tuple[int, int]
Point = tuple[float, float]

# Ghost overlay lanes, in base pixels from the tile centre, by ghost index (cycling): side by
# side where paths share a corridor, leaving the centre to Pac-Man's path.
GHOST_LANES = (-2.25, -0.75, 0.75, 2.25)
# Target marker shape per ghost kind, so markers on one tile stay distinguishable.
GHOST_MARKERS = frozendict({"blinky": "ring", "pinky": "square", "inky": "diamond", "clyde": "cross"})


class PygameRenderer:
    """
    Draws SimulationFrames on a pixel grid: 8x8 base-pixel tiles scaled up by a
    whole number. The maze background is rendered once; each frame adds the
    ghost spawn stickers, pellets, overlays, the player and the ghosts (always on
    top). Draws only; no game rules.

    Overlays: T and P toggle Pac-Man's target and path, G every ghost's path and
    target in the ghost's overlay colour: paths in lanes beside each other with a
    dark outline, targets as one marker shape per kind, and the raw target (before
    projection onto a corridor) as a dot joined to its marker. Paths and sprites
    through a tunnel are drawn on both edges, clipped to the maze.

    headless=True draws on an offscreen surface without opening a window (video
    export); it needs an explicit scale.

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
        show_ghost_overlays: bool = True,
        headless: bool = False,
    ) -> None:

        if headless and scale is None:
            raise ValueError("A headless renderer needs an explicit scale.")

        pygame.init()
        self.headless = headless

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

        self.caption = f"Pac-Man OTM | {maze.name}"

        if headless:
            self.window = None
            self.screen = pygame.Surface((self.width, self.height))
        else:
            window_size = (round(self.width * display_factor), round(self.height * display_factor))
            self.window = pygame.display.set_mode(window_size)
            # Everything is drawn on self.screen; _present shows it in the window.
            self.screen = self.window if window_size == (self.width, self.height) else pygame.Surface(
                (self.width, self.height)
            )
            pygame.display.set_caption(self.caption)

        self.maze_rect = pygame.Rect(self.maze_x, self.hud_px, maze.width * self.tile_px, maze.height * self.tile_px)

        self.font = pygame.font.Font(None, max(12, round(self.hud_px * 0.9)))
        self.message_font = pygame.font.Font(None, max(16, self.tile_px * 2))

        self.background = render_maze(maze, theme, self.scale)
        self.sprites = SpriteSet(theme, self.scale)

        # Overlay settings
        self.show_target = show_target
        self.show_planned_path = show_planned_path
        self.show_ghost_overlays = show_ghost_overlays

        # Optional text in the middle of the HUD, e.g. "RUN 3/20" in an experiment replay.
        self.hud_label: str | None = None

        # Called with every KEYDOWN the renderer handles (e.g. the keyboard input of
        # `play`, which buffers turns pressed while Pac-Man is not being asked).
        self.key_listeners: list = []

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
        ghost_frame: int | None = None,
    ) -> None:
        """
        Draw a frame. With previous_frame and progress < 1, the player and the
        ghosts are drawn part-way between the two positions (display only).
        The last frame of a completed run gets the "COMPLETE!" banner unless
        another message is given.
        ghost_frame picks the ghosts' hem; by default it follows the clock, so
        ghosts keep moving while the picture holds still.
        """

        ghost_tracks = self._ghost_tracks(frame, previous_frame, progress)
        self._draw_scene(frame, previous_frame, progress, ghost_tracks)

        self._blit_sprite(
            self.sprites.player(pose.mouth, pose.facing),
            self._player_point(frame, previous_frame, progress),
        )

        self._draw_ghosts(frame, ghost_tracks, ghost_frame)

        if message is None and progress >= 1.0:
            message = end_message(frame.state)

        self._finish(frame, message)

    def draw_step(self, step: DrawStep, ghost_frame: int | None = None) -> None:
        """Draw one picture of frames.py's step sequences (live, replay and export share them)."""

        if step.death_index is not None:
            self.draw_death(step.frame, step.death_index, step.message)
        else:
            self.draw(
                step.frame,
                step.pose,
                previous_frame=step.previous_frame,
                progress=step.progress,
                message=step.message,
                ghost_frame=ghost_frame,
            )

    def draw_death(
        self,
        frame: SimulationFrame,
        death_index: int,
        message: str | None = None,
    ) -> None:
        # The ghosts leave the picture while Pac-Man dies, as in the arcade.
        self._draw_scene(frame, None, 1.0, [])

        self._blit_sprite(self.sprites.death[death_index], frame.state.pacman_point)

        # "GAME OVER!" once the death sequence has played.
        if message is None and death_index == DEATH_FRAMES - 1:
            message = end_message(frame.state)

        self._finish(frame, message)

    def _draw_scene(
        self,
        frame: SimulationFrame,
        previous_frame: SimulationFrame | None,
        progress: float,
        ghost_tracks: list[list[Point]],
    ) -> None:
        self.screen.fill(self.theme.background)
        self.screen.blit(self.background, (self.maze_x, self.hud_px))
        self._draw_stickers([ghost.kind for ghost in frame.state.ghosts])

        # The pellet on the destination tile is eaten halfway through the move.
        if previous_frame is not None and progress < 0.5:
            pellets = previous_frame.state.remaining_pellets
        else:
            pellets = frame.state.remaining_pellets

        self._draw_pellets(pellets)

        # Plans are about the game in progress: a finished run shows none.
        if not frame.state.terminated:
            self._draw_planned_path(frame)
            self._draw_target(frame)
            self._draw_ghost_overlays(frame, ghost_tracks)

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

    def _player_point(
        self,
        frame: SimulationFrame,
        previous_frame: SimulationFrame | None,
        progress: float,
    ) -> Point:
        """Pac-Man's point in tiles, part-way along his track from the previous frame."""

        if previous_frame is None or progress >= 1.0:
            return frame.state.pacman_point

        point, _ = point_along(pacman_track(previous_frame.state, frame.state), progress)
        return point

    def _wrapped_copies(self, point: Point) -> list[Point]:
        """A point off the grid (in a tunnel mouth) is also drawn where it comes back in."""

        height, width = self.maze.height, self.maze.width
        rows = [point[0]] + ([point[0] + height] if point[0] < 0 else [point[0] - height] if point[0] > height - 1 else [])
        cols = [point[1]] + ([point[1] + width] if point[1] < 0 else [point[1] - width] if point[1] > width - 1 else [])
        return [(row, col) for row in rows for col in cols]

    def _blit_sprite(self, sprite: pygame.Surface, point: Point) -> None:
        """A sprite at a point in tiles; off the grid, on both edges and clipped to the maze."""

        offset = self.theme.sprite_offset * self.scale
        copies = self._wrapped_copies(point)

        if len(copies) > 1:
            self.screen.set_clip(self.maze_rect)

        for copy in copies:
            x, y = self._tile_pixel(copy)
            self.screen.blit(sprite, (round(x + offset), round(y + offset)))

        self.screen.set_clip(None)

    def _draw_pellets(self, pellets: set[Position]) -> None:
        size = self.theme.pellet * self.scale
        inset = (self.theme.tile - self.theme.pellet) // 2 * self.scale

        for position in pellets:
            x, y = self._tile_pixel(position)
            self.screen.fill(
                self.theme.pellet_color,
                pygame.Rect(round(x) + inset, round(y) + inset, size, size),
            )

    def _draw_stickers(self, kinds: list[str]) -> None:
        """A dim ghost on every spawn tile, coloured by the ghost that starts there."""

        offset = (self.theme.tile - self.theme.sticker) // 2 * self.scale

        for index, spawn in enumerate(self.maze.ghost_spawns):
            sticker = self.sprites.sticker(kinds[index] if index < len(kinds) else None)
            x, y = self._tile_pixel(spawn)
            self.screen.blit(sticker, (round(x) + offset, round(y) + offset))

    def _ghost_tracks(
        self,
        frame: SimulationFrame,
        previous_frame: SimulationFrame | None,
        progress: float,
    ) -> list[list[Point]]:
        """Per ghost, the rest of its track this tick from where it is drawn (its point first)."""

        if previous_frame is None or progress >= 1.0:
            return [[frame.state.ghost_point(index)] for index in range(len(frame.state.ghosts))]

        return [
            track_remainder(ghost_track(previous_frame.state, frame.state, index), progress)
            for index in range(len(frame.state.ghosts))
        ]

    def _draw_ghosts(self, frame: SimulationFrame, ghost_tracks: list[list[Point]], ghost_frame: int | None) -> None:
        if ghost_frame is None:
            ghost_frame = ghost_frame_at(pygame.time.get_ticks())

        for index, ghost in enumerate(frame.state.ghosts):
            points = ghost_tracks[index]
            direction = point_along(points, 0.0)[1] if len(points) > 1 else None
            sprite = self.sprites.ghost(ghost.kind, ghost_frame, direction or ghost.heading)
            self._blit_sprite(sprite, points[0])

    def _draw_ghost_overlays(self, frame: SimulationFrame, ghost_tracks: list[list[Point]]) -> None:
        """
        Every ghost's path and target, in a fixed order so overlaps look the same in
        every frame: all outlines, then all paths (each in its lane), then the
        targets (outline and marker) and raw-target dots.
        """
        if not self.show_ghost_overlays:
            return

        overlays = []

        for index, (ghost, status) in enumerate(zip(frame.state.ghosts, frame.ghost_statuses)):
            if status is None:
                continue

            # From where the ghost is drawn, along the rest of its planned path.
            path = status.planned_path
            ahead = path[path.index(ghost.position) + 1:] if ghost.position in path else path
            points = [*ghost_tracks[index], *ahead] if ghost_tracks else [frame.state.ghost_point(index), *ahead]
            lane = GHOST_LANES[index % len(GHOST_LANES)] * self.scale
            overlays.append((ghost.kind, status, self._lane_points(points, lane)))

        outline = self.theme.overlay_outline

        for _, _, lines in overlays:
            for line in lines:
                pygame.draw.lines(self.screen, outline, False, line, width=self.scale + 2)

        for kind, _, lines in overlays:
            for line in lines:
                pygame.draw.lines(self.screen, self.theme.ghost_overlay[kind], False, line, width=self.scale)

        self.screen.set_clip(self.maze_rect)

        for kind, status, _ in overlays:
            if status.target is None:
                continue

            color = self.theme.ghost_overlay[kind]
            center = self._tile_center(status.target)
            raw = status.raw_target

            if raw is not None and raw != status.target:
                raw_center = self._tile_center(raw)
                pygame.draw.line(self.screen, color, center, raw_center, width=max(1, self.scale // 2))
                pygame.draw.circle(self.screen, color, raw_center, self.scale + 1)

            self._draw_marker(GHOST_MARKERS.get(kind, "ring"), center, self.tile_px * 5 // 8, outline, self.scale + 2)
            self._draw_marker(GHOST_MARKERS.get(kind, "ring"), center, self.tile_px * 5 // 8, color, self.scale)

        self.screen.set_clip(None)

    def _draw_marker(self, shape: str, center: tuple[int, int], radius: int, color, width: int) -> None:
        x, y = center

        if shape == "square":
            side = round(radius * 1.6)
            pygame.draw.rect(self.screen, color, pygame.Rect(x - side // 2, y - side // 2, side, side), width=width)
        elif shape == "diamond":
            pygame.draw.polygon(
                self.screen, color, [(x, y - radius), (x + radius, y), (x, y + radius), (x - radius, y)], width=width
            )
        elif shape == "cross":
            arm = round(radius * 0.8)
            pygame.draw.line(self.screen, color, (x - arm, y - arm), (x + arm, y + arm), width=width)
            pygame.draw.line(self.screen, color, (x - arm, y + arm), (x + arm, y - arm), width=width)
        else:
            pygame.draw.circle(self.screen, color, center, radius, width=width)

    def _screen_segments(self, path) -> list[list[Point]]:
        """
        Points in tiles -> runs of points in tiles that never jump across the maze: a
        step through a tunnel ends one run off the edge and starts the next off the
        other edge (both clipped to the maze when drawn).
        """
        size = (self.maze.height, self.maze.width)
        runs: list[list[Point]] = [[path[0]]]

        for before, after in zip(path, path[1:]):
            shift = wrap_shift(before, after, size)

            if shift == (0, 0):
                runs[-1].append(after)
            else:
                runs[-1].append((after[0] + shift[0], after[1] + shift[1]))
                runs.append([(before[0] - shift[0], before[1] - shift[1]), after])

        return runs

    def _lane_points(self, path, lane: float) -> list[list[tuple[float, float]]]:
        """
        Screen points of a path through tile centres, moved `lane` pixels to the side:
        horizontal stretches down, vertical ones right (the same for both directions, so
        two paths keep their lanes when they meet head-on); a corner moves both ways.
        """
        lines = []

        for run in self._screen_segments(path):
            if len(run) < 2:
                continue

            centers = [self._tile_center_exact(point) for point in run]
            shifted = []

            for index, (x, y) in enumerate(centers):
                neighbours = centers[max(0, index - 1):index] + centers[index + 1:index + 2]
                horizontal = any(abs(ny - y) < 0.5 and abs(nx - x) >= 0.5 for nx, ny in neighbours)
                vertical = any(abs(nx - x) < 0.5 and abs(ny - y) >= 0.5 for nx, ny in neighbours)
                shifted.append((x + (lane if vertical else 0.0), y + (lane if horizontal else 0.0)))

            lines.append(shifted)

        return lines

    def _tile_center_exact(self, position) -> tuple[float, float]:
        x, y = self._tile_pixel(position)
        return x + self.tile_px / 2, y + self.tile_px / 2

    def _draw_path_line(self, path, color) -> None:
        """A line through tile centres; positions may be fractional (a mover between tiles)."""

        if len(path) < 2:
            return

        self.screen.set_clip(self.maze_rect)

        for run in self._screen_segments(path):
            if len(run) >= 2:
                pygame.draw.lines(
                    self.screen,
                    color,
                    False,
                    [self._tile_center(position) for position in run],
                    width=self.scale,
                )

        self.screen.set_clip(None)

    def _draw_message(self, message: str) -> None:
        """Draw a banner (e.g. "READY!") centred over the maze."""

        color = self.theme.game_over if message == GAME_OVER_MESSAGE else self.theme.player
        text = self.message_font.render(message, True, color)
        center = (
            self.width // 2,
            self.hud_px + self.maze.height * self.tile_px // 2,
        )
        self.screen.blit(text, text.get_rect(center=center))

    def _draw_target(self, frame: SimulationFrame) -> None:

        if not self.show_target or frame.status is None:
            return

        target = frame.status.target

        if target is None or target == frame.state.pacman_occupied:
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

        if frame.status.target == frame.state.pacman_occupied:
            return

        path = frame.status.planned_path
        path_index = frame.status.path_index

        if not path:
            return

        # Keep only the path ahead of Pac-Man.
        self._draw_path_line(path[path_index:], self.theme.path)

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
            f"P:{'on' if self.show_planned_path else 'off'}"
            + (f"  G:{'on' if self.show_ghost_overlays else 'off'}" if self.maze.ghost_spawns else ""),
            True,
            self.theme.text,
        )
        overlay_rect = overlay_text.get_rect(midright=(self.width - self.scale * 2, self.hud_px // 2))
        self.screen.blit(overlay_text, overlay_rect)

        if self.show_ghost_overlays and frame.state.ghosts:
            self._draw_legend(frame, overlay_rect.left - self.scale * 3)

    def _draw_legend(self, frame: SimulationFrame, right: int) -> None:
        """One marker per ghost kind in the run, in its overlay colour, left of the overlay switches."""

        kinds = list(dict.fromkeys(ghost.kind for ghost in frame.state.ghosts))
        radius = max(2, self.hud_px // 4)
        spacing = radius * 3
        y = self.hud_px // 2

        for index, kind in enumerate(reversed(kinds)):
            x = right - radius - index * spacing
            self._draw_marker(GHOST_MARKERS.get(kind, "ring"), (x, y), radius, self.theme.ghost_overlay[kind], max(1, self.scale // 2 + 1))

    def draw_preview(self, highlights: Iterable[Position], status: str) -> None:
        """A maze without a run: spawn stickers, pellets, Pac-Man at the start, highlighted tiles and a status line."""

        self.screen.fill(self.theme.background)
        self.screen.blit(self.background, (self.maze_x, self.hud_px))
        self._draw_stickers([])
        self._draw_pellets(set(self.maze.initial_pellets))

        tint = pygame.Surface((self.tile_px, self.tile_px), pygame.SRCALPHA)
        tint.fill((*self.theme.highlight, self.theme.highlight_alpha))

        for position in highlights:
            self.screen.blit(tint, self._tile_pixel(position))

        sprite = self.sprites.player(INITIAL_POSE.mouth, INITIAL_POSE.facing)
        self._blit_sprite(sprite, self.maze.pacman_start)

        text = self.font.render(status, True, self.theme.text)
        self.screen.blit(text, text.get_rect(midleft=(self.scale * 2, self.hud_px // 2)))

        self._present()

    def _present(self) -> None:
        if self.headless:
            return

        if self.screen is not self.window:
            pygame.transform.smoothscale(self.screen, self.window.get_size(), self.window)

        pygame.display.flip()

    # Events

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.is_open = False

        elif event.type == pygame.KEYDOWN:
            for listener in self.key_listeners:
                listener(event)

            if event.key == pygame.K_t:
                self.show_target = not self.show_target

            elif event.key == pygame.K_p:
                self.show_planned_path = not self.show_planned_path

            elif event.key == pygame.K_g:
                self.show_ghost_overlays = not self.show_ghost_overlays

    def process_events(self) -> bool:
        for event in pygame.event.get():
            self.handle_event(event)

        return self.is_open

    def close(self) -> None:

        pygame.quit()
        self.is_open = False
