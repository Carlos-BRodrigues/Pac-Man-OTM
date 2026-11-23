import time

import numpy as np
import pytest

from pacman_otm.mazes.generation.errors import GenerationError
from pacman_otm.mazes.generation.lattice import LatticeParams, generate_lattice, line_starts
from pacman_otm.mazes.generation.shapes import (
    playable_area,
    region_mask,
    trim_outer_wall,
)
from pacman_otm.mazes.grid import straight_runs, walkable_mask
from pacman_otm.mazes.registry import LAYOUTS_DIR
from pacman_otm.mazes.rules.base import RuleSet
from pacman_otm.mazes.rules.hard import HARD_RULES
from pacman_otm.mazes.rules.local import MaxBlock, MinWallThickness, NoDiagonalContact
from pacman_otm.mazes.rules.structure import (
    MaxCorridorLength,
    MaxDeadEnds,
    MaxStraightRun,
    MinLoops,
    MirrorSymmetric,
)
from pacman_otm.mazes.tiles import Tile

OPEN = RuleSet([MaxDeadEnds(count=0), MaxBlock(tile="corridor", size=2), NoDiagonalContact()])
STRICT = OPEN + RuleSet(
    [
        MaxBlock(tile="wall", size=5),
        MaxStraightRun(length=9),
        MaxCorridorLength(length=12),
        MinLoops(count=5),
    ]
)
SHAPES = ["rectangle", "ellipse", "blob"]


def generate(shape="rectangle", seed=0, size=31, params=LatticeParams(), rules=OPEN, **shape_params):
    rng = np.random.default_rng(seed)
    region = region_mask(shape, size, size, rng, **shape_params)
    return generate_lattice(region, params, rules, rng)


def sweep(seeds: range) -> None:
    for shape in SHAPES:
        for rules in (OPEN, STRICT):
            for seed in seeds:
                grid = generate(shape, seed, rules=rules)
                # generate_lattice already checks this; the test must not rely on it.
                assert (HARD_RULES + rules).holds(grid), (shape, seed)


def test_seeds_pass_the_final_check() -> None:
    sweep(range(20))


@pytest.mark.slow
def test_200_seeds_pass_the_final_check() -> None:
    sweep(range(200))


def test_same_seed_same_grid() -> None:
    for shape in SHAPES:
        first = generate(shape, seed=11, rules=STRICT)
        assert np.array_equal(first, generate(shape, seed=11, rules=STRICT))
        assert not np.array_equal(first, generate(shape, seed=12, rules=STRICT))


@pytest.mark.parametrize("mirror", ["horizontal", "vertical", "both"])
def test_mirroring(mirror: str) -> None:
    symmetric = RuleSet([MirrorSymmetric(axis=mirror)])
    failures = []

    # Mirroring both ways leaves a quarter of the choices, and on small blobs about
    # 1% of seeds run out of repair moves. That must stay rare and must fail with
    # an error naming the rule, never with a broken maze.
    for seed in range(30):
        for params, rules in (
            (LatticeParams(mirror=mirror), STRICT + symmetric),
            (LatticeParams(mirror=mirror, node_dropout=0.2), OPEN + symmetric),
        ):
            generate("rectangle", seed, params=params, rules=rules)

            try:
                generate("blob", seed, params=params, rules=rules, mirror=mirror)
            except GenerationError as error:
                assert "cannot be met" in str(error)
                failures.append(seed)

    assert len(failures) <= 2, failures


@pytest.mark.parametrize("size", [(31, 31), (30, 31), (31, 30), (30, 30)])
def test_mirroring_works_for_odd_and_even_sizes(size) -> None:
    rng = np.random.default_rng(3)
    region = region_mask("rectangle", *size, rng)
    rules = OPEN + RuleSet([MirrorSymmetric(axis="both")])

    generate_lattice(region, LatticeParams(mirror="both"), rules, rng)


def test_straightness_changes_texture() -> None:
    def mean_run(straightness: float) -> float:
        lengths = []
        params = LatticeParams(straightness=straightness, extra_loops=0.0)

        for seed in range(30):
            grid = generate(seed=seed, params=params, rules=[])
            lengths += [len(run) for run in straight_runs(walkable_mask(grid))]

        return float(np.mean(lengths))

    assert mean_run(1.0) > mean_run(0.0) > mean_run(-1.0)


def test_node_dropout_leaves_wall_islands() -> None:
    def mean_walkable(dropout: float) -> float:
        params = LatticeParams(node_dropout=dropout, extra_loops=0.0)
        return float(np.mean([walkable_mask(generate(seed=s, params=params)).sum() for s in range(20)]))

    assert mean_walkable(0.3) < mean_walkable(0.0)


def test_wide_corridors() -> None:
    params = LatticeParams(corridor_width=2, spacing=(3, 5))
    rules = RuleSet([NoDiagonalContact(), MaxBlock(tile="corridor", size=3)])

    for seed in range(10):
        grid = generate(seed=seed, params=params, rules=rules)
        assert MaxBlock(tile="corridor", size=2).violations(grid)


def test_outline_follows_the_corridors() -> None:
    for shape in SHAPES:
        grid = generate(shape, seed=5, rules=STRICT)

        # Corridors stay inside the shape's playable area, and hidden outer wall is gone.
        region = region_mask(shape, 31, 31, np.random.default_rng(5))
        assert not (walkable_mask(grid) & ~playable_area(region)).any()
        assert np.array_equal(trim_outer_wall(grid), grid)


