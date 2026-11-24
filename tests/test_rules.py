import numpy as np
import pytest

from pacman_otm.mazes.layout import LEGEND
from pacman_otm.mazes.registry import create_maze_registry
from pacman_otm.mazes.rules.base import RuleSet
from pacman_otm.mazes.rules.hard import HARD_RULES, Connected, Enclosed, SizeBounds
from pacman_otm.mazes.rules.local import MaxBlock, MinWallThickness, NoDiagonalContact
from pacman_otm.mazes.rules.registry import (
    RULES,
    RuleConfigError,
    rule_from_config,
    rules_from_toml,
)
from pacman_otm.mazes.rules.structure import (
    MaxCorridorLength,
    MaxDeadEnds,
    MaxStraightRun,
    MinJunctionShare,
    MinLoops,
    MirrorSymmetric,
    WalkableFraction,
)
from pacman_otm.mazes.tiles import Tile


def grid(text: str) -> np.ndarray:
    """Layout characters -> tile grid; rules ignore pellets and the start."""
    rows = text.strip("\n").split("\n")
    return np.array([[LEGEND[character][0] for character in row] for row in rows], dtype=np.uint8)


def failing_positions(rule, tiles: np.ndarray) -> set[tuple[int, int]]:
    return {position for violation in rule.violations(tiles) for position in violation.positions}


RING = grid("""
#####
#   #
# # #
#   #
#####
""")

OPEN_ROOM = grid("""
#####
#   #
#   #
#   #
#####
""")


def test_size_bounds() -> None:
    assert not SizeBounds().violations(RING)
    assert SizeBounds().violations(np.ones((4, 6), dtype=np.uint8))
    assert SizeBounds().violations(np.ones((5, 102), dtype=np.uint8))


def test_connected() -> None:
    assert not Connected().violations(RING)

    split = grid("""
#######
#   # #
#   # #
#######
#######
""")
    assert failing_positions(Connected(), split) == {(1, 5), (2, 5)}


def test_enclosed() -> None:
    assert not Enclosed().violations(RING)

    tiles = grid("""
_#####
##   #
#    #
#    #
######
""")
    assert not Enclosed().violations(tiles)

    # (1,1) touches the void at (0,0) only diagonally; (3,0) is on the grid edge.
    tiles[1, 1] = Tile.CORRIDOR
    tiles[3, 0] = Tile.CORRIDOR
    assert failing_positions(Enclosed(), tiles) == {(1, 1), (3, 0)}


def test_classic_fails_only_enclosed_on_the_tunnel_row() -> None:
    classic = create_maze_registry().create("classic")
    violations = HARD_RULES.violations(classic.topography)

    assert [violation.rule for violation in violations] == ["enclosed()"]
    assert violations[0].positions == ((14, 0), (14, 27))


def test_small_passes_the_hard_rules() -> None:
    assert HARD_RULES.holds(create_maze_registry().create("small").topography)


def test_max_block_corridor() -> None:
    rule = MaxBlock(tile="corridor", size=2)

    assert not rule.violations(RING)
    assert failing_positions(rule, OPEN_ROOM) == {(1, 1), (1, 2), (2, 1), (2, 2)}


def test_max_block_wall() -> None:
    rule = MaxBlock(tile="wall", size=3)
    thick = grid("""
#######
#     #
# ### #
# ### #
# ### #
#     #
#######
""")

    assert not rule.violations(RING)
    assert failing_positions(rule, thick) == {(2, 2)}
    assert not MaxBlock(tile="wall", size=4).violations(thick)


def test_max_block_rejects_bad_parameters() -> None:
    with pytest.raises(ValueError, match="size must be >= 2"):
        MaxBlock(tile="wall", size=1)

    with pytest.raises(ValueError, match="tile must be one of"):
        MaxBlock(tile="lava", size=2)


def test_no_diagonal_contact() -> None:
    rule = NoDiagonalContact()
    touching = grid("""
######
#  ###
#  # #
### ##
######
""")
    # (2,4) is a separate cell touching (3,3) diagonally; so is (2,2)-(3,3).
    assert not rule.violations(RING)
    assert failing_positions(rule, touching) == {(2, 2), (2, 3)}


@pytest.mark.parametrize(
    "rule",
    [MaxBlock(tile="corridor", size=2), MaxBlock(tile="wall", size=3), NoDiagonalContact()],
)
def test_local_rules_incremental_check_matches_full_check(rule) -> None:
    """A random walk of single flips that stays valid, as a sculpting generator would do."""

    rng = np.random.default_rng(0)
    # A lattice of one-tile corridors every other row and column: valid for all three rules.
    tiles = np.full((11, 11), Tile.WALL, dtype=np.uint8)
    tiles[1:-1:2, 1:-1] = Tile.CORRIDOR
    tiles[1:-1, 1:-1:2] = Tile.CORRIDOR
    assert not rule.violations(tiles)

    outcomes = set()

    for _ in range(2000):
        position = (int(rng.integers(11)), int(rng.integers(11)))
        previous = tiles[position]
        tiles[position] = Tile.WALL if previous == Tile.CORRIDOR else Tile.CORRIDOR

        holds = rule.holds_after_change(tiles, position)
        assert holds == (not rule.violations(tiles))
        outcomes.add(holds)

        if not holds:
            tiles[position] = previous

    assert outcomes == {True, False}


