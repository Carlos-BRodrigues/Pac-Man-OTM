# Roadmap — Arbitrary and Generated Mazes

Status: agreed design, ready for implementation. Written 2026-11-21.
Read `AGENTS.md` first; every rule there still applies.

**How to use this file (for Claude Code):** work on **one step per session**. For each step:
read the files involved, restate the plan in a few lines, wait for approval, implement,
then check every acceptance criterion and report. Do not start the next step unasked.
Do not commit, push or delete files unless asked.

---

## Goal

Mazes of any size and shape (non-rectangular via void), with corridors of any width,
loaded from hand-written layouts or generated from a seed. Generated mazes pass
quality rules (minimal or Pac-Man-like). An experiment can generate a fresh maze for
every run and record, in each run file, the maze itself, how it was made and its measured
properties.

## Decisions already made

| Topic | Decision |
|---|---|
| Maze generality | Generic first. Any shape, any number of loops. Pac-Man-like mazes are a stricter quality tier, not the default. |
| Corridor width | Any width is allowed by `Maze`. "One tile wide" is a quality rule, not a validation rule. |
| Void | Non-playable cells that pad a non-rectangular maze into a rectangle. Never walkable; drawn as background, not as wall. |
| Ghost house | Decorative only: non-walkable tiles drawn differently. No gate logic. |
| Ghost spawns | (Later, with ghosts.) Arbitrary seeded positions on walkable tiles, subject to spawn rules. |
| Power pellets | None. `o` in layouts is a normal pellet. |
| Tunnels | Later. Modelled as portal pairs (connections) on `Maze`, not as a tile type. Tile 5 stays reserved. |
| Tile numbers | Stable forever, because saved results store them. |

## Tile set

| Value | Tile | Pac-Man walkable | Pellet allowed | Drawn as |
|---|---|---|---|---|
| 0 | `CORRIDOR` | yes | yes | corridor |
| 1 | `WALL` | no | no | wall |
| 2 | `VOID` | no | no | background |
| 3 | `GHOST_HOUSE` | no | no | decoration |
| 4 | `GHOST_GATE` | no | no | decoration |
| 5 | reserved (`TUNNEL`) | — | — | — |

Behaviour comes from a rules table (`TILE_RULES[tile].pacman_walkable`, …), never from `== 0` checks.

---

## Step 0 — Safety net

**Why:** every following step claims "no behaviour change". This step makes that claim checkable.

- Add `pytest` as a dev dependency (optional dependency group in `pyproject.toml`), and `tests/`.
- Save golden results in `tests/golden/`:
  - `nearest-pellet` on small and classic
  - `random-walk` seed 7 on small
- Add a test that re-runs them and compares actions and states. Ignore the timing fields.
- Fix the housekeeping items from `AGENTS.md`: UTF-8 `requirements.txt` without the self-pin, and `egg-info` in `.gitignore`.

**Done when:** `pytest` passes, and the golden test fails if one action is changed by hand.

## Step 1 — Tile enum, rules table, renderer palette

- `mazes/tiles.py`: `Tile(IntEnum)`, a frozen `TileRules` dataclass, `TILE_RULES`.
- `Maze.is_walkable` and `_validate` use the rules table. Validation accepts exactly the defined tiles.
- Classic layout: `H` → `GHOST_HOUSE`, `-` → `GHOST_GATE`. Both were walls before, so they remain non-walkable.
- Renderer: a mapping from tile to colour. An unknown tile raises an error instead of being drawn as void.
  Void is drawn in the background colour.

**Done when:** golden tests pass unchanged, and the classic maze shows the ghost house distinctly.

## Step 2 — Text layouts

- `mazes/layout.py`: `parse_layout(text: str, name: str) -> Maze` with this legend:
  - `#` wall
  - `.` corridor with pellet
  - `o` corridor with pellet (no power pellets)
  - space: corridor without pellet
  - `P`: Pac-Man start (corridor, no pellet)
  - `_` void
  - `H` ghost house
  - `-` ghost gate
- Error messages must name the row, column and character. Exactly one `P` is required. All rows must have the same length.
- Move the small and classic mazes to `mazes/layouts/small.txt` and `classic.txt`, read with `pathlib` and `encoding="utf-8"`.
- `maps.py` factories become thin wrappers, or are replaced by the registry in Step 4.
- Remove the hard-coded 28×31 check.

**Done when:** parsed topography, start and pellets are identical to the current factories (add a test), and golden tests pass.

## Step 3 — Harden `Maze`

- **Immutability:** read-only numpy array (`flags.writeable = False`) and `frozenset` pellets.
- **Validation:**
  - rectangular grid
  - only known tiles
  - start and pellets on tiles that allow them
  - **every pellet reachable from the start**
- **Neighbour table** built once in `__init__`. `get_valid_movements` reads from it.
  This speeds up BFS; neighbour order must stay `Maze.MOVEMENTS` order.
- **`MazeOrigin`** frozen dataclass:
  - `source`: `"layout"` or `"generated"`
  - `name`
  - `generator`: `str | None`
  - `params`: `dict`
  - `seed`: `int | None`
  - stored as `maze.origin`
- **Result JSON:** `maze` gains `origin`. Old files without it still load, with origin `None`.
  Add a top-level `format_version` field.

**Done when:**
- golden tests pass
- a maze with an unreachable pellet is rejected with a clear message
- an old saved result still replays

## Step 4 — Maze registry and CLI

