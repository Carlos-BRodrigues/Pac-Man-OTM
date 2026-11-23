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
from pacman_otm.mazes.rules.base import Rule, Violation

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
            for run in straight_runs(walkable_mask(grid))
            if len(run) > self.length
        ]


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
