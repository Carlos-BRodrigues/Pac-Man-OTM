# Roadmap — Arbitrary and Generated Mazes

Status: steps 0–4 done (commit `32c1c1b`); step 5 done (`ea7ea19`); step 6 done (uncommitted).
Steps 7–10 below are the agreed design for recipes, experiments and sculpting. Revised 2026-11-23; replaces the earlier steps 5–7.
Added 2026-11-22: rule `max_corridor_length(length)` (step 5, done) and lattice params
`straightness` and `node_dropout` (step 6); details in the implementation plan.
Read `AGENTS.md` first; every rule there still applies.

**How to use this file (for Claude Code):** work on **one step per session**. For each step:
read the files involved, restate the plan in a few lines, wait for approval, implement,
then check every acceptance criterion and report. Do not start the next step unasked.
Do not commit, push or delete files unless asked.

---

## Goal

Mazes of any rectangular size within fixed bounds, any shape (void as padding), corridors of
any width. Mazes come from hand-written layouts, saved generated mazes, or **recipes**.
A recipe is a file naming a shape, a topography generator, a set of rules with parameters,
and content placers. The same recipe and seed always give the same maze. Experiments can
generate a fresh maze per run and record in each run file how it was made and what it measures.

## Decisions

| Topic | Decision |
|---|---|
| Generality | Generic first: any shape, any number of loops. Pac-Man-like is a recipe, not the default. |
| Hard rules for generated mazes | Size within bounds; one connected walkable region; enclosed: no walkable tile 8-adjacent to void or the grid edge, so every maze has wall borders. |
| Quality rules | Modular, optional, each with its own parameters, chosen per recipe. |
| Topography vs content | Independent. Rules see only tiles. Pellets, start (and later ghost spawns) are placed afterwards, from their own seed stream. |
| Size bounds | `MIN_MAZE_SIZE = 5`, `MAX_MAZE_SIZE = 101` for both rows and columns. Enforced by `Maze` for every maze. |
| How rules are met | By construction where possible, then targeted repair, then a final check. Not generate-and-test. |
| Corridor width | Any width; "one tile wide" is the rule `max_block(corridor, 2)`. |
| Void | Padding for non-rectangular mazes; never walkable; drawn as background. |
| Ghost house / ghosts | Decorative house (a reserved feature). Ghost spawns are a content placer, added later. No power pellets. |
| Tunnels | Later: portal pairs on `Maze`. Until then `classic` fails the `enclosed` check on its tunnel row, which is expected. |
| Recipe format | TOML (`tomllib`, standard library, read only) for hand-written recipes. JSON wherever recipes are saved into results. |

### Why "minimum corridor degree" is not a tile-level rule

At tile level, a minimum degree of 3 is impossible in any finite grid maze. The top-most,
left-most walkable tile can only have neighbours to the right and below, so it has at most 2.
Degree 2 everywhere is exactly "no dead ends". The intent ("enough choices") is covered by
three rules:

- `max_dead_ends(count)`: tiles with one neighbour; `count = 0` means none.
- `max_straight_run(length)`: longest corridor stretch with no junction; long runs offer no decisions.
- `min_junction_share(share)`: fraction of walkable tiles with 3 or more neighbours.

---

## Done

- **Step 0:** pytest, golden results, housekeeping.
- **Step 1:** `Tile` enum + `TILE_RULES`, renderer palette, decorative ghost tiles.
- **Step 2:** text layouts in `mazes/layouts/`, `parse_layout` / `load_layout` / `format_layout`.
- **Step 3:** immutable `Maze`, reachability validation, neighbour table, `MazeOrigin`, `format_version`.
- **Step 4:** maze registry, `--maze` on every command, `mazes` command, renderer scaling.
- **Step 5:** `grid.py`, `rules/` (hard, local, structure, registry), `analysis.py`, `Maze` size bounds,
  `maze.metrics` in results (`FORMAT_VERSION = 3`), `mazes list | show | check [--rules FILE]`.
- **Step 6:** `generation/shapes.py`, `generation/lattice.py` (with `straightness`, `node_dropout`).
  Decisions made while building it:
  - Hidden outer wall (touching no corridor, connected to the outside) becomes void, so the outline
    follows the corridors and unreachable shape edges don't fail `max_block(wall)`. Looks identical.
  - An overlong corridor with nowhere to branch is cut (if the maze stays connected); cut segments
    are never re-added, which keeps repairs from oscillating.
  - Mirrored both ways on small blobs, about 1% of seeds fail with a `GenerationError` naming the rule.
  - 101×101 with strict rules: about 0.25–0.4 s (worst seen 0.8 s); open rules about 0.15 s.