- `mazes/registry.py`: name → factory, mirroring the controller registry.
- CLI: `--maze NAME` for `simulate`, `play` and `experiment`, with the same default everywhere. This ends the small/classic mismatch.
- Renderer: choose `tile_size` so the window fits a maximum size, which keeps large mazes on screen.

**Done when:** `simulate --maze small` and `--maze classic` both work, and a 60×60 layout fits on screen.

## Step 5 — Maze analysis and quality rules

- `mazes/analysis.py`: `analyze(maze) -> MazeMetrics` (frozen dataclass). Measures:
  - walkable cells
  - walkable fraction
  - connected regions
  - dead ends (walkable cells with one neighbour)
  - junctions (three or more neighbours)
  - loops (cycle rank = walkable edges − walkable cells + regions)
  - open 2×2 blocks (counts wide areas)
  - maximum corridor width
  - enclosed (no walkable cell next to void or the grid edge)
  - mirror symmetry (left/right)
  - pellet count
- `mazes/quality.py`: `QualityRule` checks and named tiers. `check(maze, tier) -> list[str]` returns the reasons for failure; an empty list means it passes.
  - **`minimal`**:
    - 1 region
    - enclosed
    - loops ≥ 1
    - dead-end share of walkable cells ≤ 0.25
    - walkable fraction between 0.2 and 0.8
    - at least 3 junctions
  - **`pacman`**: everything in `minimal`, plus:
    - 0 dead ends
    - 0 open 2×2 blocks (corridors one tile wide)
    - mirror-symmetric
    - loops ≥ 10
  - All thresholds are starting values in one place, to be tuned later.
- Tests use tiny hand-written layouts: a tree maze fails `minimal`, the classic maze passes `pacman`, and an open room fails `pacman`.

**Done when:** the tests above pass. `simulate` saves the maze metrics in the result under `maze.metrics`.

## Step 6 — Generation framework and first generic generators

Generation is a pipeline. Each stage is a small function taking a seeded `numpy.random.Generator`:

1. **Shape mask.** Which cells of the H×W rectangle belong to the maze; everything else is void.
   Start with `rectangle` and `blob` (random connected shape, optional mirror).
2. **Carving.** Turn the masked area into walls and corridors. Two generators to start:
   - `braided`: a grid maze (recursive backtracker on a cell grid) followed by braiding,
     i.e. opening walls at dead ends with probability `braid` to create loops.
     The `corridor_width` parameter scales cells, which gives corridors of any width.
   - `cave`: random fill with density `p`, a few smoothing passes, then keep the largest region.
     This gives open, irregular areas.
3. **Border.** Wall cells surround the playable area, so the maze is enclosed.
4. **Placement.** Pellets on every walkable cell, and a seeded random start.
5. **Accept or retry.** Run the quality check for the requested tier. If it fails, retry with the same `rng`
   (deterministic), up to `max_attempts`. On failure, raise an error listing the most common reasons.

API sketch:

```python
@dataclass(frozen=True)
class GeneratorConfig:
    generator: str              # "braided" | "cave"
    height: int
    width: int
    shape: str = "rectangle"
    quality: str = "minimal"
    params: frozendict = frozendict()
    max_attempts: int = 200

def generate_maze(config: GeneratorConfig, seed: int) -> Maze: ...
```

- The same `(config, seed)` must always produce the same maze, on any machine.
- `maze.origin` records the generator, its parameters (the full config) and the seed.
- Add a `random` entry to the maze registry and CLI options: `--maze random --generator braided --size 31x28 --maze-seed 7 --quality minimal`.

**Done when:**
- determinism test passes (generate twice, compare)
- 100 seeds per generator all pass their tier, or fail with clear reasons
- generated mazes simulate and replay

## Step 7 — Experiments with a maze per run

- `ExperimentRunner` takes either a fixed maze or a `GeneratorConfig`.
- **Seed separation:** one experiment seed is split with `numpy.random.SeedSequence` into a maze seed
  and a controller seed for each run. Changing the controller seeds then never changes the mazes.
- **Fair comparison:** the maze seeds depend only on the experiment seed and the run index.
  Two controllers run with the same experiment seed see exactly the same mazes.
- Each run file stores the full maze, its `origin` (with the seed) and its `metrics`.
  `results.json` drops the single `map` block in favour of per-run maze data.
  `results.csv` gains the maze seed and the main maze metric columns.
- Option `--maze-per-run` (generated) versus a fixed `--maze NAME`.

**Done when:**
- `experiment --maze random --maze-per-run --runs 20` produces 20 different mazes
- rerunning with the same seed reproduces them exactly
- each run file replays on its own

---

## Later (not yet scheduled)

- **Pac-Man-like generator:** coarse grid scaled up, mirrored, fully braided, one-tile corridors, thick walls,
  and a decorative ghost house. Must pass the `pacman` tier.
- **Tunnels:** portal pairs on `Maze`, used by `get_destination` and `get_valid_movements`.
  BFS and controllers then get tunnels for free. Layout legend: matching letters on the edges.
- **Ghosts:** seeded spawn positions with rules:
  - on walkable tiles, outside the decorative house
  - at least N steps (BFS distance) from Pac-Man's start
  - no two ghosts on the same tile
  - recorded in the run file
- **Single-BFS nearest-pellet** (see `AGENTS.md` known points): about 4,000× faster on classic with identical results.
- **Analysis metrics in experiment aggregates**, e.g. controller performance against loop count.
