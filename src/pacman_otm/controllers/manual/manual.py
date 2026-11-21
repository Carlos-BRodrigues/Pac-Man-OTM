from collections.abc import Callable
from typing import Any

from pacman_otm.controllers.controller import Controller
from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.state import SimulationState

# Returns the direction the player last asked for since the previous call, or None.
DirectionSource = Callable[[SimulationState], Action | None]


class ManualController(Controller):
    """
    A human player steering an always-moving Pac-Man, as in the arcade game.

    Pac-Man keeps going in his current direction every step; the player can only
    change that direction, never stop. A requested turn is remembered and taken
    as soon as it is open, so it can be pressed just before a junction. Against
    a wall he waits in place until a requested direction is open.

    Input comes from an injected source (e.g. pygame keyboard), so this layer
    stays free of any UI library. The source may raise ControllerAborted.
    """

    controller_type = "manual"

    def __init__(
        self,
        maze: Maze,
        direction_source: DirectionSource,
        initial_direction: Action = Action.LEFT,
    ) -> None:
        super().__init__()
        self.maze = maze
        self.direction_source = direction_source
        self.initial_direction = initial_direction
        self.reset()

    def reset(self) -> None:
        self.current_direction = self.initial_direction
        self.requested_direction: Action | None = None

    def select_action(self, state: SimulationState) -> Action:

        requested = self.direction_source(state)

        if requested is not None:
            self.requested_direction = requested

        if (
            self.requested_direction is not None
            and self._is_open(state, self.requested_direction)
        ):
            self.current_direction = self.requested_direction
            self.requested_direction = None

        return self.current_direction

    def _is_open(self, state: SimulationState, direction: Action) -> bool:
        destination = self.maze.get_destination(state.pacman_position, direction)
        return self.maze.is_walkable(destination)

    def describe(self) -> dict[str, Any]:
        return {
            **super().describe(),
            "initial_direction": self.initial_direction.value,
        }
