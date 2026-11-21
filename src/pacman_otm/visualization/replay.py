
import pygame

from pacman_otm.simulation.replay import ReplayPlayer
from pacman_otm.visualization.pygame_renderer import PygameRenderer


class ReplayPygameVisualizer:
    def __init__(
        self,
        renderer: PygameRenderer,
        replay: ReplayPlayer,
        fps: int = 8,
    ) -> None:
        if fps <= 0:
            raise ValueError("FPS must be greater than zero.")

        self.renderer = renderer
        self.replay = replay
        self.fps = fps
        self.playing = False

        self.clock = pygame.time.Clock()
        self.elapsed_ms = 0.0

    def _handle_event(self, event: pygame.event.Event) -> None:
        self.renderer.handle_event(event)

        if event.type != pygame.KEYDOWN:
            return

        if event.key == pygame.K_ESCAPE:
            self.renderer.is_open = False

        elif event.key == pygame.K_SPACE:
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
        if not self.playing:
            return

        self.elapsed_ms += delta_ms
        frame_duration_ms = 1000.0 / self.fps

        while self.elapsed_ms >= frame_duration_ms:
            self.elapsed_ms -= frame_duration_ms

            if self.replay.at_end:
                self.playing = False
                self.elapsed_ms = 0.0
                break

            self.replay.next_frame()

    def _update_caption(self) -> None:
        mode = "Playing" if self.playing else "Paused"

        pygame.display.set_caption(
            f"{self.renderer.caption} | Replay "
            f"{self.replay.current_index + 1}/{self.replay.total_frames} "
            f"| {mode} | {self.fps} FPS"
        )

    def run(self) -> None:
        while self.renderer.is_open:
            delta_ms = self.clock.tick(60)

            for event in pygame.event.get():
                self._handle_event(event)

            self._update_playback(delta_ms)
            self.renderer.draw(self.replay.current_frame)
            self._update_caption()

    def close(self) -> None:
        self.renderer.close()