@pytest.mark.parametrize("mirror", ["none", "horizontal", "vertical", "both"])
def test_blob_is_seeded_connected_and_mirrorable(mirror: str) -> None:
    from pacman_otm.mazes.grid import components
    from pacman_otm.mazes.rules.structure import mirror_flips

    for seed in range(20):
        blob = region_mask("blob", 41, 37, np.random.default_rng(seed), mirror=mirror)

        assert np.array_equal(blob, region_mask("blob", 41, 37, np.random.default_rng(seed), mirror=mirror))
        assert 0.3 < blob.mean() < 0.95

        if mirror == "none":
            assert components(blob)[1] == 1
        else:
            assert all(np.array_equal(blob, flipped) for flipped in mirror_flips(blob, mirror))


def test_ellipse_and_playable_area() -> None:
    ellipse = region_mask("ellipse", 21, 31, np.random.default_rng(0))

    assert np.array_equal(ellipse, ellipse[::-1, :]) and np.array_equal(ellipse, ellipse[:, ::-1])
    assert not ellipse[0, 0] and ellipse[10, 15]

    playable = playable_area(np.ones((7, 9), dtype=bool))
    assert playable.sum() == 5 * 7 and not playable[0].any() and not playable[:, -1].any()


def test_unknown_shape() -> None:
    with pytest.raises(GenerationError, match="Unknown shape 'star'; known shapes are rectangle"):
        region_mask("star", 21, 21, np.random.default_rng(0))


def test_layout_shape(tmp_path) -> None:
    rng = np.random.default_rng(0)
    region = region_mask("layout", 31, 28, rng, path=str(LAYOUTS_DIR / "classic.txt"))

    assert region.all()

    with pytest.raises(GenerationError, match="is 31x28, but the maze size is 31x31"):
        region_mask("layout", 31, 31, rng, path=str(LAYOUTS_DIR / "classic.txt"))


@pytest.mark.parametrize(
    ("params", "rules", "message"),
    [
        (LatticeParams(spacing=(2, 6)), [MaxBlock(tile="wall", size=4)], r"spacing max <= 4 \(now 6\)"),
        (LatticeParams(spacing=(2, 6)), [MaxStraightRun(length=6)], r"spacing max <= 5 \(now 6\)"),
        (
            LatticeParams(corridor_width=2, spacing=(3, 4)),
            [MaxBlock(tile="corridor", size=2)],
            "conflicts with corridor_width = 2",
        ),
        (LatticeParams(), [MirrorSymmetric(axis="vertical")], "needs topography.mirror = 'vertical'"),
        (LatticeParams(), [MinWallThickness(size=2)], r"spacing min >= 3 \(now 2\)"),
        (
            LatticeParams(corridor_width=2, spacing=(3, 5)),
            [MinWallThickness(size=2)],
            r"spacing min >= 4 \(now 3\)",
        ),
    ],
)
def test_infeasible_combinations_are_caught_up_front(params, rules, message: str) -> None:
    with pytest.raises(GenerationError, match=message):
        generate(params=params, rules=rules)


def test_mirroring_needs_a_symmetric_shape() -> None:
    with pytest.raises(GenerationError, match="horizontally symmetric"):
        generate("blob", seed=1, params=LatticeParams(mirror="horizontal"))


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"spacing": (1, 3)}, "spacing: min must be >= corridor_width \\+ 1 = 2"),
        ({"spacing": (4, 3)}, "max \\(3\\) is below min \\(4\\)"),
        ({"spacing": 3}, "expected \\[min, max\\]"),
        ({"straightness": 2.0}, "straightness must be between -1 and 1"),
        ({"node_dropout": 0.5}, "node_dropout must be in \\[0, 0.5\\)"),
        ({"mirror": "diagonal"}, "mirror must be one of"),
    ],
)
def test_bad_params_name_the_field(params, message: str) -> None:
    with pytest.raises(GenerationError, match=message):
        LatticeParams(**params)


def test_unrepairable_rule_names_the_rule() -> None:
    # More loops than the lattice has segments.
    with pytest.raises(GenerationError, match=r"min_loops\(count=10000\) cannot be met"):
        generate(rules=[MinLoops(count=10000)])


@pytest.mark.parametrize("mirrored", [False, True])
def test_line_starts_respect_spacing(mirrored: bool) -> None:
    rng = np.random.default_rng(0)

    for _ in range(200):
        low, high = 1, int(rng.integers(8, 99))
        starts = line_starts(low, high, 1, (2, 4), rng, mirrored)
        gaps = np.diff(starts)

        assert starts[0] >= low and starts[-1] <= high
        assert ((gaps >= 2) & (gaps <= 4)).all()

        if mirrored:
            assert starts == [low + high - s for s in reversed(starts)]


def test_101_by_101_is_fast() -> None:
    generate(size=101, rules=STRICT)  # warm-up: imports, caches

    for shape in SHAPES:
        start = time.perf_counter()
        generate(shape, seed=1, size=101, rules=STRICT)
        elapsed = time.perf_counter() - start

        # Typically 0.2-0.4 s; the bound only catches gross regressions.
        assert elapsed < 2.0, (shape, elapsed)


def test_generated_grid_contains_only_frame_and_corridor_tiles() -> None:
    grid = generate("blob", seed=2, rules=STRICT)

    assert set(np.unique(grid).tolist()) <= {Tile.CORRIDOR, Tile.WALL, Tile.VOID}


@pytest.mark.parametrize("shape", SHAPES)
def test_min_wall_thickness_holds_by_construction(shape: str) -> None:
    rules = OPEN + RuleSet([MinWallThickness(size=2), MaxBlock(tile="wall", size=5)])
    params = LatticeParams(spacing=(3, 5), node_dropout=0.15, extra_loops=0.15)

    for seed in range(20):
        grid = generate(shape, seed, params=params, rules=rules)
        assert not MinWallThickness(size=2).violations(grid)