- Also in place: `experiments/seeding.py` (`derive_run_seeds`) and `ExperimentRunner(maze_factory=…)`.

---

## Target package layout

```
mazes/
  tiles.py  maze.py  origin.py  layout.py  serialization.py  registry.py   (exist)
  grid.py              # pure numpy helpers on a tile grid: windows, neighbour counts, masks
  analysis.py          # MazeMetrics: measurements of a maze (no thresholds)
  rules/
    base.py            # Rule, Violation, RuleSet, check()
    hard.py            # SizeBounds, Connected, Enclosed
    local.py           # MaxBlock, NoDiagonalContact
    structure.py       # MaxDeadEnds, MaxStraightRun, MinJunctionShare, MinLoops,
                       # WalkableFraction, MirrorSymmetric
    registry.py        # rule name -> rule class (built from recipe params)
  generation/
    shapes.py          # region masks: rectangle, ellipse, blob, layout
    lattice.py         # constructive topography generator
    sculpt.py          # constraint-preserving local search (step 9)
    content.py         # pellet and start placers (ghost spawns later)
    recipe.py          # MazeRecipe dataclass, TOML loading, --maze-set overrides
    pipeline.py        # build_maze(recipe, seed) -> Maze
    registry.py        # shape / generator / placer names -> implementations
  recipes/*.toml       # named recipes, auto-registered like layouts
  saved/*.json         # generated mazes kept by name, auto-registered
```

Rules and generators operate on the tile grid (`np.ndarray`), never on pellets or the start.

---

## Step 5 — Rule framework and measurements

**Why:** everything else (generation, repair, quality checks, experiment metrics) is built on
rules that can say *where* they fail.

- `mazes/grid.py`: helpers such as `walkable_mask(grid)`, `neighbour_counts(grid)` (4-neighbourhood),
  `windows(mask, size)` (all-true k×k windows via slicing), `components(mask)`.
- `rules/base.py`:

  ```python
  @dataclass(frozen=True)
  class Violation:
      rule: str
      message: str
      positions: tuple[Position, ...] = ()   # where; empty for global rules

  class Rule(ABC):
      name: ClassVar[str]

      @abstractmethod
      def violations(self, grid: np.ndarray) -> list[Violation]: ...

      def holds_after_change(self, grid: np.ndarray, position: Position) -> bool:
          """Incremental check after one tile changed. Default: full check.
          Local rules override this with an O(1) check of the neighbourhood."""
          return not self.violations(grid)
  ```

  Each rule is a frozen dataclass whose fields are its parameters, so it can be built from TOML and saved as JSON.
  `RuleSet` holds rules and returns all violations. `HARD_RULES` are always included for generated mazes.
- **Rules:**
  - Hard: `size_bounds`, `connected`, `enclosed`.
  - Local:
    - `max_block(tile, size)`: no size×size window of the same tile.
      `corridor, 2` gives one-tile corridors; `wall, k` keeps walls thinner than k.
    - `no_diagonal_contact`: no checkerboard 2×2 window, i.e. two walkable tiles touching only at a corner.
  - Structure: `max_dead_ends(count)`, `max_straight_run(length)`, `min_junction_share(share)`,
    `min_loops(count)`, `walkable_fraction(min, max)`, `mirror_symmetric(axis)`.
- `Maze` validation adds `size_bounds` (5–101). `small` and `classic` must still load.
- `analysis.py`: `analyze(maze) -> MazeMetrics` (frozen dataclass). Measures:
  - size, walkable count and fraction
  - regions
  - dead ends, junctions
  - loops (cycle rank = edges − walkable tiles + regions)
  - longest straight run
  - largest corridor block, largest wall block
  - enclosed, symmetry
  - pellet count
- Results: `maze_to_dict` adds `metrics`; bump `FORMAT_VERSION`.
- CLI: turn `mazes [--show NAME]` into subcommands (`mazes list`, `mazes show NAME`) and add
  `mazes check SPEC [--rules RECIPE]`, which prints metrics and violations with positions.

