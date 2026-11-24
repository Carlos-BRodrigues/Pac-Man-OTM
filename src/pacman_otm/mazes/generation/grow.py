"""
The grow generator: organic mazes dug path by path into solid wall.

Start from a small valid maze: a ring corridor just inside the shape, or a small
loop at its centre when the ring doesn't fit the shape. Then repeatedly dig a
winding path from one corridor to another through the emptiest wall, until
every rule holds:

- connected and no dead ends, by construction: both ends of every path attach
  to existing corridors;
- one-tile corridors and thick walls, by construction: paths only cross wall
  that is more than `thickness` tiles from any corridor (min_wall_thickness
  sets the thickness), leaving each end through a short straight stem;
- max_block(wall, k) drives the digging: each path is aimed at a wall block
  that is still too big;
- max_straight_run and max_corridor_length: a path is attached near the middle
  of an overlong corridor, which gives it a junction;
- min_loops, min_junction_share, walkable_fraction.min: every path adds a loop,
  junctions and corridor tiles, so more paths are dug until they hold;
- every other rule (and mirror symmetry) is checked on every path.

A path is the cheapest route under a cost that is lower deep inside the wall
(so paths swing into empty space), noisy (so they wander) and charges per turn
(so they run straight for a while). The result must pass the full rule check,
or a GenerationError names the rule that could not be met.
"""

import heapq
from dataclasses import dataclass

import numpy as np

from pacman_otm.mazes.generation.errors import GenerationError
from pacman_otm.mazes.generation.shapes import (
    MIRROR_CHOICES,
    frame_grid,
    playable_area,
    trim_outer_wall,
)
from pacman_otm.mazes.grid import (
    MAX_MAZE_SIZE,
    MIN_MAZE_SIZE,
    Position,
    walkable_mask,
    windows,
)
from pacman_otm.mazes.rules.base import Rule, RuleSet, Violation
from pacman_otm.mazes.rules.hard import HARD_RULES, Connected, Enclosed, SizeBounds
from pacman_otm.mazes.rules.local import MaxBlock, MinWallThickness
from pacman_otm.mazes.rules.structure import (
    MaxCorridorLength,
    MaxDeadEnds,
    MaxStraightRun,
    MinJunctionShare,
    MinLoops,
    MirrorSymmetric,
    WalkableFraction,
    mirror_flips,
)
from pacman_otm.mazes.tiles import Tile

STEPS = ((-1, 0), (0, 1), (1, 0), (0, -1))
START_CHOICES = ("auto", "ring", "center")

# Rules met by what the generator digs next, rather than checked on each path.
TARGET_RULES = (MaxBlock, MaxStraightRun, MaxCorridorLength, MinLoops, MinJunctionShare, WalkableFraction)
# Guaranteed by construction.
BY_CONSTRUCTION = (Connected, Enclosed, SizeBounds, MaxDeadEnds)

# How deep (in tiles from the nearest corridor) the cost keeps getting cheaper.
DEPTH_RANGE = 8


@dataclass(frozen=True)
class GrowParams:
    # "ring": a corridor just inside the shape (arcade-like); "center": a small loop in
    # the middle, which works for any shape; "auto": the ring for rectangular shapes,
    # else center (a ring along a curved edge is one long winding corridor).
    start: str = "auto"
    # Cost of each turn: higher gives longer straight stretches, lower gives more jogs.
    turn_cost: float = 4.0
    # Random extra cost per tile (0..noise): higher makes paths wander more.
    noise: float = 1.5
    # How much cheaper the deepest wall is than wall next to a corridor: higher makes
    # paths swing further into empty space.
    depth_bonus: float = 3.0
    mirror: str = "none"
    # The biggest wall block left when the recipe has no max_block(wall) rule.
    max_wall_block: int = 7
    # Paths dug after every rule holds, for a more open maze.
    extra_paths: int = 0
    # Each path is searched within this many tiles of its target, which keeps
    # digging fast on large mazes.
    search_radius: int = 16
    # Failed digs in a row before this attempt gives up.
    max_failures: int = 80
    # Fresh starts (same seed stream, so still reproducible) before generation fails.
    # Strict run rules on large mazes sometimes need four or five.
    attempts: int = 6

    def __post_init__(self) -> None:
        if self.start not in START_CHOICES:
            raise GenerationError(
                f"topography.start must be one of {', '.join(START_CHOICES)}, got '{self.start}'."
            )

        if self.mirror not in MIRROR_CHOICES:
            raise GenerationError(
                f"topography.mirror must be one of {', '.join(MIRROR_CHOICES)}, got '{self.mirror}'."
            )

        for name in ("turn_cost", "noise", "depth_bonus"):
            if getattr(self, name) < 0:
                raise GenerationError(f"topography.{name} must be >= 0, got {getattr(self, name)}.")

        if self.max_wall_block < 3:
            raise GenerationError(f"topography.max_wall_block must be >= 3, got {self.max_wall_block}.")

        if self.extra_paths < 0:
            raise GenerationError(f"topography.extra_paths must be >= 0, got {self.extra_paths}.")

        if self.search_radius < 6:
            raise GenerationError(f"topography.search_radius must be >= 6, got {self.search_radius}.")

        if self.max_failures < 1:
            raise GenerationError(f"topography.max_failures must be >= 1, got {self.max_failures}.")

        if self.attempts < 1:
            raise GenerationError(f"topography.attempts must be >= 1, got {self.attempts}.")