def test_max_dead_ends() -> None:
    stub = grid("""
######
#    #
# ## #
#    #
## ###
######
""")

    assert not MaxDeadEnds(count=0).violations(RING)
    assert failing_positions(MaxDeadEnds(count=0), stub) == {(4, 2)}
    assert not MaxDeadEnds(count=1).violations(stub)


def test_max_straight_run() -> None:
    hall = grid("""
#########
#       #
# ##### #
#       #
#########
""")
    # Each long side is 7 tiles from corner to corner; no junctions anywhere.
    assert not MaxStraightRun(length=7).violations(hall)
    assert failing_positions(MaxStraightRun(length=6), hall) == {
        (row, col) for row in (1, 3) for col in range(1, 8)
    }

    # A junction in the middle splits the top run into two runs of 4.
    hall[2, 4] = Tile.CORRIDOR
    assert not MaxStraightRun(length=4).violations(hall)


def test_max_corridor_length() -> None:
    ring = grid("""
#######
#     #
# ### #
#     #
#######
""")
    # A ring with no junction is one 12-tile choice-free corridor, turns included.
    assert failing_positions(MaxCorridorLength(length=11), ring) == {
        tuple(position) for position in np.argwhere(ring == Tile.CORRIDOR).tolist()
    }
    assert not MaxCorridorLength(length=12).violations(ring)

    # A cross-link makes junctions at (1,3) and (3,3): two 7-tile side corridors
    # (5 tiles plus both junctions) and a 3-tile middle one.
    ring[2, 3] = Tile.CORRIDOR
    assert not MaxCorridorLength(length=7).violations(ring)
    assert len(MaxCorridorLength(length=6).violations(ring)) == 2


def test_min_junction_share() -> None:
    assert MinJunctionShare(share=0.1).violations(RING)

    cross = RING.copy()
    cross[2, 2] = Tile.CORRIDOR  # the open room: 3x3, every edge tile has 3+ neighbours
    assert not MinJunctionShare(share=0.5).violations(cross)


def test_min_loops() -> None:
    assert not MinLoops(count=1).violations(RING)
    assert MinLoops(count=2).violations(RING)
    # A 3x3 open room has 12 edges over 9 tiles: 4 loops.
    assert not MinLoops(count=4).violations(OPEN_ROOM)


def test_walkable_fraction() -> None:
    # RING: 8 walkable of 25 tiles.
    assert not WalkableFraction(min=0.3, max=0.33).violations(RING)
    assert WalkableFraction(min=0.4).violations(RING)
    assert WalkableFraction(max=0.3).violations(RING)

    padded = RING.copy()
    padded[0, :] = Tile.VOID  # void is not maze area: 8 of 20
    assert not WalkableFraction(min=0.4, max=0.4).violations(padded)

    with pytest.raises(ValueError, match="must not exceed"):
        WalkableFraction(min=0.6, max=0.5)


def test_mirror_symmetric() -> None:
    lopsided = grid("""
######
#    #
# ####
#    #
######
""")

    for axis in ("horizontal", "vertical", "both"):
        assert not MirrorSymmetric(axis=axis).violations(RING)

    assert failing_positions(MirrorSymmetric(axis="horizontal"), lopsided) == {(2, 1), (2, 4)}
    assert not MirrorSymmetric(axis="vertical").violations(lopsided)
    assert MirrorSymmetric(axis="both").violations(lopsided)


def test_rule_set_collects_all_violations() -> None:
    rules = RuleSet([MaxBlock(tile="corridor", size=2), MinLoops(count=10)])

    assert [violation.rule for violation in rules.violations(OPEN_ROOM)] == [
        "max_block(tile=corridor, size=2)",
        "min_loops(count=10)",
    ]


