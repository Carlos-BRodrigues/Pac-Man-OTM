"""
Rules about the shape of the corridor network as a whole.

They are measured on tiles, which suits one-tile corridors. In wide corridors
every tile has 3 or more neighbours, so junction and loop counts mean little.
"""

from dataclasses import dataclass
from typing import Literal

import numpy as np

from pacman_otm.mazes.grid import (
    components,
    corridor_chains,
    dead_end_mask,
    edge_count,
    junction_mask,
    positions,
    straight_runs,
    tile_mask,
    walkable_mask,
)
from pacman_otm.mazes.rules.base import Position, Rule, Violation

MirrorAxis = Literal["horizontal", "vertical", "both"]
MIRROR_AXES: tuple[MirrorAxis, ...] = ("horizontal", "vertical", "both")


def cycle_rank(mask: np.ndarray) -> int:
    """Independent loops: edges - tiles + regions."""
    _, regions = components(mask)
    return edge_count(mask) - int(mask.sum()) + regions


def mirror_flips(grid: np.ndarray, axis: MirrorAxis) -> list[np.ndarray]:
    """
    The reflections a grid must equal. 'horizontal' flips left <-> right (the
    two halves sit side by side, as in the classic maze); 'vertical' flips
    top <-> bottom; 'both' requires both.
    """
    if axis == "horizontal":
        return [grid[:, ::-1]]
    if axis == "vertical":
        return [grid[::-1, :]]
    return [grid[:, ::-1], grid[::-1, :]]


def _require_non_negative(name: str, value: int) -> None:
    if value < 0:
        raise ValueError(f"{name} must be >= 0, got {value}.")


