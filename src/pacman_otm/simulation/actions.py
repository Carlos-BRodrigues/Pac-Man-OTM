from enum import Enum


class Action(Enum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"

    @property
    def reverse(self) -> "Action":
        """The opposite direction: ghosts may not take it except at a dead end."""
        return _REVERSE[self]


_REVERSE = {
    Action.UP: Action.DOWN,
    Action.DOWN: Action.UP,
    Action.LEFT: Action.RIGHT,
    Action.RIGHT: Action.LEFT,
}
