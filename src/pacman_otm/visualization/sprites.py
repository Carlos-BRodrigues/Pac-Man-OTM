"""
Procedural sprites, drawn as base-pixel masks and scaled like the maze.

Player: a round body with a rounded notch (a U-shaped bite) cut into its front.
Three shapes: closed (shared by all directions), half and wide open, the last two
in four directions: 9 movement sprites. Plus an 11-frame death sequence.

Ghost: a dome over a straight body with a scalloped hem. The hem alternates
between two frames so a ghost never looks static, and the pupils look the way
it moves. Plus a small dim silhouette, the sticker that marks a spawn tile.
"""

from dataclasses import dataclass
from enum import IntEnum
from math import cos, pi, radians, sin

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


GHOST_FRAMES = 2

# The hem of the 13 px ghost, per frame: (columns filled in the second-to-last
# row, columns filled in the last row). The two frames put the gaps in opposite places.
_GHOST_HEMS = (
    (frozenset(range(13)) - {3, 9}, frozenset({0, 1, 5, 6, 7, 11, 12})),
    (frozenset(range(13)) - {0, 6, 12}, frozenset({2, 3, 4, 8, 9, 10})),
)

# Top-left corners of the 4x4 eye whites and where the 2x2 pupil sits inside them.
_EYE_CORNERS = ((3, 2), (3, 7))
_PUPIL_OFFSETS: dict[Action | None, tuple[int, int]] = {
    Action.LEFT: (1, 0),
    Action.RIGHT: (1, 2),
    Action.UP: (0, 1),
    Action.DOWN: (2, 1),
    None: (1, 1),
}


def ghost_body_mask(frame: int, size: int = 13) -> np.ndarray:
    """Dome, straight body and the hem of `frame`. Drawn for a 13 px sprite."""

    if size != 13:
        raise ValueError("The ghost is drawn for 13 px sprites.")

    y, x = _grid(size)
    centre = (size - 1) / 2
    dome = ((y - centre) ** 2 + (x - centre) ** 2 <= (centre + 0.3) ** 2) & (y <= centre)
    body = (y > centre) & (y < size - 2)
    mask = dome | body

    second_last, last = _GHOST_HEMS[frame % GHOST_FRAMES]

    for col in second_last:
        mask[size - 2, col] = True

    for col in last:
        mask[size - 1, col] = True

    return mask


def ghost_eye_masks(facing: Action | None, size: int = 13) -> tuple[np.ndarray, np.ndarray]:
    """(eye whites, pupils): 4x4 whites with trimmed corners, 2x2 pupils toward `facing`."""

    whites = np.zeros((size, size), dtype=bool)
    pupils = np.zeros((size, size), dtype=bool)
    pupil_row, pupil_col = _PUPIL_OFFSETS[facing]

    for row, col in _EYE_CORNERS:
        whites[row:row + 4, col:col + 4] = True

        for corner_row, corner_col in ((row, col), (row, col + 3), (row + 3, col), (row + 3, col + 3)):
            whites[corner_row, corner_col] = False

        pupils[row + pupil_row:row + pupil_row + 2, col + pupil_col:col + pupil_col + 2] = True

    return whites & ~pupils, pupils


def sticker_mask(size: int) -> np.ndarray:
    """A tiny filled ghost: a rounded top, a body and a notched hem (feet symmetric for size 6)."""

    y, x = _grid(size)
    centre = (size - 1) / 2
    top = ((y - centre) ** 2 + (x - centre) ** 2 <= (centre + 0.4) ** 2) & (y <= centre)
    mask = top | ((y > centre) & (y < size - 1))
    mask[size - 1, [col for col in range(size) if col % 3 != 1]] = True
    return mask


def _layers(layers: list[tuple[np.ndarray, Color]], scale: int) -> pygame.Surface:
    """One surface from several single-colour masks, later masks on top."""

    height, width = layers[0][0].shape
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    surface.fill((0, 0, 0, 0))

    for mask, color in layers:
        for y, x in zip(*np.nonzero(mask)):
            surface.set_at((int(x), int(y)), (*color, 255))

    return pygame.transform.scale_by(surface, scale)


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

        # (kind, frame, facing) -> sprite, and kind or None (neutral) -> sticker; built on first use.
        self._ghosts: dict[tuple[str, int, Action | None], pygame.Surface] = {}
        self._stickers: dict[str | None, pygame.Surface] = {}

    def player(self, mouth: Mouth, facing: Action) -> pygame.Surface:
        key = SpriteKey(mouth, None if mouth == Mouth.CLOSED else facing)
        return self.movement[key]

    def ghost(self, kind: str, frame: int, facing: Action | None) -> pygame.Surface:
        key = (kind, frame % GHOST_FRAMES, facing)

        if key not in self._ghosts:
            whites, pupils = ghost_eye_masks(facing, self.theme.sprite)
            body = ghost_body_mask(key[1], self.theme.sprite) & ~whites & ~pupils
            self._ghosts[key] = _layers(
                [
                    (body, self.theme.ghost_body[kind]),
                    (whites, self.theme.ghost_eye),
                    (pupils, self.theme.ghost_pupil),
                ],
                self.scale,
            )

        return self._ghosts[key]

    def sticker(self, kind: str | None) -> pygame.Surface:
        """The spawn marker, in the colour of the ghost `kind` (None: neutral)."""

        if kind not in self._stickers:
            color = self.theme.ghost_body[kind] if kind is not None else self.theme.sticker_neutral
            surface = _surface(sticker_mask(self.theme.sticker), color, self.scale)
            surface.set_alpha(self.theme.sticker_alpha)
            self._stickers[kind] = surface

        return self._stickers[kind]