def test_every_rule_round_trips_through_config() -> None:
    examples = {
        "max_block": {"tile": "wall", "size": 4},
        "max_dead_ends": {"count": 0},
        "max_straight_run": {"length": 9},
        "max_corridor_length": {"length": 12},
        "min_junction_share": {"share": 0.2},
        "min_loops": {"count": 3},
        "walkable_fraction": {"min": 0.3, "max": 0.6},
        "mirror_symmetric": {"axis": "both"},
        "min_wall_thickness": {"size": 2},
    }

    for name in RULES:
        rule = rule_from_config({"rule": name, **examples.get(name, {})})
        assert rule.name == name
        assert rule_from_config(rule.to_dict()) == rule


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"rule": "max_blok"}, r"rules\[1\]: unknown rule 'max_blok'"),
        ({"rule": "max_block", "tile": "wall"}, r"rules\[1\]\.size: missing"),
        ({"rule": "max_block", "tile": "wall", "size": 2.5}, r"rules\[1\]\.size: expected an integer"),
        ({"rule": "max_block", "tile": "lava", "size": 2}, r"rules\[1\]\.tile: expected one of"),
        ({"rule": "min_loops", "count": 1, "extra": 2}, r"unknown parameter\(s\) extra"),
        ({"rule": "max_dead_ends", "count": -1}, r"rules\[1\] \(max_dead_ends\): count must be >= 0"),
    ],
)
def test_bad_rule_configs_name_the_field(config, message: str) -> None:
    with pytest.raises(RuleConfigError, match=message):
        rule_from_config(config, where="rules[1]")


def test_rules_from_toml(tmp_path) -> None:
    path = tmp_path / "rules.toml"
    path.write_text(
        'name = "ignored"\n\n[[rules]]\nrule = "max_dead_ends"\ncount = 0\n\n'
        '[[rules]]\nrule = "walkable_fraction"\nmin = 0.25\n',
        encoding="utf-8",
    )

    assert list(rules_from_toml(path)) == [MaxDeadEnds(count=0), WalkableFraction(min=0.25)]


def test_min_wall_thickness() -> None:
    rule = MinWallThickness(size=2)

    # The arcade maze: every wall between corridors is at least two thick; its border
    # and ghost-house walls are one tile, which the rule allows.
    assert not rule.violations(create_maze_registry().create("classic").topography)

    thin = grid("""
#######
#     #
# ### #
#     #
#######
""")
    assert failing_positions(rule, thin) == {(2, 2), (2, 3), (2, 4)}

    thick = grid("""
########
#      #
# #### #
# #### #
#      #
########
""")
    assert not rule.violations(thick)
    assert failing_positions(MinWallThickness(size=3), thick) == {
        (row, col) for row in (2, 3) for col in range(2, 6)
    }

    # Next to void the border may be one tile thick.
    padded = grid("""
_______
_#####_
_#   #_
_#   #_
_#####_
_______
""")
    assert not rule.violations(padded)

    with pytest.raises(ValueError, match="size must be >= 2"):
        MinWallThickness(size=1)


@pytest.mark.parametrize("size", [2, 3])
def test_min_wall_thickness_incremental_check_matches_full_check(size: int) -> None:
    rule = MinWallThickness(size=size)
    rng = np.random.default_rng(1)
    step = size + 1
    # Corridors every `step` rows and columns: walls exactly `size` thick.
    tiles = np.full((3 * step + 2, 3 * step + 2), Tile.WALL, dtype=np.uint8)
    tiles[1:-1:step, 1:-1] = Tile.CORRIDOR
    tiles[1:-1, 1:-1:step] = Tile.CORRIDOR
    assert not rule.violations(tiles)

    outcomes = set()

    for _ in range(1500):
        position = (int(rng.integers(tiles.shape[0])), int(rng.integers(tiles.shape[1])))
        previous = tiles[position]
        tiles[position] = Tile.WALL if previous == Tile.CORRIDOR else Tile.CORRIDOR

        holds = rule.holds_after_change(tiles, position)
        assert holds == (not rule.violations(tiles))
        outcomes.add(holds)

        if not holds:
            tiles[position] = previous

    assert outcomes == {True, False}


@pytest.mark.parametrize(
    "rule",
    [MaxStraightRun(length=5), MaxCorridorLength(length=8), MirrorSymmetric(axis="horizontal")],
)
def test_structure_rules_incremental_check_matches_full_check(rule) -> None:
    rng = np.random.default_rng(3)
    # A lattice with corridors every other line: valid for all three (symmetric, runs <= 3 between junctions).
    tiles = np.full((11, 11), Tile.WALL, dtype=np.uint8)
    tiles[1:-1:2, 1:-1] = Tile.CORRIDOR
    tiles[1:-1, 1:-1:2] = Tile.CORRIDOR
    assert not rule.violations(tiles)

    outcomes = set()

    for _ in range(2000):
        position = (int(rng.integers(1, 10)), int(rng.integers(1, 10)))
        previous = tiles[position]
        tiles[position] = Tile.WALL if previous == Tile.CORRIDOR else Tile.CORRIDOR

        holds = rule.holds_after_change(tiles, position)
        assert holds == (not rule.violations(tiles)), (rule.describe(), position)
        outcomes.add(holds)

        if not holds:
            tiles[position] = previous

    assert outcomes == {True, False}