def generate_grow(
    region: np.ndarray,
    params: GrowParams,
    rules: RuleSet,
    rng: np.random.Generator,
) -> np.ndarray:
    rules = rules if isinstance(rules, RuleSet) else RuleSet(rules)
    region = np.asarray(region, dtype=bool)

    error = None

    for _ in range(params.attempts):
        grower = _Grower(region, params, rules, rng)

        try:
            grower.grow()
            break
        except GenerationError as failure:
            error = failure
    else:
        raise error

    grid = trim_outer_wall(grower.grid)
    remaining = (HARD_RULES + rules).violations(grid)

    if remaining:
        details = "; ".join(f"{v.rule}: {v.message}" for v in remaining)
        raise GenerationError(
            f"The grown maze fails {details}. If this is walkable_fraction, trimming the outer "
            f"wall raised the fraction; otherwise please report the recipe and seed."
        )

    return grid


class _Grower:

    def __init__(self, region: np.ndarray, params: GrowParams, rules: RuleSet, rng: np.random.Generator) -> None:
        self.params = params
        self.rng = rng
        self.rules = rules
        self.playable = playable_area(region)
        self.height, self.width = region.shape

        _check_feasibility(region, params, rules)

        thickness_rules = [rule.size for rule in rules if isinstance(rule, MinWallThickness)]
        self.thickness = max(thickness_rules, default=1)

        block_rules = [rule.size for rule in rules if isinstance(rule, MaxBlock) and rule.tile == "wall"]
        self.block = MaxBlock(tile="wall", size=min(block_rules, default=params.max_wall_block))

        # Checked on every path: everything that isn't a target or guaranteed.
        self.checked = RuleSet(
            rule
            for rule in rules
            if not isinstance(rule, BY_CONSTRUCTION)
            and not (isinstance(rule, TARGET_RULES) and not _is_corridor_block(rule))
        )

        if params.mirror != "none":
            self.checked = self.checked + RuleSet([MirrorSymmetric(axis=params.mirror)])

        self.grid = frame_grid(region)
        # Corridor tiles a branch must not reconnect to (set with each run target).
        self.avoid: frozenset[Position] = frozenset()
        # Coverage targets that no path reached.
        self.skipped = np.zeros(region.shape, dtype=bool)
        self._start()

    # Start

    def _start(self) -> None:
        start = self.params.start

        rectangular = self._playable_is_rectangle()

        if start == "ring" or (start == "auto" and rectangular):
            ring = self._ring()

            if ring is not None:
                self.grid = ring
                return

            if start == "ring":
                raise GenerationError(
                    "topography.start = 'ring' does not fit this shape (its edge is too ragged "
                    "for one clean corridor); use start = 'center' or 'auto'."
                )

        loop = self._center_loop()

        if loop is None:
            raise GenerationError("The shape has no room for a starting loop; use a larger size.")

        self.grid = loop

    def _playable_is_rectangle(self) -> bool:
        rows, cols = np.nonzero(self.playable)
        box = self.playable[rows.min():rows.max() + 1, cols.min():cols.max() + 1]
        return bool(box.all())

    def _ring(self) -> np.ndarray | None:
        """A corridor along the inside edge of the playable area, if that is a valid maze."""

        playable = self.playable
        inner = np.zeros_like(playable)
        inner[1:-1, 1:-1] = (
            playable[1:-1, 1:-1] & playable[:-2, 1:-1] & playable[2:, 1:-1]
            & playable[1:-1, :-2] & playable[1:-1, 2:]
            & playable[:-2, :-2] & playable[:-2, 2:] & playable[2:, :-2] & playable[2:, 2:]
        )
        grid = self.grid.copy()
        grid[playable & ~inner] = Tile.CORRIDOR

        start_rules = RuleSet([Connected(), MaxDeadEnds(count=0), MaxBlock(tile="corridor", size=2)]) + self.checked
        return grid if not start_rules.violations(grid) else None

    def _center_loop(self) -> np.ndarray | None:
        """
        The largest square loop (up to 7x7, or 8 wide across an axis between two
        tile columns) that fits around the middle of the playable area. With
        mirroring the loop is centred on the mirror axes, so it is its own mirror
        image instead of gaining a disconnected copy.
        """
        mirror_columns = self.params.mirror in ("horizontal", "both")
        mirror_rows = self.params.mirror in ("vertical", "both")
        centre_row, centre_col = self._loop_centre(mirror_rows, mirror_columns)

        for half in (3, 2):
            top, bottom = _span(centre_row, half, self.height, mirror_rows)
            left, right = _span(centre_col, half, self.width, mirror_columns)

            if top < 0 or left < 0 or bottom >= self.height or right >= self.width:
                continue

            if not self.playable[top:bottom + 1, left:right + 1].all():
                continue

            grid = self.grid.copy()
            grid[top:bottom + 1, left:right + 1] = Tile.CORRIDOR
            grid[top + 1:bottom, left + 1:right] = Tile.WALL

            if not (RuleSet([Connected(), MaxDeadEnds(count=0)]) + self.checked).violations(grid):
                return grid

        return None

    def _loop_centre(self, on_row_axis: bool, on_column_axis: bool) -> Position:
        """
        The tile deepest inside the shape (a lumpy blob's centre of mass may lie
        outside it), the one nearest the middle among equally deep tiles. On a
        mirror axis the centre must lie on that axis.
        """
        limit = max(self.height, self.width)
        depth = _depth(~np.pad(self.playable, 1), limit)[1:-1, 1:-1].astype(float)
        rows, cols = np.indices(depth.shape)
        middle_row, middle_col = (self.height - 1) / 2, (self.width - 1) / 2

        if on_row_axis:
            depth[np.abs(rows - middle_row) > 0.5] = -1

        if on_column_axis:
            depth[np.abs(cols - middle_col) > 0.5] = -1

        # Deepest first; among ties, nearest the middle (as a fraction below one).
        offset = np.hypot(rows - middle_row, cols - middle_col) / (np.hypot(*depth.shape) + 1)
        index = np.unravel_index(np.argmax(depth - offset), depth.shape)
        return int(index[0]), int(index[1])

    # Growth

    def grow(self) -> None:
        failures = 0

        while True:
            target, rule = self._next_target()

            if target is None:
                break

            attach = rule is not None and _is_run_rule(rule)

            if (attach and self._bridge(target)) or self._dig_towards(target, attach_at=attach):
                failures = 0
                continue

            if rule is None:
                # A coverage target no path reaches (e.g. a narrow lobe): leave it.
                row, col = target
                self.skipped[max(row - 3, 0):row + 4, max(col - 3, 0):col + 4] = True
                continue

            failures += 1

            if failures >= self.params.max_failures:
                raise GenerationError(
                    f"{rule.describe()} cannot be met: no more paths could be dug "
                    f"(e.g. near {target}). {_advice(rule, self.thickness, self.block.size)}"
                )

        # Extra paths for a more open maze; each must keep every rule.
        for _ in range(self.params.extra_paths):
            for _ in range(self.params.max_failures):
                if self._dig_towards(self._random_target(), attach_at=False, keep_rules=True):
                    break

    def _next_target(self) -> tuple[Position | None, Rule | None]:
        """Where the next path should go, and the rule asking for it."""

        self.avoid: frozenset[Position] = frozenset()

        # Overlong corridors first, while there is still room for a branch next to them.
        for rule in self.rules:
            if isinstance(rule, MaxStraightRun | MaxCorridorLength):
                violations = rule.violations(self.grid)

                if violations:
                    tiles = violations[int(self.rng.integers(len(violations)))].positions
                    # The branch's other end goes to a different corridor: back onto the
                    # same one it would run alongside it, making a new long stretch.
                    self.avoid = frozenset(tiles)
                    # A random tile along it (retries try others), away from the ends.
                    inner = tiles[2:-2] if len(tiles) > 4 else tiles
                    return inner[int(self.rng.integers(len(inner)))], rule

        # Wall blocks inside the playable area. Wall beyond it (the shape's ring, ragged
        # edges no path can reach) becomes void when the outline is trimmed.
        corners = windows((self.grid == Tile.WALL) & self.playable, self.block.size)

        depth = _depth(walkable_mask(self.grid), DEPTH_RANGE)

        if corners.any():
            half = self.block.size // 2
            centres = np.argwhere(corners) + half
            # Grow outwards from what exists: among the blocks, those nearest a corridor
            # (a block beyond search_radius from every corridor cannot be reached yet).
            nearness = depth[centres[:, 0], centres[:, 1]]
            frontier = centres[nearness <= nearness.min() + 1]
            pick = frontier[int(self.rng.integers(len(frontier)))]
            return (int(pick[0]), int(pick[1])), self.block

        # Best effort: reach into the rest of the shape too, so the maze fills it out to
        # its edge instead of leaving a band that trimming turns into void.
        far = self.playable & ~self.skipped & (depth >= (self.block.size + 1) // 2)

        if far.any():
            tiles = np.argwhere(far)
            return tuple(int(v) for v in tiles[int(self.rng.integers(len(tiles)))]), None

        for rule in self.rules:
            if isinstance(rule, MinLoops | MinJunctionShare) or (
                isinstance(rule, WalkableFraction) and _below_minimum(rule, self.grid)
            ):
                if rule.violations(self.grid):
                    return self._random_target(), rule

        return None, None

    def _random_target(self) -> Position:
        """Deep inside the wall, where a new path fits best."""

        depth = _depth(walkable_mask(self.grid), DEPTH_RANGE)
        candidates = np.argwhere(self.playable & (depth > self.thickness))

        if len(candidates) == 0:
            tiles = np.argwhere(self.playable)
            return tuple(int(v) for v in tiles[int(self.rng.integers(len(tiles)))])

        weights = depth[tuple(candidates.T)].astype(float) ** 2
        index = int(self.rng.choice(len(candidates), p=weights / weights.sum()))
        return tuple(int(v) for v in candidates[index])

    def _dig_towards(self, target: Position, attach_at: bool, keep_rules: bool = False) -> bool:
        """
        Dig one path near `target`. With attach_at, one end attaches right at the
        target corridor tile (to give it a junction); otherwise both ends are the
        corridor-side entries nearest the target. With keep_rules, the path must
        also keep the target rules (used for extra paths, dug when all rules hold).
        """
        radius = self.params.search_radius
        row, col = target
        top, left = max(row - radius, 0), max(col - radius, 0)
        box = (slice(top, row + radius + 1), slice(left, col + radius + 1))

        grid = self.grid[box]
        playable = self.playable[box]
        walkable = walkable_mask(grid)
        walls = (grid == Tile.WALL) & playable
        depth = _depth(walkable, DEPTH_RANGE)
        local_target = (row - top, col - left)

        stems = self._stems(walkable, walls, depth)

        if attach_at:
            avoid = {(r - top, c - left) for r, c in self.avoid}
            first = [stem for stem in stems if stem[1] == local_target]
            # When there is no other corridor (e.g. only the starting loop), the branch
            # comes back onto the same one: that still gives it two junctions.
            others = [stem for stem in stems if stem[1] not in avoid] or [
                stem for stem in stems if stem[1] != local_target
            ]
        else:
            first = others = stems

        if not first or not others:
            return False

        a = self._near(first, local_target, exclude=None)
        b = self._near(others, local_target, exclude=a)

        if a is None or b is None:
            return False

        allowed = walls & (depth > self.thickness)

        for tile in a[0] + b[0]:
            allowed[tile] = True

        # Around each stem's end, one tile less clearance, so a path can leave a stem
        # in a corner (where the other side of the corner is also close). The rule
        # check below rejects any path that leaves a wall too thin.
        reach = self.thickness

        for stem_tiles, _ in (a, b):
            end_row, end_col = stem_tiles[-1]
            near = (
                slice(max(end_row - reach, 0), end_row + reach + 1),
                slice(max(end_col - reach, 0), end_col + reach + 1),
            )
            allowed[near] |= walls[near] & (depth[near] >= self.thickness)

        cost = (
            1.0
            + self.params.noise * self.rng.random(grid.shape)
            + self.params.depth_bonus * (1.0 - np.minimum(depth, DEPTH_RANGE) / DEPTH_RANGE)
        )
        # From the far end of one stem to the far end of the other; the stems complete it.
        path = _cheapest_path(cost, allowed, a[0][-1], b[0][-1], self.params.turn_cost)

        if path is None:
            return False

        candidate = self.grid.copy()
        tiles = [(r + top, c + left) for r, c in a[0] + path + b[0]]

        for tile in tiles:
            candidate[tile] = Tile.CORRIDOR

        if self.params.mirror != "none":
            candidate = _symmetrize_corridors(candidate, self.params.mirror)

        if self.checked.violations(candidate) or MaxDeadEnds(count=0).violations(candidate):
            return False

        if self._over_maximum(candidate):
            return False

        if keep_rules and self.rules.violations(trim_outer_wall(candidate)):
            return False

        self.grid = candidate
        return True

    def _bridge(self, target: Position) -> bool:
        """
        A straight link from the corridor tile `target` across the wall to the next
        corridor (not the overlong one it belongs to): the short connector between
        two parallel corridors that the arcade maze uses everywhere.
        """
        directions = list(STEPS)
        self.rng.shuffle(directions)

        for d_row, d_col in directions:
            tiles = []
            row, col = target[0] + d_row, target[1] + d_col

            while 0 <= row < self.height and 0 <= col < self.width and len(tiles) <= self.params.search_radius:
                if self.grid[row, col] == Tile.CORRIDOR:
                    break

                if self.grid[row, col] != Tile.WALL or not self.playable[row, col]:
                    tiles = []
                    break

                tiles.append((row, col))
                row, col = row + d_row, col + d_col
            else:
                continue

            if not tiles or (row, col) in self.avoid or not (0 <= row < self.height and 0 <= col < self.width):
                continue

            candidate = self.grid.copy()

            for tile in tiles:
                candidate[tile] = Tile.CORRIDOR

            if self.params.mirror != "none":
                candidate = _symmetrize_corridors(candidate, self.params.mirror)

            if self.checked.violations(candidate) or MaxDeadEnds(count=0).violations(candidate):
                continue

            if self._over_maximum(candidate):
                continue

            self.grid = candidate
            return True

        return False

    def _over_maximum(self, grid: np.ndarray) -> bool:
        """walkable_fraction.max only rises as paths are dug, so no path may cross it."""

        for rule in self.rules:
            if isinstance(rule, WalkableFraction):
                trimmed = trim_outer_wall(grid)
                area = int((trimmed != Tile.VOID).sum())

                if area and int(walkable_mask(trimmed).sum()) / area > rule.max:
                    return True

        return False

    def _stems(
        self,
        walkable: np.ndarray,
        walls: np.ndarray,
        depth: np.ndarray,
    ) -> list[tuple[list[Position], Position]]:
        """
        Every way a path can leave a corridor: `thickness` wall tiles in a straight
        line, starting next to a corridor tile and heading away from it, with
        nothing but wall on either side (so the stem keeps walls thick), and
        opening into wall a path can cross (the next tile has enough clearance).
        Each stem is (its tiles from the corridor outwards, the corridor tile behind it).
        """
        length = self.thickness
        opening = walls & (depth >= self.thickness)
        stems = []

        for d_row, d_col in STEPS:
            valid = walkable.copy()

            for k in range(1, length + 1):
                valid &= _shifted(walls, k * d_row, k * d_col)

                # The tiles beside the stem, on both sides.
                for s_row, s_col in ((d_col, d_row), (-d_col, -d_row)):
                    valid &= ~_shifted(walkable, k * d_row + s_row, k * d_col + s_col, fill=True)

            valid &= _shifted(opening, (length + 1) * d_row, (length + 1) * d_col)

            for row, col in zip(*np.nonzero(valid)):
                row, col = int(row), int(col)
                tiles = [(row + k * d_row, col + k * d_col) for k in range(1, length + 1)]
                stems.append((tiles, (row, col)))

        return stems

    def _near(self, stems, target: Position, exclude):
        """A random stem among those closest to the target, a few tiles away from `exclude`."""

        def far_end(stem) -> Position:
            return stem[0][-1]

        def distance(stem) -> int:
            row, col = far_end(stem)
            return abs(row - target[0]) + abs(col - target[1])

        options = [
            stem
            for stem in stems
            if exclude is None
            or abs(far_end(stem)[0] - far_end(exclude)[0]) + abs(far_end(stem)[1] - far_end(exclude)[1])
            > 2 * self.thickness + 2
        ]

        if not options:
            return None

        options.sort(key=distance)
        closest = options[: max(4, len(options) // 6)]
        return closest[int(self.rng.integers(len(closest)))]


# Helpers


def _check_feasibility(region: np.ndarray, params: GrowParams, rules: RuleSet) -> None:
    height, width = region.shape

    if not (MIN_MAZE_SIZE <= height <= MAX_MAZE_SIZE and MIN_MAZE_SIZE <= width <= MAX_MAZE_SIZE):
        raise GenerationError(f"size {height}x{width} is outside {MIN_MAZE_SIZE}..{MAX_MAZE_SIZE}.")

    for axis in ("horizontal", "vertical"):
        needed = params.mirror in (axis, "both")

        if needed and not all(np.array_equal(region, flipped) for flipped in mirror_flips(region, axis)):
            raise GenerationError(
                f"topography.mirror = '{params.mirror}' needs a shape that is {axis}ly symmetric "
                f"(blob shapes take shape.mirror)."
            )

    thickness = max((rule.size for rule in rules if isinstance(rule, MinWallThickness)), default=1)
    blocks = [rule.size for rule in rules if isinstance(rule, MaxBlock) and rule.tile == "wall"]
    block = min(blocks, default=params.max_wall_block)

    # A path through a block needs `thickness` wall on both sides of it.
    if block < 2 * thickness + 1:
        raise GenerationError(
            f"max_block(wall, {block}) is too small for walls {thickness} thick: a corridor through a "
            f"wall block needs {thickness} wall on each side, so use a block size of at least "
            f"{2 * thickness + 1}."
        )

    for rule in rules:
        if isinstance(rule, MaxBlock) and rule.tile == "corridor" and rule.size < 2:
            raise GenerationError(f"{rule.describe()}: grow makes one-tile corridors only.")

        if isinstance(rule, MirrorSymmetric) and params.mirror not in (rule.axis, "both"):
            raise GenerationError(
                f"{rule.describe()} needs topography.mirror = '{rule.axis}' or 'both' (now '{params.mirror}')."
            )


def _is_corridor_block(rule: Rule) -> bool:
    return isinstance(rule, MaxBlock) and rule.tile != "wall"


def _is_run_rule(rule: Rule) -> bool:
    return isinstance(rule, MaxStraightRun | MaxCorridorLength)


def _below_minimum(rule: WalkableFraction, grid: np.ndarray) -> bool:
    area = int((grid != Tile.VOID).sum())
    return area > 0 and int(walkable_mask(grid).sum()) / area < rule.min


def _shifted(mask: np.ndarray, d_row: int, d_col: int, fill: bool = False) -> np.ndarray:
    """result[r, c] = mask[r + d_row, c + d_col]; `fill` outside the grid."""

    height, width = mask.shape
    result = np.full(mask.shape, fill, dtype=bool)
    source_rows = slice(max(d_row, 0), height + min(d_row, 0))
    source_cols = slice(max(d_col, 0), width + min(d_col, 0))
    target_rows = slice(max(-d_row, 0), height + min(-d_row, 0))
    target_cols = slice(max(-d_col, 0), width + min(-d_col, 0))
    result[target_rows, target_cols] = mask[source_rows, source_cols]
    return result


def _depth(walkable: np.ndarray, limit: int) -> np.ndarray:
    """Chebyshev distance to the nearest corridor tile, capped at limit."""

    height, width = walkable.shape
    depth = np.full(walkable.shape, limit, dtype=np.int32)
    reached = walkable.copy()
    depth[reached] = 0

    for step in range(1, limit):
        padded = np.pad(reached, 1)
        grown = reached.copy()

        for d_row in (-1, 0, 1):
            for d_col in (-1, 0, 1):
                grown |= padded[1 + d_row:1 + d_row + height, 1 + d_col:1 + d_col + width]

        depth[grown & ~reached] = step
        reached = grown

    return depth


def _cheapest_path(
    cost: np.ndarray,
    allowed: np.ndarray,
    start: Position,
    goal: Position,
    turn_cost: float,
) -> list[Position] | None:
    """
    Cheapest orthogonal path of allowed tiles, with a cost per turn: A* over
    (tile, heading). Every step costs at least 1, so the Manhattan distance to
    the goal never overestimates and the path found is the cheapest.
    """
    # Flat indices and plain lists: this loop is most of the generator's run time.
    # A state is tile * 5 + heading + 1 (heading -1 = no step taken yet).
    height, width = cost.shape
    goal_row, goal_col = goal
    tile_cost = cost.ravel().tolist()
    open_tile = allowed.ravel().tolist()
    infinity = float("inf")
    distance = [infinity] * (height * width * 5)
    parent = [-1] * (height * width * 5)
    closed = bytearray(height * width * 5)
    rows, cols = np.indices(cost.shape)
    # Manhattan distance to the goal, per tile.
    remaining = (np.abs(rows - goal_row) + np.abs(cols - goal_col)).ravel().tolist()

    first = (start[0] * width + start[1]) * 5
    distance[first] = 0.0
    heap = [(0.0, 0, first)]
    order = 0
    moves = [(index, d_row, d_col, d_row * width + d_col) for index, (d_row, d_col) in enumerate(STEPS)]

    while heap:
        _, _, state = heapq.heappop(heap)

        if closed[state]:
            continue

        closed[state] = 1
        total = distance[state]
        tile, heading = divmod(state, 5)
        heading -= 1
        row, col = divmod(tile, width)

        if row == goal_row and col == goal_col:
            path = []

            while state != -1:
                path.append(divmod(state // 5, width))
                state = parent[state]

            return path[::-1]

        for index, d_row, d_col, d_tile in moves:
            next_row, next_col = row + d_row, col + d_col

            if not (0 <= next_row < height and 0 <= next_col < width):
                continue

            next_tile = tile + d_tile

            if not open_tile[next_tile]:
                continue

            step = tile_cost[next_tile] + (turn_cost if heading != -1 and heading != index else 0.0)
            key = next_tile * 5 + index + 1

            if total + step < distance[key]:
                distance[key] = total + step
                parent[key] = state
                order += 1
                heapq.heappush(heap, (total + step + remaining[next_tile], order, key))

    return None


def _span(centre: int, half: int, size: int, mirrored: bool) -> tuple[int, int]:
    """The first and last row (or column) of a loop side; symmetric in the grid when mirrored."""

    if not mirrored:
        return centre - half, centre + half

    low = (size - 1) // 2 - half
    return low, size - 1 - low


def _symmetrize_corridors(grid: np.ndarray, axis: str) -> np.ndarray:
    """Corridors mirrored onto the other half (or quarters)."""

    corridor = grid == Tile.CORRIDOR

    if axis in ("horizontal", "both"):
        corridor = corridor | corridor[:, ::-1]

    if axis in ("vertical", "both"):
        corridor = corridor | corridor[::-1, :]

    result = grid.copy()
    result[corridor] = Tile.CORRIDOR
    return result


def _advice(rule: Rule, thickness: int, block: int) -> str:
    if isinstance(rule, MaxBlock):
        return (
            f"Wall blocks of {block} remain where no path fits with walls {thickness} thick; "
            f"use a larger max_block(wall) size, a smaller min_wall_thickness, or a larger search_radius."
        )

    if _is_run_rule(rule):
        return "No branch fits along that corridor; use a larger length or a smaller min_wall_thickness."

    return "There is no room for more paths; relax the rule or use a larger size."
