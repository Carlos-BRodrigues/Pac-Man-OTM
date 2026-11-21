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

    def __call__(self, state: SimulationState) -> Action | None:

        requested = None

        for event in pygame.event.get():
            # Lets the renderer see window close and its overlay toggles
            self.renderer.handle_event(event)

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.renderer.is_open = False

                elif event.key in self.KEY_ACTIONS:
                    # Several presses within one tick: the latest wins
                    requested = self.KEY_ACTIONS[event.key]

        if not self.renderer.is_open:
            raise ControllerAborted("player_quit")

        return requested
