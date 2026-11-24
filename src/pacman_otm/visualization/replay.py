import pygame

from pacman_otm.simulation.replay import ReplayPlayer, ResultSequence
from pacman_otm.visualization.animation import (
    DEATH_FPS,
    SUBFRAMES,
    ends_in_death,
    poses_for_states,
    pacman_track,
    step_poses,
)
from pacman_otm.visualization.pygame_renderer import PygameRenderer
from pacman_otm.visualization.sprites import DEATH_FRAMES


# Pause at the end of a run (after any death animation) before the next run starts.
ADVANCE_HOLD_MS = 1000.0


class ReplayPygameVisualizer:
    """
    Plays back recorded runs. While playing, each step is shown as SUBFRAMES
    in-between frames; stepping with the keys jumps straight to a frame.
    Poses come from the recorded positions only.

    With a ResultSequence (an experiment folder), PageDown / ] and PageUp / [
    move between runs, and with auto-advance on (A toggles) playback goes on
    to the next run when one ends.
    """

    def __init__(
        self,
        renderer: PygameRenderer,
        replay: ReplayPlayer,
        fps: int = 8,
        runs: ResultSequence | None = None,
        run_index: int = 0,
        scale: int | None = None,
        auto_advance: bool = True,
    ) -> None:
        if fps <= 0:
            raise ValueError("FPS must be greater than zero.")

        self.fps = fps
        self.playing = False
        self.clock = pygame.time.Clock()

        self.runs = runs
        self.run_index = run_index
        self.scale = scale
        self.auto_advance = auto_advance

        self._show(renderer, replay)

    @classmethod
    def for_runs(
        cls,
        runs: ResultSequence,
        fps: int = 8,
        scale: int | None = None,
        auto_advance: bool = True,
    ) -> "ReplayPygameVisualizer":
        result = runs.load(0)
        return cls(
            renderer=PygameRenderer(result.maze, scale=scale),
            replay=ReplayPlayer(result),
            fps=fps,
            runs=runs,
            scale=scale,
            auto_advance=auto_advance,
        )

    def _show(self, renderer: PygameRenderer, replay: ReplayPlayer) -> None:
        self.renderer = renderer
        self.replay = replay
        self.poses = poses_for_states(replay.result.states)
        self.elapsed_ms = 0.0

        # Milliseconds into the death sequence, or None when it isn't showing.
        self.death_ms: float | None = None
        # Milliseconds waited at the end of a run before auto-advancing, or None.
        self.advance_ms: float | None = None

        if self.run_count > 1:
            self.renderer.hud_label = f"RUN {self.run_index + 1}/{self.run_count}"
            self.renderer.caption = f"Pac-Man OTM | {self.runs.label(self.run_index)}"

    @property
    def run_count(self) -> int:
        return len(self.runs) if self.runs is not None else 1

    def show_run(self, index: int, playing: bool = False) -> None:
        """Switch to run `index`; a new maze may mean a new window size."""

        if self.runs is None or not 0 <= index < len(self.runs):
            return

        result = self.runs.load(index)
        self.run_index = index
        # A new renderer resizes the window; the old one is dropped without closing pygame.
        self._show(PygameRenderer(result.maze, scale=self.scale), ReplayPlayer(result))
        self.playing = playing

    def _handle_event(self, event: pygame.event.Event) -> None:
        self.renderer.handle_event(event)

        if event.type != pygame.KEYDOWN:
            return

        if event.key == pygame.K_ESCAPE:
            self.renderer.is_open = False
            return

        if event.key in (pygame.K_PAGEDOWN, pygame.K_RIGHTBRACKET):
            self.show_run(self.run_index + 1, playing=self.playing)
            return

        if event.key in (pygame.K_PAGEUP, pygame.K_LEFTBRACKET):
            self.show_run(self.run_index - 1, playing=self.playing)
            return

        if event.key == pygame.K_a:
            self.auto_advance = not self.auto_advance
            return

        if event.key in (
            pygame.K_SPACE,
            pygame.K_RIGHT,
            pygame.K_LEFT,
            pygame.K_HOME,
            pygame.K_END,
        ):
            # Any navigation restarts from a still frame.
            self.elapsed_ms = 0.0
            self.death_ms = None
            self.advance_ms = None

        if event.key == pygame.K_SPACE:
            if self.replay.at_end:
                self.replay.first_frame()
            self.playing = not self.playing

        elif event.key == pygame.K_RIGHT:
            self.playing = False
            self.replay.next_frame()

        elif event.key == pygame.K_LEFT:
            self.playing = False
            self.replay.previous_frame()

        elif event.key == pygame.K_HOME:
            self.playing = False
            self.replay.first_frame()

        elif event.key == pygame.K_END:
            self.playing = False
            self.replay.last_frame()

        elif event.key == pygame.K_UP:
            self.fps = min(self.fps + 2, 60)

        elif event.key == pygame.K_DOWN:
            self.fps = max(self.fps - 2, 1)

    def _update_playback(self, delta_ms: int) -> None:
        if self.advance_ms is not None:
            self.advance_ms += delta_ms
            hold_ms = ADVANCE_HOLD_MS

            if self.death_ms is not None:
                self.death_ms += delta_ms
                hold_ms += DEATH_FRAMES * 1000 / DEATH_FPS

            if self.advance_ms >= hold_ms:
                self.show_run(self.run_index + 1, playing=True)
            return

        if self.death_ms is not None:
            self.death_ms += delta_ms
            return

        if not self.playing:
            return

        self.elapsed_ms += delta_ms
        frame_duration_ms = 1000.0 / self.fps

        while self.elapsed_ms >= frame_duration_ms:
            self.elapsed_ms -= frame_duration_ms
            self.replay.next_frame()

            if self.replay.at_end:
                self.playing = False
                self.elapsed_ms = 0.0

                if ends_in_death(self.replay.current_frame.state):
                    self.death_ms = 0.0

                if self.auto_advance and self.run_index + 1 < self.run_count:
                    self.advance_ms = 0.0
                break

    def _draw(self) -> None:
        index = self.replay.current_index
        frame = self.replay.current_frame

        if self.death_ms is not None:
            death_index = min(DEATH_FRAMES - 1, int(self.death_ms * DEATH_FPS / 1000))
            self.renderer.draw_death(frame, death_index)
            return

        if not self.playing or self.replay.at_end:
            self.renderer.draw(frame, self.poses[index])
            return

        # Part-way to the next frame, in whole in-between frames.
        frame_duration_ms = 1000.0 / self.fps
        subframe = int(self.elapsed_ms / frame_duration_ms * SUBFRAMES)

        if subframe == 0:
            self.renderer.draw(frame, self.poses[index])
            return

        next_frame = self.replay.get_frame(index + 1)
        pose = step_poses(self.poses[index], pacman_track(frame.state, next_frame.state))[subframe - 1]

        self.renderer.draw(
            next_frame,
            pose,
            previous_frame=frame,
            progress=subframe / SUBFRAMES,
        )

    def _update_caption(self) -> None:
        mode = "Playing" if self.playing else "Paused"
        runs = f" | auto-advance {'on' if self.auto_advance else 'off'}" if self.run_count > 1 else ""

        pygame.display.set_caption(
            f"{self.renderer.caption} | Replay "
            f"{self.replay.current_index + 1}/{self.replay.total_frames} "
            f"| {mode} | {self.fps} FPS{runs}"
        )

    def run(self) -> None:
        while self.renderer.is_open:
            delta_ms = self.clock.tick(60)

            for event in pygame.event.get():
                self._handle_event(event)

            self._update_playback(delta_ms)
            self._draw()
            self._update_caption()

    def close(self) -> None:
        self.renderer.close()
