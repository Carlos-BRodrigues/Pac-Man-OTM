import pygame

from pacman_otm.controllers.controller import ControllerAborted
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.state import SimulationState
from pacman_otm.visualization.pygame_renderer import PygameRenderer


class PygameKeyboardInput:
    """
    Direction source for ManualController. Non-blocking: returns the last
    direction key pressed since the previous call, or None. The game keeps
    running at the live visualizer's pace. Esc or closing the window quits.

    Keys reach it through the renderer (a key listener), so a key pressed on a
    tick where Pac-Man is not asked (between tiles, or in a pellet pause) is
    kept until he is, even though the live view reads the event queue every tick.
    """

    KEY_ACTIONS = frozendict(
        {
            pygame.K_UP: Action.UP,
            pygame.K_w: Action.UP,
            pygame.K_DOWN: Action.DOWN,
            pygame.K_s: Action.DOWN,
            pygame.K_LEFT: Action.LEFT,
            pygame.K_a: Action.LEFT,
            pygame.K_RIGHT: Action.RIGHT,
            pygame.K_d: Action.RIGHT,
        }
    )

    def __init__(self, renderer: PygameRenderer) -> None:
        self.renderer = renderer
        self._requested: Action | None = None
        renderer.key_listeners.append(self._on_key)

    def _on_key(self, event: pygame.event.Event) -> None:
        if event.key == pygame.K_ESCAPE:
            self.renderer.is_open = False

        elif event.key in self.KEY_ACTIONS:
            # Several presses before Pac-Man is asked: the latest wins
            self._requested = self.KEY_ACTIONS[event.key]

    def __call__(self, state: SimulationState) -> Action | None:
        # Lets the renderer see window close, overlay toggles and new keys.
        self.renderer.process_events()

        if not self.renderer.is_open:
            raise ControllerAborted("player_quit")

        requested, self._requested = self._requested, None
        return requested
