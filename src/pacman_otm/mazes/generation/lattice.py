"""
The lattice generator: corridors along randomly spaced row and column lines.

Most rules hold by construction instead of by luck:
- enclosed: corridors only go inside the playable area (the shape minus its ring);
- connected: the corridor graph starts as a spanning tree;
- no corridor 2x2 and no diagonal contact: parallel lines are at least
  corridor_width + 1 apart, so two corridors never run side by side;
- mirror symmetry: every choice is made for a whole mirror orbit at once.

The rest (dead ends, wall blocks, long runs, loop counts) is met by repairs that
read each violation's positions and add the corridor that fixes it (or, for an
overlong corridor with nowhere to branch, cut it). A final full check must pass;
if it does not, that is a bug, not bad luck.

Wall that touches no corridor and is connected to the outside becomes void
(`trim_outer_wall`), so the maze outline follows its corridors.
"""

from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import numpy as np

from pacman_otm.mazes.generation.errors import GenerationError
from pacman_otm.mazes.generation.shapes import (
    MIRROR_CHOICES,
    frame_grid,
    playable_area,
    trim_outer_wall,
)
from pacman_otm.mazes.grid import MAX_MAZE_SIZE, MIN_MAZE_SIZE, Position
from pacman_otm.mazes.rules.base import Rule, RuleSet, Violation
from pacman_otm.mazes.rules.hard import HARD_RULES
from pacman_otm.mazes.rules.local import MaxBlock
from pacman_otm.mazes.rules.structure import (
    MaxCorridorLength,
    MaxDeadEnds,
    MaxStraightRun,
    MinJunctionShare,
    MinLoops,
    MirrorSymmetric,
    WalkableFraction,
    cycle_rank,
    mirror_flips,
)
from pacman_otm.mazes.tiles import Tile

# (row line index, column line index): a line intersection.
Node = tuple[int, int]
# Two neighbouring intersections on one line, sorted.
Edge = tuple[Node, Node]
# Tile bounds of an edge, including both end blocks: rows r0:r1, cols c0:c1.
Rect = tuple[int, int, int, int]

# Below this a turn would almost never be taken, which can stall the tree.
MIN_DIRECTION_WEIGHT = 0.05

# Seeded retries when node dropout leaves less than half of the lattice connected.
DROPOUT_ATTEMPTS = 10


@dataclass(frozen=True)
class LatticeParams:
    # Distance between neighbouring parallel lines, in tiles (min, max).
    spacing: tuple[int, int] = (2, 4)
    corridor_width: int = 1
    # Share of the unused line segments added as loops after the spanning tree.
    extra_loops: float = 0.1
    mirror: str = "none"
    # -1 favours turning at every node (twisty), +1 continuing straight (long halls).
    straightness: float = 0.0
    # Share of intersections removed before the tree: irregular cells and wall islands.
    node_dropout: float = 0.0
    max_repair_rounds: int = 200

    def __post_init__(self) -> None:
        try:
            low, high = self.spacing
        except (TypeError, ValueError):
            raise GenerationError(
                f"topography.spacing: expected [min, max], got {self.spacing!r}."
            ) from None

        object.__setattr__(self, "spacing", (int(low), int(high)))

        if self.corridor_width < 1:
            raise GenerationError(
                f"topography.corridor_width must be >= 1, got {self.corridor_width}."
            )

        if low < self.corridor_width + 1:
            raise GenerationError(
                f"topography.spacing: min must be >= corridor_width + 1 = "
                f"{self.corridor_width + 1} so parallel corridors never touch, got {low}."
            )

        if high < low:
            raise GenerationError(f"topography.spacing: max ({high}) is below min ({low}).")

        if not 0.0 <= self.extra_loops <= 1.0:
            raise GenerationError(
                f"topography.extra_loops must be between 0 and 1, got {self.extra_loops}."
            )

        if self.mirror not in MIRROR_CHOICES:
            raise GenerationError(
                f"topography.mirror must be one of {', '.join(MIRROR_CHOICES)}, "
                f"got '{self.mirror}'."
            )

        if not -1.0 <= self.straightness <= 1.0:
            raise GenerationError(
                f"topography.straightness must be between -1 and 1, got {self.straightness}."
            )

        if not 0.0 <= self.node_dropout < 0.5:
            raise GenerationError(
                f"topography.node_dropout must be in [0, 0.5), got {self.node_dropout}."
            )

        if self.max_repair_rounds < 1:
            raise GenerationError(
                f"topography.max_repair_rounds must be >= 1, got {self.max_repair_rounds}."
            )

    @property
    def mirrors_columns(self) -> bool:
        """Left <-> right symmetry: the column lines are mirrored."""
        return self.mirror in ("horizontal", "both")

    @property
    def mirrors_rows(self) -> bool:
        return self.mirror in ("vertical", "both")