def _require_fraction(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1, got {value}.")


@dataclass(frozen=True)
class MaxDeadEnds(Rule):
    """At most `count` tiles with a single neighbour; 0 means no dead ends."""

    name = "max_dead_ends"

    count: int

    def __post_init__(self) -> None:
        _require_non_negative("count", self.count)

    def violations(self, grid: np.ndarray) -> list[Violation]:
        dead_ends = dead_end_mask(walkable_mask(grid))
        found = int(dead_ends.sum())

        if found <= self.count:
            return []

        return [self._violation(f"{found} dead end(s), at most {self.count} allowed", positions(dead_ends))]


@dataclass(frozen=True)
class MaxStraightRun(Rule):
    """No straight stretch longer than `length` tiles without a junction."""

    name = "max_straight_run"

    length: int

    def __post_init__(self) -> None:
        if self.length < 2:
            raise ValueError(f"length must be >= 2, got {self.length}.")

    def violations(self, grid: np.ndarray) -> list[Violation]:
        return [
            self._violation(f"straight run of {len(run)} tiles, at most {self.length}", run)
            for run in straight_runs(walkable_mask(grid), min_length=self.length + 1)
        ]

    def holds_after_change(self, grid: np.ndarray, position: Position) -> bool:
        # A change alters the tile and its neighbours' junction status, so only runs on
        # the three rows and three columns through it can change. Each band is taken
        # with one more line on either side, so junctions at its edge are judged right.
        row, col = position
        height, width = grid.shape
        walkable = walkable_mask(grid)
        top, left = max(row - 2, 0), max(col - 2, 0)

        rows = walkable[top:row + 3, :]
        for run in straight_runs(rows, min_length=self.length + 1):
            run_rows = {tile[0] + top for tile in run}
            if len(run_rows) == 1 and abs(run_rows.pop() - row) <= 1:
                return False

        columns = walkable[:, left:col + 3]
        for run in straight_runs(columns, min_length=self.length + 1):
            run_cols = {tile[1] + left for tile in run}
            if len(run_cols) == 1 and abs(run_cols.pop() - col) <= 1:
                return False

        return True


@dataclass(frozen=True)
class MaxCorridorLength(Rule):
    """
    No choice-free corridor longer than `length` tiles, turns included, counted
    from the junction (or dead end) at one end to the one at the other.
    """

    name = "max_corridor_length"

    length: int

    def __post_init__(self) -> None:
        if self.length < 2:
            raise ValueError(f"length must be >= 2, got {self.length}.")

    def violations(self, grid: np.ndarray) -> list[Violation]:
        return [
            self._violation(
                f"corridor of {len(chain)} tiles without a choice, at most {self.length}",
                sorted(set(chain)),
            )
            for chain in corridor_chains(walkable_mask(grid))
            if len(chain) > self.length
        ]

    def holds_after_change(self, grid: np.ndarray, position: Position) -> bool:
        # Only corridors through the changed tile or its neighbours can change. Each is
        # walked out from there, stopping as soon as it is too long: O(length).
        walkable = walkable_mask(grid)
        row, col = position

        for start in ((row, col), (row - 1, col), (row, col - 1), (row + 1, col), (row, col + 1)):
            if _corridor_length_through(walkable, start, self.length) > self.length:
                return False

        return True


@dataclass(frozen=True)
class MinJunctionShare(Rule):
    """At least `share` of the walkable tiles have 3 or more neighbours."""

    name = "min_junction_share"

    share: float

    def __post_init__(self) -> None:
        _require_fraction("share", self.share)

    def violations(self, grid: np.ndarray) -> list[Violation]:
        walkable = walkable_mask(grid)
        total = int(walkable.sum())
        actual = int(junction_mask(walkable).sum()) / total if total else 0.0

        if actual >= self.share:
            return []

        return [self._violation(f"junction share {actual:.3f}, at least {self.share}")]


@dataclass(frozen=True)
class MinLoops(Rule):
    """At least `count` independent loops (cycle rank of the walkable tiles)."""

    name = "min_loops"

    count: int

    def __post_init__(self) -> None:
        _require_non_negative("count", self.count)

    def violations(self, grid: np.ndarray) -> list[Violation]:
        loops = cycle_rank(walkable_mask(grid))

        if loops >= self.count:
            return []

        return [self._violation(f"{loops} loop(s), at least {self.count}")]


@dataclass(frozen=True)
class WalkableFraction(Rule):
    """Walkable tiles as a share of the maze area (all tiles except void)."""

    name = "walkable_fraction"

    min: float = 0.0
    max: float = 1.0

    def __post_init__(self) -> None:
        _require_fraction("min", self.min)
        _require_fraction("max", self.max)

        if self.min > self.max:
            raise ValueError(f"min ({self.min}) must not exceed max ({self.max}).")

    def violations(self, grid: np.ndarray) -> list[Violation]:
        area = int((~tile_mask(grid, "void")).sum())
        fraction = int(walkable_mask(grid).sum()) / area if area else 0.0

        if self.min <= fraction <= self.max:
            return []

        return [self._violation(f"walkable fraction {fraction:.3f}, expected {self.min}..{self.max}")]


def _corridor_length_through(walkable: np.ndarray, start: Position, limit: int) -> int:
    """
    Length of the choice-free corridor through `start` (as corridor_chains counts
    it: chain tiles plus the junction or dead end at each end), or 0 if start is
    not a chain tile. Stops counting once the length passes `limit`.
    """
    height, width = walkable.shape

    def neighbours(tile: Position) -> list[Position]:
        r, c = tile
        return [
            (n_r, n_c)
            for n_r, n_c in ((r - 1, c), (r, c - 1), (r + 1, c), (r, c + 1))
            if 0 <= n_r < height and 0 <= n_c < width and walkable[n_r, n_c]
        ]

    row, col = start

    if not (0 <= row < height and 0 <= col < width and walkable[row, col]):
        return 0

    if len(neighbours(start)) != 2:
        return 0

    length = 1
    seen = {start}

    # Walk both ways along the chain; each way ends at a non-chain tile (counted) or
    # comes back round (a ring without junctions).
    for first in neighbours(start):
        previous, current = start, first

        while length <= limit:
            if current in seen:
                return length  # a ring: every tile already counted

            next_tiles = neighbours(current)
            length += 1

            if len(next_tiles) != 2:
                break  # a junction or dead end ends the corridor

            seen.add(current)
            previous, current = current, next_tiles[0] if next_tiles[1] == previous else next_tiles[1]

    return length


@dataclass(frozen=True)
class MirrorSymmetric(Rule):
    """Walkability is unchanged by the mirror(s) of `axis`; see mirror_flips."""

    name = "mirror_symmetric"

    axis: MirrorAxis

    def __post_init__(self) -> None:
        if self.axis not in MIRROR_AXES:
            raise ValueError(f"axis must be one of {', '.join(MIRROR_AXES)}, got '{self.axis}'.")

    def violations(self, grid: np.ndarray) -> list[Violation]:
        walkable = walkable_mask(grid)
        asymmetric = np.zeros(walkable.shape, dtype=bool)

        for flipped in mirror_flips(walkable, self.axis):
            asymmetric |= walkable != flipped

        if not asymmetric.any():
            return []

        return [
            self._violation(
                f"{int(asymmetric.sum())} tile(s) differ from their mirror image",
                positions(asymmetric),
            )
        ]

    def holds_after_change(self, grid: np.ndarray, position: Position) -> bool:
        # Only the changed tile and its mirror images are compared.
        walkable = walkable_mask(grid)
        height, width = walkable.shape
        row, col = position
        images = []

        if self.axis in ("horizontal", "both"):
            images.append((row, width - 1 - col))

        if self.axis in ("vertical", "both"):
            images.append((height - 1 - row, col))

        return all(walkable[image] == walkable[row, col] for image in images)
