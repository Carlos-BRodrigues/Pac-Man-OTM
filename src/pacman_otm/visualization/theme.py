"""
The visual style in one place: colours and pixel geometry.

Geometry is in *base pixels*: a tile is 8x8 base px, and the whole picture is
scaled up by a whole number (nearest neighbour) so pixels stay crisp.
"""

from dataclasses import dataclass

Color = tuple[int, int, int]


@dataclass(frozen=True)
class Theme:
    # Geometry (base pixels)
    tile: int = 8
    # Sprites are larger than a tile and overlap neighbouring tiles.
    sprite: int = 13
    # Wall outlines sit this far inside wall tiles so sprites never touch them.
    wall_recess: int = 3
    # Radius used to round the outward corners of wall shapes.
    corner_radius: int = 2
    pellet: int = 2
    gate_bar: int = 2
    hud_height: int = 10

    # Colours
    background: Color = (6, 8, 18)
    wall_outline: Color = (25, 25, 166)
    gate: Color = (236, 150, 196)
    pellet_color: Color = (255, 214, 192)
    player: Color = (255, 255, 0)
    spark: Color = (255, 236, 170)
    text: Color = (225, 230, 240)
    target: Color = (120, 250, 120)
    path: Color = (120, 250, 120)
    # Tiles flagged in 'mazes preview' (rule violations), drawn translucent.
    highlight: Color = (235, 64, 52)
    highlight_alpha: int = 120

    @property
    def sprite_offset(self) -> int:
        """
        Top-left of a sprite relative to its tile's top-left. A 13 px sprite
        on an 8 px tile cannot be centred exactly; it hangs 2 px up/left and
        3 px down/right, still clear of the 3 px wall recess.
        """
        return -((self.sprite - self.tile) // 2)


DEFAULT_THEME = Theme()