**Done when:**
- every rule has a passing and a failing tiny-layout test
- `mazes check classic` reports only the tunnel-row `enclosed` violation
- golden tests pass

## Step 6 — Shapes and the lattice generator (topography only)

**Why:** this generator meets most rules by construction instead of by luck.

1. **Region:** a shape fills an H×W boolean mask.
   - `rectangle`
   - `ellipse`
   - `blob` (seeded random connected shape; optional mirror)
   - `layout` (mask taken from a layout file's non-void tiles)

   The playable area is the mask shrunk by one tile (8-neighbourhood). The removed ring becomes `WALL`, everything outside becomes `VOID`.
   **`enclosed` holds by construction.**
2. **Lattice:** choose corridor row lines and column lines inside the playable area, with random gaps in `spacing = [min, max]` (min ≥ 2).
   Nodes are line intersections inside the playable area; candidate edges are line segments fully inside it.
   With gap ≥ 2 and width 1, **no corridor 2×2 and no diagonal contact hold by construction.**
   The maximum gap bounds wall thickness.
3. **Graph:**
   - Seeded random spanning tree over the largest connected candidate component → **`connected` by construction.**
   - Add a share `extra_loops` of the unused candidate edges.
   - Optional mirroring (build half, reflect).
4. **Repair driven by violations:**
   - For `max_dead_ends`, `max_block(wall, k)`, `max_straight_run` and `min_loops`:
     read the violation positions and add the nearest unused candidate edge, or remove a node on a run.
     Repeat until the rules hold or no repair move remains.
   - If repairs run out, raise an error that names the rule and suggests a parameter change.
     Example: "max_dead_ends=0 needs spacing ≤ … for this shape".
   - A quick feasibility check up front catches impossible combinations, such as a size too small for the spacing.
5. **Rasterize:** edges become corridor tiles of `corridor_width`. Everything else in the playable area is `WALL`.
6. **Final check:** `RuleSet.violations(grid)` must be empty. A failure here is a bug, not bad luck.

Programmatic API in this step (recipes come in step 7):

```python
grid = generate_lattice(shape=..., size=(31, 31), params=LatticeParams(...), rules=rule_set, rng=rng)
```

**Done when:**
- 200 seeds × three shapes × two rule sets pass the final check
- the same seed gives an identical grid
- a 101×101 maze generates in well under a second

## Step 7 — Recipes, content placement, pipeline, CLI

- **Content** (`generation/content.py`): placers take the finished grid and an rng.
  - Pellets: `all_corridors` (default), `density(p)`, `exclude_near_start(distance)`.
  - Start: `random`, `center` (walkable tile closest to the centre), `layout` (keep a layout's `P`).
  - Same interface later for ghost spawns.
  - Content never changes tiles.
- **Seeds:** the maze seed is split with `SeedSequence` into shape, topography and content streams.
  Changing the pellet placer never changes the topography, and changing the rules never changes the shape.
- **`MazeRecipe`** (`generation/recipe.py`): name, description, size, shape, generator + params, rules, content.
  - Loaded from TOML and validated with clear errors (unknown rule, bad parameter).
  - `apply_overrides(recipe, ["size=41x41", "topography.extra_loops=0.3", "rules.max_block.wall.size=3"])`
    applies `--maze-set` values.
- **Pipeline:** `build_maze(recipe, seed) -> Maze`: shape → topography → final rule check → content → `Maze`.
  `origin = MazeOrigin(source="generated", name=recipe.name, generator=…, params=<full resolved recipe>, seed=seed)`.
  The origin also records the package version, because a generator change may change what a seed produces.
  The saved topography keeps replay independent of that.
- **Registry and maze specs** (one resolver for every command):

  | Spec | Meaning |
  |---|---|
  | `classic` | layout in `mazes/layouts/` |
  | `open-lattice` | recipe in `mazes/recipes/` (needs `--maze-seed`, default 0) |
  | `my-favourite` | saved maze in `mazes/saved/` |
  | `path/to/file.txt` / `.toml` / `.json` | one-off layout / recipe / saved maze |

  Name clashes across the three folders are an error at registry build time.
- **CLI:**
  - `simulate / play / experiment --maze SPEC [--maze-seed N] [--maze-set KEY=VALUE ...]`
  - `mazes list` shows layouts, recipes and saved mazes, with kind and size.
  - `mazes show SPEC [--maze-seed N]` prints the layout and metrics.
  - `mazes check SPEC [--rules RECIPE]`
  - `mazes generate RECIPE --seed N [--count K] [--save NAME]` writes to `mazes/saved/`, which registers it.
  - `mazes preview SPEC [--maze-seed N]` opens a Pygame view; violations highlighted (optional).
- **Starter recipes:**
  - `open-lattice`: any shape, loops, no dead ends.
  - `wide-halls`: `corridor_width = 2`, no `max_block(corridor)`.
  - `blob-lattice`: random shape.
  - `classic-like`: symmetric, one-tile corridors, `max_block(wall, 5)`, decorative ghost house once step 10 exists.

Example recipe (`mazes/recipes/open-lattice.toml`):

```toml
name = "open-lattice"
description = "Generic loopy maze with no dead ends."

[size]
height = 31
width = 31

[shape]
kind = "rectangle"

[topography]
generator = "lattice"
spacing = [2, 4]
corridor_width = 1
extra_loops = 0.15
mirror = "none"          # none | horizontal | vertical | both

[[rules]]
rule = "max_dead_ends"
count = 0

[[rules]]
rule = "max_block"
tile = "corridor"
size = 2

[[rules]]
rule = "max_block"
tile = "wall"
size = 5

[[rules]]
rule = "no_diagonal_contact"

[content.pellets]
placer = "all_corridors"

[content.start]
placer = "center"
```

**Done when:**
- `simulate --maze open-lattice --maze-seed 7 --visualize` works and the saved result replays
- `mazes generate open-lattice --seed 7 --save demo` followed by `simulate --maze demo` uses the identical maze
- the same seed with a different pellet placer gives the same topography (test)
- bad recipes fail with messages that name the field

## Step 8 — Experiments with a maze per run

- `experiment --maze RECIPE` generates one maze per run from `derive_run_seeds(seed, i).maze_seed`
  (the hook already exists). `--maze-seed N` instead fixes one generated maze for all runs.
- Every run file holds the full maze, its origin (full recipe, seed, version) and its metrics.
- `results.json` stores the recipe once at experiment level. `results.csv` gains `maze_seed`
  and the main metric columns (walkable tiles, loops, dead ends, junction share, longest run).
- Fairness is unchanged: maze seeds depend only on the experiment seed and run index.

**Done when:**
- 20 runs give 20 different mazes
- rerunning reproduces them exactly
- two controllers with the same seed get identical maze sequences (test)
- any run file replays on its own

## Step 9 — Sculpt generator (organic shapes)

**Why:** lattice mazes look grid-like. Sculpt explores freely while **never leaving the space of valid mazes**.

- Start from a valid grid (lattice output, or the playable area opened to corridors).
- Repeatedly propose flipping one tile WALL↔CORRIDOR inside the playable area. Accept only if
  every rule's `holds_after_change` passes. Local rules check a 3×3 or 4×4 neighbourhood in O(1).
- **Connectivity stays local:**
  - CORRIDOR→WALL is allowed only if the tile's walkable neighbours remain connected within its 3×3 neighbourhood.
    This is a sufficient condition, so connectivity is never broken.
  - WALL→CORRIDOR is allowed only next to an existing corridor.
- Optional objective (targets for walkable fraction, loops, junction share) with simulated annealing.
  Without one, it is a seeded random walk over valid mazes.
- Global-only rules (`min_loops`, `mirror_symmetric`) are checked at the end, or kept by flipping mirrored pairs together.
- The same recipe format applies: `generator = "sculpt"`, with `start_from = "lattice"` and its params.

**Done when:**
- every accepted step keeps the full rule check passing (a debug flag checks after every step)
- 100 seeds pass
- the output looks clearly non-lattice

## Step 10 — Features for ghosts (when ghosts arrive)

- **Reserved features** are placed after the shape and before topography, as fixed regions the generator builds around:
  - decorative ghost house: a `GHOST_HOUSE` rectangle with a `GHOST_GATE` tile, a forced corridor ring around it
  - later, tunnel portal endpoints
- **Ghost spawn placer** in `content.py`:
  - walkable tiles outside the house
  - at least N BFS steps from the start
  - distinct tiles
  - seeded from the content stream; recorded in the run file

---

## Later

- Single-BFS nearest-pellet (about 4,000× faster on classic, identical results).
- Controller performance against maze metrics in experiment summaries.
- Maze pools: generate K mazes once, run every controller on all of them.
