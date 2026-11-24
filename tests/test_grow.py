import numpy as np
import pytest

from pacman_otm.mazes.generation.errors import GenerationError
from pacman_otm.mazes.generation.grow import GrowParams, generate_grow
from pacman_otm.mazes.generation.lattice import LatticeParams, generate_lattice
from pacman_otm.mazes.generation.shapes import region_mask
from pacman_otm.mazes.grid import straight_runs, walkable_mask
from pacman_otm.mazes.registry import create_maze_registry
from pacman_otm.mazes.rules.base import RuleSet
from pacman_otm.mazes.rules.hard import HARD_RULES
from pacman_otm.mazes.rules.local import MaxBlock, MinWallThickness, NoDiagonalContact
from pacman_otm.mazes.rules.structure import (
    MaxCorridorLength,
    MaxDeadEnds,
    MaxStraightRun,
    MirrorSymmetric,
)
from pacman_otm.mazes.tiles import Tile

ARCADE = RuleSet(
    [
        MaxDeadEnds(count=0),
        MaxBlock(tile="corridor", size=2),
        NoDiagonalContact(),
        MinWallThickness(size=2),
        MaxBlock(tile="wall", size=7),
    ]
)
RUNS = ARCADE + RuleSet([MaxStraightRun(length=9), MaxCorridorLength(length=16)])
SHAPES = ["rectangle", "ellipse", "blob"]


def grow(shape="rectangle", seed=0, size=31, params=GrowParams(), rules=ARCADE, **shape_params):
    rng = np.random.default_rng(seed)
    region = region_mask(shape, size, size, rng, **shape_params)
    return generate_grow(region, params, rules, rng)


def sweep(seeds: range, rules: RuleSet) -> None:
    for shape in SHAPES:
        for seed in seeds:
            grid = grow(shape, seed, rules=rules)
            assert (HARD_RULES + rules).holds(grid), (shape, seed)


def test_arcade_rules_hold_on_every_shape() -> None:
    sweep(range(15), ARCADE)


@pytest.mark.slow
def test_100_seeds_with_arcade_and_run_rules() -> None:
    # Rectangles and ellipses always succeed. On 31x31 blobs with these strict run rules,
    # about 1 seed in 12 has no room left for a rule and fails with a GenerationError
    # naming it (measured: 8 of 100 with 6 attempts).
    failures = 0

    for shape in SHAPES:
        for seed in range(100):
            try:
                grid = grow(shape, seed, rules=RUNS)
            except GenerationError as error:
                assert "cannot be met" in str(error) or "no room" in str(error)
                assert shape == "blob", (shape, seed, str(error))
                failures += 1
                continue

            assert (HARD_RULES + RUNS).holds(grid), (shape, seed)

    assert failures <= 15


def test_run_rules_are_met_on_rectangles() -> None:
    for seed in range(10):
        grid = grow(seed=seed, rules=RUNS)
        assert not MaxStraightRun(length=9).violations(grid)
        assert not MaxCorridorLength(length=16).violations(grid)


def test_same_seed_same_maze() -> None:
    for shape in SHAPES:
        assert np.array_equal(grow(shape, 4), grow(shape, 4))

    assert not np.array_equal(grow(seed=4), grow(seed=5))


@pytest.mark.parametrize("mirror", ["horizontal", "vertical", "both"])
def test_mirroring(mirror: str) -> None:
    rules = ARCADE + RuleSet([MirrorSymmetric(axis=mirror)])

    for seed in range(5):
        grid = grow(seed=seed, params=GrowParams(mirror=mirror), rules=rules)
        assert not MirrorSymmetric(axis=mirror).violations(grid)


def test_center_start_works_on_rectangles_too() -> None:
    grid = grow(seed=2, params=GrowParams(start="center"))
    assert (HARD_RULES + ARCADE).holds(grid)


def test_grown_mazes_are_not_lattices() -> None:
    """
    A lattice puts every corridor on a few row and column lines; grown corridors
    use many more of them. Counted: rows holding a horizontal run of 3 or more.
    """

    def busy_rows(grid: np.ndarray) -> int:
        runs = straight_runs(walkable_mask(grid), min_length=3)
        return len({run[0][0] for run in runs if len({row for row, _ in run}) == 1})

    lattice_rows, grown_rows = [], []

    for seed in range(10):
        rng = np.random.default_rng(seed)
        region = region_mask("rectangle", 31, 31, rng)
        lattice_rows.append(busy_rows(generate_lattice(region, LatticeParams(spacing=(3, 5)), ARCADE, rng)))
        grown_rows.append(busy_rows(grow(seed=seed)))

    assert np.mean(grown_rows) > 1.4 * np.mean(lattice_rows)