def generate_lattice(
    region: np.ndarray,
    params: LatticeParams,
    rules: RuleSet | Iterable[Rule],
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Carve a lattice maze into `region` (a shape mask). Returns the tile grid;
    it passes HARD_RULES and `rules`, or a GenerationError says why it cannot.
    """
    region = np.asarray(region, dtype=bool)
    rules = rules if isinstance(rules, RuleSet) else RuleSet(rules)

    check_feasibility(region, params, rules)

    playable = playable_area(region)
    lattice = _Lattice.build(playable, params, rng)
    builder = _Builder(lattice, params, rng, frame_grid(region))

    builder.choose_nodes()
    builder.grow_tree()
    builder.join_components()
    builder.add_extra_loops()
    builder.repair(rules)

    grid = builder.rasterize()
    remaining = (HARD_RULES + rules).violations(grid)

    if remaining:
        details = "; ".join(f"{v.rule}: {v.message}" for v in remaining)
        raise GenerationError(
            f"Bug in the lattice generator: the final check failed ({details}). "
            f"Please report the recipe and seed."
        )

    return grid


def check_feasibility(region: np.ndarray, params: LatticeParams, rules: RuleSet) -> None:
    """Catch parameter combinations that can never work, before generating anything."""

    height, width = region.shape

    if not (
        MIN_MAZE_SIZE <= height <= MAX_MAZE_SIZE and MIN_MAZE_SIZE <= width <= MAX_MAZE_SIZE
    ):
        raise GenerationError(
            f"size {height}x{width} is outside {MIN_MAZE_SIZE}..{MAX_MAZE_SIZE}."
        )

    for axis in ("horizontal", "vertical"):
        needed = params.mirrors_columns if axis == "horizontal" else params.mirrors_rows

        if needed and not all(
            np.array_equal(region, flipped) for flipped in mirror_flips(region, axis)
        ):
            raise GenerationError(
                f"topography.mirror = '{params.mirror}' needs a shape that is "
                f"{axis}ly symmetric; this one is not (blob shapes take shape.mirror)."
            )

    corridor = params.corridor_width
    _, gap_max = params.spacing

    for rule in rules:
        if isinstance(rule, MaxBlock) and rule.tile == "corridor" and rule.size <= corridor:
            raise GenerationError(
                f"{rule.describe()} conflicts with corridor_width = {corridor}: every "
                f"corridor is a {corridor}x{corridor} block. Remove the rule or use "
                f"size > {corridor}."
            )

        if isinstance(rule, MaxBlock) and rule.tile == "wall" and gap_max - corridor >= rule.size:
            raise GenerationError(
                f"{rule.describe()} needs topography.spacing max <= "
                f"{rule.size + corridor - 1} (now {gap_max}): the wall between two "
                f"lines is spacing - corridor_width tiles thick."
            )

        if (
            isinstance(rule, MaxStraightRun | MaxCorridorLength)
            and corridor == 1
            and gap_max + 1 > rule.length
        ):
            raise GenerationError(
                f"{rule.describe()} needs topography.spacing max <= {rule.length - 1} "
                f"(now {gap_max}): one segment between two junctions is spacing + 1 tiles."
            )

        if isinstance(rule, MirrorSymmetric):
            if params.mirror not in (rule.axis, "both"):
                raise GenerationError(
                    f"{rule.describe()} needs topography.mirror = '{rule.axis}' or 'both' "
                    f"(now '{params.mirror}')."
                )


def line_starts(
    low: int,
    high: int,
    width: int,
    spacing: tuple[int, int],
    rng: np.random.Generator,
    mirrored: bool,
) -> list[int]:
    """
    First tiles of the corridor bands of one direction, inside [low, high].
    Gaps between neighbouring starts are drawn uniformly from the gaps that can
    still be completed, so the sequence always ends cleanly: at the far side
    (a remainder thinner than spacing min) or, mirrored, at the centre.
    """
    gap_min, gap_max = spacing
    # p and its mirror image always add up to this.
    mirror_sum = low + high - (width - 1)

    if mirrored:
        def allowed(position: int) -> bool:
            return 2 * position <= mirror_sum

        def can_stop(position: int) -> bool:
            gap = mirror_sum - 2 * position
            return gap == 0 or gap_min <= gap <= gap_max
    else:
        def allowed(position: int) -> bool:
            return position + width - 1 <= high

        def can_stop(position: int) -> bool:
            return position + gap_min + width - 1 > high

    # completable[p]: some sequence from p reaches a valid end.
    completable: dict[int, bool] = {}

    for position in range(high, low - 1, -1):
        if not allowed(position):
            completable[position] = False
            continue

        completable[position] = can_stop(position) or any(
            completable.get(position + gap, False) for gap in range(gap_min, gap_max + 1)
        )

    # A thicker border only when the first tile cannot start a valid sequence.
    start = next(
        (low + offset for offset in range(gap_max) if completable.get(low + offset)),
        None,
    )

    if start is None:
        raise GenerationError(
            f"No line layout fits {high - low + 1} playable tiles with spacing "
            f"{list(spacing)} and corridor_width {width}"
            f"{' mirrored' if mirrored else ''}; change the size or the spacing."
        )

    starts = [start]
    position = start

    while True:
        options: list[int | None] = [None] if can_stop(position) else []
        options += [
            position + gap
            for gap in range(gap_min, gap_max + 1)
            if completable.get(position + gap, False)
        ]

        choice = options[int(rng.integers(len(options)))]

        if choice is None:
            break

        starts.append(choice)
        position = choice

    if mirrored:
        starts += [mirror_sum - p for p in reversed(starts) if mirror_sum - p != p]

    return starts


class _Lattice:
    """Candidate nodes and edges: everything the generator may use, fixed after build."""

    def __init__(
        self,
        rows: list[int],
        cols: list[int],
        width: int,
        playable: np.ndarray,
        mirror: str,
    ) -> None:
        self.rows = rows
        self.cols = cols
        self.width = width

        self.nodes: set[Node] = {
            (i, j)
            for i, row in enumerate(rows)
            for j, col in enumerate(cols)
            if playable[row:row + width, col:col + width].all()
        }

        self.rects: dict[Edge, Rect] = {}

        for i, j in sorted(self.nodes):
            for neighbour in ((i, j + 1), (i + 1, j)):
                if neighbour not in self.nodes:
                    continue

                ni, nj = neighbour
                rect = (rows[i], rows[ni] + width, cols[j], cols[nj] + width)

                if playable[rect[0]:rect[1], rect[2]:rect[3]].all():
                    self.rects[((i, j), neighbour)] = rect

        self.node_edges: dict[Node, list[Edge]] = {node: [] for node in self.nodes}

        for edge in sorted(self.rects):
            for node in edge:
                self.node_edges[node].append(edge)

        self.tile_edges: dict[Position, list[Edge]] = {}
        self.tile_node: dict[Position, Node] = {}

        for edge, (r0, r1, c0, c1) in sorted(self.rects.items()):
            for row in range(r0, r1):
                for col in range(c0, c1):
                    self.tile_edges.setdefault((row, col), []).append(edge)

        for i, j in self.nodes:
            for row in range(rows[i], rows[i] + width):
                for col in range(cols[j], cols[j] + width):
                    self.tile_node[(row, col)] = (i, j)

        last_row, last_col = len(rows) - 1, len(cols) - 1
        self.transforms: list[Callable[[Node], Node]] = [lambda node: node]

        if mirror in ("horizontal", "both"):
            self.transforms.append(lambda node: (node[0], last_col - node[1]))

        if mirror in ("vertical", "both"):
            self.transforms.append(lambda node: (last_row - node[0], node[1]))

        if mirror == "both":
            self.transforms.append(lambda node: (last_row - node[0], last_col - node[1]))

    @classmethod
    def build(
        cls,
        playable: np.ndarray,
        params: LatticeParams,
        rng: np.random.Generator,
    ) -> _Lattice:
        if not playable.any():
            raise GenerationError("The shape leaves no playable area; use a larger size.")

        play_rows = np.flatnonzero(playable.any(axis=1))
        play_cols = np.flatnonzero(playable.any(axis=0))
        width = params.corridor_width

        rows = line_starts(
            int(play_rows[0]), int(play_rows[-1]), width, params.spacing, rng, params.mirrors_rows
        )
        cols = line_starts(
            int(play_cols[0]), int(play_cols[-1]), width, params.spacing, rng, params.mirrors_columns
        )

        lattice = cls(rows, cols, width, playable, params.mirror)

        if not lattice.rects:
            raise GenerationError(
                f"No corridor fits the playable area with spacing {list(params.spacing)}; "
                f"use a larger size or a smaller spacing."
            )

        return lattice

    def node_orbit(self, node: Node) -> list[Node]:
        return sorted({transform(node) for transform in self.transforms})

    def edge_orbit(self, edge: Edge) -> list[Edge]:
        return sorted(
            {
                tuple(sorted((transform(edge[0]), transform(edge[1]))))
                for transform in self.transforms
            }
        )

    @staticmethod
    def other(edge: Edge, node: Node) -> Node:
        return edge[1] if edge[0] == node else edge[0]

    @staticmethod
    def is_horizontal(edge: Edge) -> bool:
        return edge[0][0] == edge[1][0]


class _Builder:
    """The mutable corridor graph and the construction steps that change it."""

    def __init__(
        self,
        lattice: _Lattice,
        params: LatticeParams,
        rng: np.random.Generator,
        frame: np.ndarray,
    ) -> None:
        self.lattice = lattice
        self.params = params
        self.rng = rng
        self.frame = frame

        self.active: set[Node] = set()
        self.chosen: set[Edge] = set()
        # Segments cut to shorten a corridor; never added back, so repairs cannot undo
        # each other forever.
        self.banned: set[Edge] = set()
        self.degree: dict[Node, int] = {}

    # Graph changes, always by whole mirror orbits

    def can_add(self, edge: Edge) -> bool:
        return edge not in self.chosen and edge not in self.banned

    def in_graph(self, node: Node) -> bool:
        return self.degree.get(node, 0) > 0

    def add_orbit(self, edge: Edge) -> list[Edge]:
        added = []

        for image in self.lattice.edge_orbit(edge):
            if image not in self.chosen:
                self.chosen.add(image)
                added.append(image)

                for node in image:
                    self.degree[node] = self.degree.get(node, 0) + 1

        return added

    def remove_orbit(self, edge: Edge) -> None:
        for image in self.lattice.edge_orbit(edge):
            if image in self.chosen:
                self.chosen.remove(image)

                for node in image:
                    self.degree[node] -= 1

    def pick(self, items: list):
        return items[int(self.rng.integers(len(items)))]

    def unused_edges(self) -> list[Edge]:
        """One representative per unused edge orbit between nodes already in the graph."""

        representatives = set()

        for edge in self.lattice.rects:
            if self.can_add(edge) and self.in_graph(edge[0]) and self.in_graph(edge[1]):
                representatives.add(self.lattice.edge_orbit(edge)[0])

        return sorted(representatives)

    def rasterize(self) -> np.ndarray:
        grid = self.frame.copy()

        for edge in self.chosen:
            r0, r1, c0, c1 = self.lattice.rects[edge]
            grid[r0:r1, c0:c1] = Tile.CORRIDOR

        return trim_outer_wall(grid)

    # Construction

    def choose_nodes(self) -> None:
        """Node dropout, then the largest mirror-invariant connected part."""

        lattice = self.lattice
        best: set[Node] = set()

        # Dropout can split the lattice; a few seeded retries keep the most of it.
        attempts = DROPOUT_ATTEMPTS if self.params.node_dropout > 0 else 1

        for _ in range(attempts):
            part = self._largest_invariant_part(self._drop_nodes())

            if len(part) > len(best):
                best = part

            if len(best) >= len(lattice.nodes) / 2:
                break

        if len(best) < 2:
            raise GenerationError(
                "No connected corridor network is left"
                + (
                    f"; topography.node_dropout = {self.params.node_dropout} is too high "
                    f"for this shape."
                    if self.params.node_dropout > 0
                    else "; use a larger size or a smaller spacing."
                )
            )

        self.active = best

    def _drop_nodes(self) -> set[Node]:
        nodes = set(self.lattice.nodes)

        if self.params.node_dropout > 0:
            orbits = sorted({tuple(self.lattice.node_orbit(node)) for node in nodes})

            for orbit in orbits:
                if self.rng.random() < self.params.node_dropout:
                    nodes -= set(orbit)

        return nodes

    def _largest_invariant_part(self, nodes: set[Node]) -> set[Node]:
        """Mirrored mazes need a part that is its own mirror image."""

        best: set[Node] = set()
        seen: set[Node] = set()

        for start in sorted(nodes):
            if start in seen:
                continue

            part = self._reachable(start, nodes)
            seen |= part
            invariant = all(
                {transform(node) for node in part} == part for transform in self.lattice.transforms
            )

            if invariant and len(part) > len(best):
                best = part

        return best

    def _reachable(self, start: Node, allowed: set[Node]) -> set[Node]:
        reached = {start}
        frontier = deque([start])

        while frontier:
            node = frontier.popleft()

            for edge in self.lattice.node_edges[node]:
                other = self.lattice.other(edge, node)

                if other in allowed and other not in reached:
                    reached.add(other)
                    frontier.append(other)

        return reached

    def grow_tree(self) -> None:
        """
        Randomized Prim over mirror orbits. The direction a node was reached from
        weights the next step: straightness > 0 favours going on in the same
        direction, < 0 favours turning.
        """
        lattice = self.lattice
        straight = max(1.0 + self.params.straightness, MIN_DIRECTION_WEIGHT)
        turn = max(1.0 - self.params.straightness, MIN_DIRECTION_WEIGHT)

        tree: set[Node] = set()

        # Frontier entries (source, edge) grouped by weight, so a weighted draw is
        # a bucket draw plus a uniform index. Entries whose far end has joined the
        # tree since are dropped when drawn.
        weights = (1.0, straight, turn)
        buckets: tuple[list[tuple[Node, Edge]], ...] = ([], [], [])
        START, STRAIGHT, TURN = 0, 1, 2

        def enter(node: Node, horizontal: bool | None) -> None:
            tree.add(node)

            for edge in lattice.node_edges[node]:
                other = lattice.other(edge, node)

                if other in self.active and other not in tree:
                    if horizontal is None:
                        bucket = START
                    elif horizontal == lattice.is_horizontal(edge):
                        bucket = STRAIGHT
                    else:
                        bucket = TURN

                    buckets[bucket].append((node, edge))

        for node in lattice.node_orbit(self.pick(sorted(self.active))):
            enter(node, None)

        while True:
            totals = [len(bucket) * weight for bucket, weight in zip(buckets, weights)]

            if not any(totals):
                break

            filled = [index for index, total in enumerate(totals) if total > 0]
            draw = self.rng.random() * sum(totals)
            chosen_bucket = filled[-1]

            for index in filled:
                if draw < totals[index]:
                    chosen_bucket = index
                    break

                draw -= totals[index]

            bucket = buckets[chosen_bucket]
            position = int(self.rng.integers(len(bucket)))
            source, edge = bucket[position]
            bucket[position] = bucket[-1]
            bucket.pop()

            if lattice.other(edge, source) in tree:
                continue

            for image in self.add_orbit(edge):
                for node in image:
                    if node not in tree:
                        enter(node, lattice.is_horizontal(image))

    def join_components(self) -> None:
        """
        Mirrored growth can leave mirror-image pieces that only meet across the
        axis; join them with random crossing edges.
        """
        while True:
            labels = self._component_labels()

            if len(set(labels.values())) <= 1:
                return

            crossing = sorted(
                edge
                for edge in self.lattice.rects
                if edge[0] in labels and edge[1] in labels and labels[edge[0]] != labels[edge[1]]
            )

            if not crossing:
                raise GenerationError("Bug in the lattice generator: the tree is disconnected.")

            self.add_orbit(self.pick(crossing))

    def _component_labels(self) -> dict[Node, int]:
        labels: dict[Node, int] = {}
        # Every active node, with or without edges yet: the start orbit of a
        # mirrored maze can be several nodes that the tree never links.
        graph = self.active

        adjacency: dict[Node, list[Node]] = {node: [] for node in graph}

        for a, b in self.chosen:
            adjacency[a].append(b)
            adjacency[b].append(a)

        count = 0

        for start in sorted(graph):
            if start in labels:
                continue

            labels[start] = count
            count += 1
            frontier = deque([start])

            while frontier:
                node = frontier.popleft()

                for other in adjacency[node]:
                    if other not in labels:
                        labels[other] = labels[start]
                        frontier.append(other)

        return labels

    def add_extra_loops(self) -> None:
        unused = self.unused_edges()
        count = round(self.params.extra_loops * len(unused))

        if count:
            for index in sorted(self.rng.choice(len(unused), size=count, replace=False)):
                self.add_orbit(unused[int(index)])

    # Repair

    def repair(self, rules: RuleSet) -> None:
        ordered = sorted(rules, key=_repair_priority)

        for _ in range(self.params.max_repair_rounds):
            grid = self.rasterize()
            failing = None

            for rule in ordered:
                violations = rule.violations(grid)

                if violations:
                    failing = (rule, violations)
                    break

            if failing is None:
                return

            rule, violations = failing

            if not self._repair(rule, violations, grid):
                raise GenerationError(_advice(rule, violations, self.params))

        raise GenerationError(
            f"Repairs did not settle within {self.params.max_repair_rounds} rounds; "
            f"the rules may pull against each other. Raise topography.max_repair_rounds "
            f"or relax a rule."
        )

    def _repair(self, rule: Rule, violations: list[Violation], grid: np.ndarray) -> bool:
        if isinstance(rule, MaxDeadEnds):
            return self._repair_dead_ends(rule, violations[0].positions)

        if isinstance(rule, MaxBlock) and rule.tile == "wall":
            return self._repair_wall_blocks(rule.size, violations[0].positions)

        if isinstance(rule, MaxStraightRun | MaxCorridorLength):
            return self._repair_long_corridors(rule, violations)

        if isinstance(rule, MinLoops):
            # Each added segment between connected nodes adds at least one loop.
            return self._add_random_edges(max(1, rule.count - cycle_rank(grid == Tile.CORRIDOR)))

        if isinstance(rule, MinJunctionShare):
            return self._add_random_edges(max(1, len(self.unused_edges()) // 20))

        if isinstance(rule, WalkableFraction):
            # Adding corridors only raises the fraction; a maximum cannot be repaired.
            if self._walkable_fraction(grid) > rule.max:
                return False

            return self._add_random_edges(max(1, len(self.unused_edges()) // 20))

        return False

    @staticmethod
    def _walkable_fraction(grid: np.ndarray) -> float:
        area = int((grid != Tile.VOID).sum())
        return int((grid == Tile.CORRIDOR).sum()) / area if area else 0.0

    def _add_random_edges(self, count: int) -> bool:
        unused = self.unused_edges()

        if not unused:
            # Bringing back a node with two links also adds a loop.
            outside = sorted(node for node in self.lattice.nodes if not self.in_graph(node))
            return bool(self._reactivate(outside))

        count = min(count, len(unused))

        for index in sorted(self.rng.choice(len(unused), size=count, replace=False)):
            self.add_orbit(unused[int(index)])

        return True

    def _repair_dead_ends(self, rule: MaxDeadEnds, positions: tuple[Position, ...]) -> bool:
        lattice = self.lattice
        dead_ends = sorted({lattice.tile_node[p] for p in positions if p in lattice.tile_node})
        to_fix = len(positions) - rule.count
        changed = False

        for index in self.rng.permutation(len(dead_ends)):
            if to_fix <= 0:
                break

            node = dead_ends[int(index)]

            if self.degree.get(node, 0) != 1:
                # Already fixed by an earlier move this round.
                to_fix -= 1
                continue

            options = [
                edge
                for edge in lattice.node_edges[node]
                if self.can_add(edge) and self.in_graph(lattice.other(edge, node))
            ]

            if options:
                # Joining two dead ends fixes both.
                joining = [e for e in options if self.degree[lattice.other(e, node)] == 1]
                self.add_orbit(self.pick(joining or options))
            else:
                (edge,) = [e for e in lattice.node_edges[node] if e in self.chosen]

                if len(self.chosen) - len(lattice.edge_orbit(edge)) < 4:
                    return False

                self.remove_orbit(edge)

            changed = True
            to_fix -= 1

        return changed

    def _repair_wall_blocks(self, size: int, corners: tuple[Position, ...]) -> bool:
        lattice = self.lattice
        touched: list[Rect] = []
        changed = False

        for index in self.rng.permutation(len(corners)):
            row, col = corners[int(index)]
            window = (row, row + size, col, col + size)

            if any(_overlaps(window, rect) for rect in touched):
                continue

            nearby = sorted(
                {
                    edge
                    for r in range(row, row + size)
                    for c in range(col, col + size)
                    for edge in lattice.tile_edges.get((r, c), ())
                }
            )
            usable = [
                edge
                for edge in nearby
                if self.can_add(edge) and self.in_graph(edge[0]) and self.in_graph(edge[1])
            ]

            if usable:
                added = self.add_orbit(self.pick(usable))
            else:
                outside = sorted({node for edge in nearby for node in edge if not self.in_graph(node)})
                added = self._reactivate(outside)

            if added:
                touched += [lattice.rects[edge] for edge in added]
                changed = True

        return changed

    def _reactivate(self, candidates: list[Node]) -> list[Edge]:
        """Bring back a node that is out of the graph, with two edges so it is no dead end."""

        lattice = self.lattice

        for index in self.rng.permutation(len(candidates)):
            node = candidates[int(index)]
            links = [
                edge
                for edge in lattice.node_edges[node]
                if self.can_add(edge) and self.in_graph(lattice.other(edge, node))
            ]

            if len(links) >= 2:
                first, second = (links[int(i)] for i in self.rng.choice(len(links), 2, replace=False))
                return self.add_orbit(first) + self.add_orbit(second)

        return []

    def _repair_long_corridors(self, rule: Rule, violations: list[Violation]) -> bool:
        """Give each too-long corridor a junction near its middle."""

        lattice = self.lattice
        changed = False
        touched: set[Node] = set()
        perpendicular_only = isinstance(rule, MaxStraightRun)

        for index in self.rng.permutation(len(violations)):
            tiles = violations[int(index)].positions
            run_nodes = sorted({lattice.tile_node[t] for t in tiles if t in lattice.tile_node})

            if touched & set(run_nodes):
                continue

            # Inner nodes of the corridor have degree 2; the ends are junctions or dead ends.
            inner = [node for node in run_nodes if self.degree.get(node, 0) == 2]
            middle = np.mean(tiles, axis=0)
            inner.sort(
                key=lambda node: abs(lattice.rows[node[0]] - middle[0])
                + abs(lattice.cols[node[1]] - middle[1])
            )

            horizontal_run = len({row for row, _ in tiles}) == 1
            added: list[Edge] = []

            for node in inner:
                options = [
                    edge
                    for edge in lattice.node_edges[node]
                    if self.can_add(edge)
                    and self.in_graph(lattice.other(edge, node))
                    and not (perpendicular_only and lattice.is_horizontal(edge) == horizontal_run)
                ]

                if options:
                    added = self.add_orbit(self.pick(options))
                    break

            if not added:
                outside = sorted(
                    {
                        lattice.other(edge, node)
                        for node in inner
                        for edge in lattice.node_edges[node]
                        if not self.in_graph(lattice.other(edge, node))
                    }
                )
                added = self._reactivate(outside)

            if added or self._cut(tiles):
                touched |= set(run_nodes)
                changed = True

        return changed

    def _cut(self, tiles: tuple[Position, ...]) -> bool:
        """
        Remove one segment near the middle of a corridor, if the maze stays
        connected without it. The two stubs left behind are shorter corridors;
        max_dead_ends, if present, then closes or prunes them.
        """
        lattice = self.lattice
        tile_set = set(tiles)
        middle = np.mean(tiles, axis=0)

        segments = sorted(
            {edge for tile in tiles for edge in lattice.tile_edges.get(tile, ()) if edge in self.chosen}
        )
        # Only segments that lie on this corridor.
        segments = [
            edge
            for edge in segments
            if all((r, c) in tile_set for r, c in _rect_tiles(lattice.rects[edge]))
        ]
        segments.sort(
            key=lambda edge: float(
                np.abs(np.mean(_rect_tiles(lattice.rects[edge]), axis=0) - middle).sum()
            )
        )

        for edge in segments:
            self.remove_orbit(edge)

            if self._connected():
                self.banned.update(lattice.edge_orbit(edge))
                return True

            self.add_orbit(edge)

        return False

    def _connected(self) -> bool:
        """Every node with a corridor is reachable from every other."""

        graph = sorted(node for node, degree in self.degree.items() if degree > 0)
        reached = {graph[0]} if graph else set()
        frontier = deque(reached)

        while frontier:
            node = frontier.popleft()

            for edge in self.lattice.node_edges[node]:
                other = self.lattice.other(edge, node)

                if edge in self.chosen and other not in reached:
                    reached.add(other)
                    frontier.append(other)

        return len(reached) == len(graph)


def _repair_priority(rule: Rule) -> int:
    """Repairs that add corridors come before pruning dead ends, which removes them."""

    if isinstance(rule, MaxBlock):
        return 0
    if isinstance(rule, MaxStraightRun | MaxCorridorLength):
        return 1
    if isinstance(rule, MinLoops | MinJunctionShare | WalkableFraction):
        return 2
    if isinstance(rule, MaxDeadEnds):
        return 3
    return 4


def _rect_tiles(rect: Rect) -> list[Position]:
    r0, r1, c0, c1 = rect
    return [(row, col) for row in range(r0, r1) for col in range(c0, c1)]


def _overlaps(a: Rect, b: Rect) -> bool:
    return a[0] < b[1] and b[0] < a[1] and a[2] < b[3] and b[2] < a[3]


def _advice(rule: Rule, violations: list[Violation], params: LatticeParams) -> str:
    where = next((v.positions[0] for v in violations if v.positions), None)
    at = f" (e.g. at {where})" if where is not None else ""
    gap_min, gap_max = params.spacing

    if isinstance(rule, MaxBlock) and rule.tile == "wall":
        hint = (
            f"no corridor can cross these walls, usually near a curved or thin part of the "
            f"shape. Use a smaller topography.spacing max (now {gap_max}), a larger "
            f"size, or a larger max_block size"
        )
    elif isinstance(rule, MaxDeadEnds):
        hint = "the shape is too thin to close every dead end into a loop; use a wider shape or allow more dead ends"
    elif isinstance(rule, MaxStraightRun | MaxCorridorLength):
        hint = (
            f"no junction can be added along these corridors; use a smaller "
            f"topography.spacing (now {[gap_min, gap_max]}) or a larger length"
        )
    elif isinstance(rule, MinLoops | MinJunctionShare | WalkableFraction):
        hint = (
            "the lattice has no more segments to add; use a smaller topography.spacing "
            "or relax the rule (a maximum walkable fraction needs a larger spacing or "
            "fewer extra_loops)"
        )
    else:
        hint = "the lattice generator cannot repair this rule; change the shape or the rule"

    return f"{rule.describe()} cannot be met{at}: {hint}."
