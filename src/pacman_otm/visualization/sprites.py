"""
Procedural sprites, drawn as base-pixel masks and scaled like the maze.

Player: a round body with a rounded notch (a U-shaped bite) cut into its front.
Three shapes: closed (shared by all directions), half and wide open, the last two
in four directions: 9 movement sprites. Plus an 11-frame death sequence.
"""

from dataclasses import dataclass
from enum import IntEnum
from math import cos, pi, radians, sin  # <-- added radians

import numpy as np
import pygame

from pacman_otm.simulation.actions import Action
from pacman_otm.visualization.theme import Color, Theme


class Mouth(IntEnum):
    CLOSED = 0
    HALF = 1
    WIDE = 2


# Half-angle (in radians) of the V-shaped mouth opening
MOUTH_ANGLES = {
    Mouth.HALF: radians(22.5),  # 45° total opening
    Mouth.WIDE: radians(45.0),  # 90° total opening
}

DEATH_FRAMES = 11


def _grid(size: int) -> tuple[np.ndarray, np.ndarray]:
    return np.mgrid[0:size, 0:size].astype(float)


def _body(size: int) -> np.ndarray:
    y, x = _grid(size)
    centre = (size - 1) / 2
    return (y - centre) ** 2 + (x - centre) ** 2 <= (centre + 0.3) ** 2


def _notch_right(size: int, half_angle: float) -> np.ndarray:
    """The classic V-shaped wedge, opening to the right from the center."""

    y, x = _grid(size)
    centre = (size - 1) / 2
    dx = x - centre
    dy = y - centre

    wedge = (dx > 0) & (np.abs(np.arctan2(dy, dx)) < half_angle)
    vertex = (dx == 0) & (dy == 0)

    return wedge | vertex


def _face(mask_right: np.ndarray, facing: Action) -> np.ndarray:
    """Turn a right-facing mask to face another direction (array rows grow downward)."""

    if facing == Action.RIGHT:
        return mask_right
    if facing == Action.LEFT:
        return np.fliplr(mask_right)
    if facing == Action.UP:
        return np.rot90(mask_right, 1)
    return np.rot90(mask_right, -1)


def player_mask(mouth: Mouth, facing: Action, size: int) -> np.ndarray:
    body = _body(size)

    if mouth == Mouth.CLOSED:
        return body

    half_angle = MOUTH_ANGLES[mouth]
    return _face(body & ~_notch_right(size, half_angle), facing)


def _ellipse(
    size: int, radius_y: float, radius_x: float, centre_y: float
) -> np.ndarray:
    y, x = _grid(size)
    centre_x = (size - 1) / 2
    return ((y - centre_y) / radius_y) ** 2 + ((x - centre_x) / radius_x) ** 2 <= 1.0


def _dots(
    size: int,
    distance: float,
    count: int,
    radius: float,
    phase: float,
    centre_y: float | None = None,
) -> np.ndarray:
    y, x = _grid(size)
    centre = (size - 1) / 2
    centre_y = centre if centre_y is None else centre_y
    mask = np.zeros((size, size), dtype=bool)

    for index in range(count):
        angle = phase + 2 * pi * index / count
        dot_y = centre_y - distance * sin(angle)
        dot_x = centre + distance * cos(angle)
        mask |= (y - dot_y) ** 2 + (x - dot_x) ** 2 <= radius**2 + 0.25

    return mask


def death_masks(size: int) -> list[tuple[np.ndarray, bool]]:
    """
    11 frames of (mask, is_spark). The body squashes flat onto the floor (1-5),
    bursts into fragments that rise and spread (6-9), then fades to sparks (10-11).
    """

    centre = (size - 1) / 2
    bottom = size - 1
    frames = []

    # 1-5: squash. Height shrinks, width grows a little, the base stays put.
    for radius_y in (centre, centre - 1.2, centre - 2.4, centre - 3.6, centre - 4.6):
        radius_x = min(centre + 0.4, centre + (centre - radius_y) * 0.25)
        frames.append(
            (_ellipse(size, radius_y + 0.3, radius_x + 0.3, bottom - radius_y), False)
        )

    # 6-9: fragments burst from the flattened body, rising and spreading as they shrink.
    for centre_y, distance, radius in (
        (bottom - 2.0, 2.4, 1.6),
        (bottom - 3.5, 3.4, 1.4),
        (bottom - 5.0, 4.4, 1.2),
        (centre, 5.4, 1.0),
    ):
        frames.append(
            (_dots(size, distance, 6, radius, phase=pi / 6, centre_y=centre_y), False)
        )

    # 10-11: sparks.
    frames.append((_dots(size, 5.8, 8, 0.5, phase=0.0), True))
    frames.append((_dots(size, 6.0, 4, 0.5, phase=pi / 4), True))

    assert len(frames) == DEATH_FRAMES
    return frames


def _surface(mask: np.ndarray, color: Color, scale: int) -> pygame.Surface:
    height, width = mask.shape
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    surface.fill((0, 0, 0, 0))

    for y, x in zip(*np.nonzero(mask)):
        surface.set_at((int(x), int(y)), (*color, 255))

    return pygame.transform.scale_by(surface, scale)


@dataclass(frozen=True)
class SpriteKey:
    mouth: Mouth
    # None for the closed shape, which is shared by all directions
    facing: Action | None


class SpriteSet:
    """All player sprites for one theme and scale, built once."""

    def __init__(self, theme: Theme, scale: int) -> None:
        self.theme = theme
        self.scale = scale
        size = theme.sprite

        self.movement: dict[SpriteKey, pygame.Surface] = {
            SpriteKey(Mouth.CLOSED, None): _surface(
                player_mask(Mouth.CLOSED, Action.RIGHT, size), theme.player, scale
            ),
        }

        for mouth in (Mouth.HALF, Mouth.WIDE):
            for facing in Action:
                self.movement[SpriteKey(mouth, facing)] = _surface(
                    player_mask(mouth, facing, size), theme.player, scale
                )

        self.death: list[pygame.Surface] = [
            _surface(mask, theme.spark if is_spark else theme.player, scale)
            for mask, is_spark in death_masks(size)
        ]

    def player(self, mouth: Mouth, facing: Action) -> pygame.Surface:
        key = SpriteKey(mouth, None if mouth == Mouth.CLOSED else facing)
        return self.movement[key]