def test_turn_cost_changes_the_texture() -> None:
    def corner_share(turn_cost: float) -> float:
        shares = []

        for seed in range(8):
            walkable = walkable_mask(grow(seed=seed, params=GrowParams(turn_cost=turn_cost)))
            padded = np.pad(walkable, 1)
            up, down = padded[:-2, 1:-1], padded[2:, 1:-1]
            left, right = padded[1:-1, :-2], padded[1:-1, 2:]
            # As integers: numpy booleans add up as logical or.
            degree = up.astype(int) + down + left + right
            corners = walkable & (degree == 2) & ~((up & down) | (left & right))
            shares.append(corners.sum() / walkable.sum())

        return float(np.mean(shares))

    # Free turns give jogging paths; once turns cost about one step, paths turn as
    # little as the walls allow (measured: 11% corner tiles at 0, 7.5% from 1 up).
    assert corner_share(0.0) > 1.2 * corner_share(4.0)


def test_extra_paths_open_the_maze() -> None:
    plain = grow(seed=3)
    opened = grow(seed=3, params=GrowParams(extra_paths=6))

    assert walkable_mask(opened).sum() > walkable_mask(plain).sum()
    assert (HARD_RULES + ARCADE).holds(opened)


@pytest.mark.parametrize(
    ("params", "rules", "message"),
    [
        (GrowParams(), RuleSet([MinWallThickness(size=3), MaxBlock(tile="wall", size=6)]), "use a block size of at least 7"),
        (GrowParams(), RuleSet([MirrorSymmetric(axis="vertical")]), "needs topography.mirror = 'vertical'"),
    ],
)
def test_infeasible_combinations(params, rules, message: str) -> None:
    with pytest.raises(GenerationError, match=message):
        grow(params=params, rules=rules)


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"start": "middle"}, "start must be one of auto, ring, center"),
        ({"turn_cost": -1}, "turn_cost must be >= 0"),
        ({"max_wall_block": 2}, "max_wall_block must be >= 3"),
        ({"attempts": 0}, "attempts must be >= 1"),
    ],
)
def test_bad_params(params, message: str) -> None:
    with pytest.raises(GenerationError, match=message):
        GrowParams(**params)


def test_organic_recipe_builds() -> None:
    source = create_maze_registry().source("organic")
    rules = HARD_RULES + source.recipe().rule_set

    for seed in range(10):
        maze = source.build(seed)
        assert rules.holds(maze.topography)
        assert 25 <= maze.height <= 41 and 25 <= maze.width <= 41


def test_only_corridor_wall_and_void() -> None:
    assert set(np.unique(grow("blob", 1)).tolist()) <= {Tile.CORRIDOR, Tile.WALL, Tile.VOID}


@pytest.mark.parametrize("mirror", ["none", "horizontal", "vertical", "both"])
@pytest.mark.parametrize(("height", "width"), [(41, 51), (40, 50)])
def test_center_start_on_large_rectangles(mirror: str, height: int, width: int) -> None:
    """
    The start loop sits in the middle (not where a capped depth first peaks, near
    a corner), and with mirroring it is centred on the axes, so it is its own
    mirror image, also when the axis runs between two tile columns.
    """
    from pacman_otm.mazes.generation.grow import _Grower

    params = GrowParams(start="center", mirror=mirror)
    rules = ARCADE + (RuleSet([MirrorSymmetric(axis=mirror)]) if mirror != "none" else RuleSet([]))
    region = region_mask("rectangle", height, width, np.random.default_rng(0))

    start = walkable_mask(_Grower(region, params, rules, np.random.default_rng(0)).grid)
    rows, cols = np.nonzero(start)
    assert abs(rows.mean() - (height - 1) / 2) <= 1 and abs(cols.mean() - (width - 1) / 2) <= 1

    grid = generate_grow(region, params, rules, np.random.default_rng(1))
    assert (HARD_RULES + rules).holds(grid)


def test_grotto_recipe_builds() -> None:
    source = create_maze_registry().source("grotto")
    rules = HARD_RULES + source.recipe().rule_set

    for seed in range(3):
        maze = source.build(seed)
        assert rules.holds(maze.topography)
        assert not MirrorSymmetric(axis="horizontal").violations(maze.topography)
