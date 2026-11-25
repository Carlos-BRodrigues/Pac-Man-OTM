# AGENTS.md — Pac-Man OTM

Guidance for AI coding agents (Claude Code, Claude, others) working in this repository.
Read this before changing anything.

## What this project is

A Python environment for **developing, comparing and optimizing algorithms that play Pac-Man**.
The game is the test bench, not the product. Clean separation between layers matters more
than clever algorithms, and every simulation must stay fully inspectable after the fact.

The owner develops interactively: **discuss the design, explain the reasoning, then implement
in small verified steps.** Do not jump straight to large changes.

## Environment

- Development happens in **VS Code on Windows**. Use `pathlib`, never hard-coded `/` or `\` paths.
  Always pass `encoding="utf-8"` when reading or writing text files.
- Python **>= 3.15** (the code uses the built-in `frozendict`). Dependencies: `numpy`, `pygame-ce`.
- Source layout: package lives in `src/pacman_otm`. Install for development with `pip install -e .`

Common commands (full reference: [docs/cli.md](docs/cli.md); recipes: [docs/recipes.md](docs/recipes.md)):

```powershell
python -m pacman_otm mazes list                                   # layouts, recipes, saved mazes
python -m pacman_otm mazes generate open-lattice --count 6        # gallery of random mazes
python -m pacman_otm mazes preview blob-lattice                   # one random maze in a window
python -m pacman_otm mazes save twisty my-twisty --maze-seed 4 --layout   # editable layout in mazes/layouts/
python -m pacman_otm simulate --maze twisty --visualize           # random maze, not saved
python -m pacman_otm simulate --maze open-lattice --maze-seed 7 --save
python -m pacman_otm play --maze small
python -m pacman_otm play --maze classic --ghosts 2                # Blinky x2 (classic has 1 by default)
python -m pacman_otm experiment --maze open-lattice --runs 20 --seed 42 --visualize
python -m pacman_otm experiment --maze my-mazes                   # a maze set: run i plays maze i
python -m pacman_otm replay results/nearest-pellet_open-lattice   # every run of an experiment
python -m pytest                                  # needs: pip install -e ".[dev]"
python -m pytest -m slow                          # long seed sweeps (skipped by default)
```

Behaviour worth knowing before changing the CLI:
- `--maze SPEC` is a layout, recipe or saved-maze name, or a `.txt`/`.toml`/`.json` path (default `classic`).
  A recipe without `--maze-seed` gets a random seed, printed and recorded in the result; a random seed whose
  build fails (`MazeGenerationFailed`) is replaced, up to 10 tries. A given seed is never replaced. `--maze-set KEY=VALUE`
  overrides recipe values. Recipe sizes may be ranges; the size is drawn from the maze seed.
- `--ghosts N` (every maze command): the number of ghosts, all Blinky. Default: the maze's own spawns (layout `G`/`g`,
  recipe `content.ghosts.count`; classic and the starter recipes have 1). A recipe re-places spawns from its ghost
  seed stream; a layout/saved maze keeps its spawns first and adds seeded ones. Tiles and pellets never change.
  `--ghosts 0` plays without ghosts. A ghost catching Pac-Man ends the run as `caught`.
- `--speeds arcade|equal` (simulate, play, experiment; default `arcade`): time runs in ticks. Arcade: ghosts at
  15/16 of Pac-Man, each pellet eaten costs him 2/16 of a tile. Equal: one tile per tick for everyone (the game
  before speeds; the golden `equal` cases pin it). `total_steps` counts ticks, `pacman_moves` tiles.
- `experiment`: `--seed` is the experiment seed; run i gets maze and controller seeds from
  `derive_run_seeds(seed, i)`, so controllers with the same `--seed` see the same mazes. A recipe without
  `--maze-seed` gives every run its own maze. `--visualize` shows runs live; closing the window stops the
  experiment (`stopped_early` in `results.json`). Experiments always save.
- `simulate` and `play` save only with `--save` (auto-named `<controller>_<maze>_<timestamp>.json` in `results/`)
  or `--output NAME`.
- `replay` takes a result file or an experiment folder (bare names are looked up in `results/`). Controls:
  Space play/pause, ←/→ step, Home/End jump, ↑/↓ speed, PageDown/`]` and PageUp/`[` next/previous run,
  A auto-advance, Esc quit. T/P toggle Pac-Man's target/path overlays, G the ghosts' (live views too).
- Play controls: after a 2 s "READY!" hold, Pac-Man always moves (starting left); arrows/WASD change direction,
  and a turn pressed early is taken at the next opening. Esc quits.
- `simulate`, `play`, `replay`, `experiment`, `mazes preview` and `sprites` take `--scale N`.

## Package map

| Path | Responsibility |
|---|---|
| `simulation/actions.py` | `Action` enum (UP/DOWN/LEFT/RIGHT). A leaf module; imports nothing internal. |
| `mazes/tiles.py` | `Tile` enum and `TILE_RULES` (walkable, pellet allowed). Tile values are stored in results: never renumber. Behaviour comes from the rules, never from `== 0`. |
| `mazes/maze.py` | `Maze`: immutable grid, start, pellets, ordered `ghost_spawns` (content like pellets: walkable, distinct, not the start), `origin`; validates tiles, positions and reachability; precomputed neighbour table (`MOVEMENTS` order). |
| `mazes/layout.py`, `mazes/layouts/*.txt` | Text layouts (`# . o space P _ H - G g`; `G`/`g` = ghost spawn without/with pellet, in reading order): `parse_layout`, `load_layout`, `format_layout`. Trailing spaces are tiles. |
| `mazes/grid.py` | Pure numpy helpers on a tile grid: masks, neighbour counts, k×k windows, components, straight runs, corridor chains. `MIN_MAZE_SIZE`/`MAX_MAZE_SIZE` (5–101). No `Maze` import. |
| `mazes/rules/` | `Rule` (frozen dataclass; fields = parameters), `Violation` (rule, message, positions), `RuleSet`. `hard.py` (`HARD_RULES`: size_bounds, connected, enclosed), `local.py` (max_block, min_wall_thickness, no_diagonal_contact), `structure.py` (dead ends, straight run, corridor length, junction share, loops, walkable fraction, mirror symmetry), `registry.py` (name → rule, built from TOML/JSON config with errors naming the field). Rules see tiles only. |
| `mazes/config.py` | `ConfigError`, `convert` and key checks for plain config values; errors name the field. |
| `mazes/generation/` | Topography generation. `shapes.py`: region masks (rectangle, ellipse, blob, layout), `playable_area`, `frame_grid`, `trim_outer_wall` (hidden outer wall → void). `lattice.py`: `LatticeParams` + `generate_lattice(region, params, rules, rng)`: lines → candidate graph → spanning tree (straightness bias, node dropout, mirror orbits) → repairs driven by violation positions → final full rule check. `grow.py`: `GrowParams` + `generate_grow`: organic mazes dug path by path from a ring or centre loop (rule-driven targets, clearance paths, bridges, restarts). `errors.py`: `GenerationError` (names the rule and a fix). `registry.py`: generator names. `content.py`: start placers (center, random, layout), pellet placers (clear_center (default: no pellets in a box centred on the grid), all_corridors, density, exclude_near_start) and the ghost placer (`random`: count, min_distance; `place_ghost_spawns` keeps fixed spawns first and is prefix-stable). `recipe.py`: `MazeRecipe`, `load_recipe` (TOML), `recipe_from_dict`, `apply_overrides` (`--maze-set`). `pipeline.py`: `build_maze(recipe, seed)` with separate seed streams for shape, topography, start, pellets, size and ghosts; `with_ghost_count(maze, n, seed)` for layouts and saved mazes; the origin records the full recipe, seed and package version. |
| `mazes/analysis.py` | `analyze(maze) -> MazeMetrics`: measurements only, no thresholds. Saved under `maze.metrics` in results; recomputed on load. |
| `mazes/origin.py`, `mazes/serialization.py` | `MazeOrigin` (how a maze was made: layout/generated, name, generator, params, seed); maze ↔ dict for results. |
| `mazes/recipes/*.toml` | Starter recipes (open-lattice, wide-halls, blob-lattice, classic-like, twisty, organic, grotto), registered by file stem. `mazes/saved/` is written by `mazes generate --save`. |
| `mazes/registry.py` | Layouts, recipes and saved mazes as named `MazeSource`s (`kind`, `build(seed)`); a name in two folders is an error. `resolve_maze_source(spec, overrides)`, `resolve_maze(spec, maze_seed, overrides)`, `save_maze` / `load_saved_maze`, `DEFAULT_MAZE`. |
| `mazes/sets.py`, `mazes/sets/*.toml` | Maze sets: fixed lists of layout/saved mazes (no recipes) for `experiment --maze SET`; run i plays maze i mod K. A set name may not also be a maze name. |
| `experiments/seeding.py` | `derive_run_seeds(experiment_seed, run_index)` → independent maze and controller seeds. |
| `simulation/state.py` | `SimulationState`: one tick. Pac-Man's tile, `pacman_heading` (move in progress, None at a centre) and `pacman_progress`, remaining pellets, `steps` (ticks), termination, `ghosts`, `move_cost`; `pacman_occupied`/`pacman_point`, `ghost_occupied(i)`/`ghost_point(i)`. `copy()` / `to_dict()`. |
| `simulation/ghosts.py`, `speeds.py` | `GhostState(kind, position, heading, next_heading, progress)` (frozen; `next_heading` = the exit committed one tile ahead) and `CAUGHT_REASON`. `SpeedRules(move_cost, pacman, ghost, pellet_pause)`, presets `ARCADE`/`EQUAL`, `occupied_tile` (destination once halfway), `mover_point`. Integer progress with carry: ratios exact, runs deterministic. |
| `simulation/engine.py` | `SimulationEngine(maze, ghosts=kinds, speeds=ARCADE)`: the game rules, in ticks. Movers are asked only at tile centres (`pacman_needs_decision`, `ghost_needs_decision`: at the spawn twice, then once per tile for the exit ahead); `decide_pacman`/`decide_ghost` record and check decisions (walls; ghosts never reverse except at a dead end); `advance()` moves everyone by speed, carries leftover progress, eats the pellet Pac-Man arrives on (pause), and ends the run as `caught` when a ghost occupies his tile or they swap occupied tiles (beats `completed`). `step()` = decide + advance, for tests. Decides nothing. |
| `algorithms/pathfinding/` | Pathfinders (`BreadthFirstSearch.find_path(maze, start, goal) -> list[Action] \| None`; `NoReverseSearch(maze).find_path(start, heading, goal)`: shortest path that never reverses except at dead ends, ties in `MOVEMENTS` order). Pure; no game decisions. |
| `algorithms/graph/` | `MetricClosure` (start + pellet distance matrix: `nodes`, `distances`) and `mst.py` (`mst_weight`, Prim: the tour lower bound). |
| `algorithms/tours/` | Pure tour algorithms on a distance matrix, open paths from node 0: `nearest_neighbour_tour`, `two_opt`, `held_karp_tour` (at most 16 pellets, `TourTooLargeError`), `tour_length`. No maze or game knowledge. |
| `controllers/algorithmic/tours/` | `TourController` (plans on the first decision, walks the tour with BFS, skips eaten pellets, reports `describe()["tour"]`); `held-karp`, `two-opt` (NN + 2-opt; lower bound, gap, improvement over NN), `nearest-pellet-tour` (online, closure-driven; lower bound and gap). |
| `controllers/controller.py` | `Controller`: `select_action(state) -> Action`, `reset()`, `describe()` (saved in results), optional `ControllerStatus`. `ControllerAborted(reason)` ends a run from inside a decision. |
| `controllers/algorithmic/` | Deterministic autonomous controllers (`AlgorithmicController`), e.g. `simple/nearest_pellet.py`. |
| `controllers/ghosts/` | `GhostController(maze, ghost_index)`: stateless; asked once per tile for the exit of the tile ahead (final: juking works), or a free first move at the spawn; publishes `GhostStatus` (target, path from its tile, decision, options, decided). Subclasses give `target(state)`: `Blinky` = Pac-Man's occupied tile. `registry.py`: `GHOST_KINDS`, `ghost_lineup(maze)` (one Blinky per spawn), `create_ghosts`. |
| `controllers/stochastic/` | `StochasticController` owns a seeded `self.rng`; `describe()` records the seed. E.g. `random_walk.py`. |
| `controllers/manual/` | `ManualController(action_source)`: a human player; the input source is injected (no UI imports). |
| `controllers/registry.py` | `create_controller_registry()`: every controller buildable from `(maze, seed)`; the CLI choices. |
| `simulation/runner.py` | `run_simulation(..., ghosts=controllers)`: per tick, asks Pac-Man's controller and each ghost only when due a decision, advances the engine, records the latest status of each (repeated while not asked), emits frames, times Pac-Man's decisions. `DEFAULT_MAX_STEPS = 3500` ticks. |
| `simulation/result.py`, `encoding.py` | `SimulationResult`: the complete recorded run (states, actions per tick or None, statuses, ghost statuses, ghost controllers, speeds, metrics, maze) + JSON I/O. Format 5 is compact on disk (per-mover arrival/heading strings and progress lists, eaten-pellet events, `=` for repeated statuses, `r,c:MOVES` paths) and rebuilds every state on load. |
| `simulation/replay.py`, `frame.py` | `ReplayPlayer` navigates a `SimulationResult` only. `SimulationFrame` = state + action + status. |
| `statistics_/` | `SimulationMetrics` (aggregate numbers) and `pretty_json`. |
| `experiments/runner.py` | Batch runs with seeds; writes per-run JSON plus `results.json` / `results.csv` aggregates. Each run record carries `maze_seed` (the seed that built its maze) and `maze_*` metric columns; `maze_info` (e.g. the recipe of per-run mazes) is written once under `experiment`. |
| `simulation/replay.py` `ResultSequence` | Runs to replay in order: one result file or an experiment folder (`runs/*/result.json`), loaded lazily. |
| `visualization/experiment.py`, `preview.py` | `ExperimentVisualizer` (the runner's `on_run_start`: a live visualizer per run, a new maze each time) and `run_maze_preview`. |
| `visualization/` | Pygame renderer, live visualizer (an `on_frame` callback), replay visualizer, `keyboard.py` (action source for `play`; buffers keys through the renderer's `key_listeners`, so a turn pressed between decisions is kept). Draws frames and reads input, no game rules. |
| `visualization/theme.py` | All colours and pixel geometry (8x8 base-pixel tiles, 13x13 sprites, wall recess). Change the look here. |
| `visualization/maze_art.py`, `sprites.py` | Maze background rendered once from masks (recessed, rounded outline walls); procedural player, death and ghost sprites (2-frame hem, eyes follow the heading) and spawn stickers. Original art: do not copy arcade sprites. |
| `visualization/animation.py` | Poses and tracks from recorded states only: movers drawn at tile + progress; between ticks along a track through the centre of any tile arrived on (`pacman_track`, `ghost_track`, `point_along`); chomp per in-between frame while moving, frozen when not; 5 in-between frames per tick, display only. Ghost hem frame from wall-clock time (`ghost_frame_at`). |
| `maze_commands.py`, `cli_types.py` | The `mazes` command family and the shared `--maze/--maze-seed/--maze-set` options; argparse types. |
| `cli.py` | Argument parsing and wiring. No logic beyond assembling components. |

## Architectural rules (do not break these)

1. **The engine executes, it never decides.** No controller or strategy logic in `SimulationEngine`.
2. **Pathfinding is a tool, not a player.** BFS (and future A*, Dijkstra…) answers "shortest path from A to B".
   Choosing *which* B is the controller's job.
3. **Controllers are the players.** They receive state, choose a target, plan, and return one `Action`.
   They must not mutate the state they receive or reach into the engine. Ghosts are controllers too.
4. **The runner coordinates; it does not absorb other layers' work.**
5. **History is first-class.** Every run keeps the full state, action and status history.
   Never replace history with aggregates only. Metrics complement history; they don't substitute for it.
6. **Replay is not live execution.** Replay reads a `SimulationResult`; it never calls a controller or engine.
   A saved JSON must be replayable on its own (it carries the maze).
7. **Recorded data is read through copies.** `get_state()` returns copies; frames and statuses are frozen
   dataclasses. Keep it that way so inspection can't corrupt history.
8. **Visualization consumes data only.** Renderers draw `SimulationFrame`s; no game rules in them.
9. **Reproducibility.** Any randomness goes through a seeded `numpy` `Generator` passed in at construction.
   Same maze + controller + seed must give the same run.
10. **Metrics must mean something.** Add a metric only when it answers a question about performance.

Dependency direction, lowest to highest — imports should only point downward:

`actions → mazes → state/engine → pathfinding → controllers → statistics → runner/result/replay → experiments, visualization → cli`

## Coding conventions (match the existing style)

- Type hints everywhere; modern syntax (`list[int]`, `X | None`). `Position = tuple[int, int]` alias.
- Small classes with one job; `@dataclass(frozen=True)` for snapshots and records.
- Descriptive names over abbreviations; validation with clear `ValueError` / `RuntimeError` messages.
- Multi-line calls use keyword arguments and trailing commas, as in the existing code.
- Comments explain *why*, not *what*. Docstrings on public classes and non-obvious methods.
- Prefer the standard library. Do not add frameworks or dependencies without discussing it first.
- No speculative abstractions: introduce an interface when a second implementation actually needs it.

## Common tasks

**Add a controller**
1. Subclass `AlgorithmicController` (deterministic) or `StochasticController` (uses `self.rng`) in
   `controllers/algorithmic/` or `controllers/stochastic/`; implement `select_action` and `reset`.
2. Accept `maze` (and `seed` for stochastic ones, passed to `super().__init__`) in `__init__`; call `reset()` there.
3. Publish intentions with `self._update_status(ControllerStatus(...))`, skipping expensive work when
   `self._status_collection_enabled` is false (see `NearestPelletController`).
4. Register it in `controllers/registry.py`. The CLI picks it up automatically.
5. Verify with `simulate --visualize`, then `experiment` against `nearest-pellet` as the baseline.

**Add a metric**: add the field to `SimulationMetrics`, compute it in `from_engine`, add it to the
experiment aggregates if numeric, and check old result JSON files still load (or say clearly that they won't).

**Add a maze**: drop a `.txt` layout in `mazes/layouts/` or a `.toml` recipe in `mazes/recipes/`; it is registered
under its file stem (see `recipes/open-lattice.toml` for every recipe section).
`Maze` validates tiles, size (5–101 rows and columns), the start, pellet placement and reachability for you;
`mazes check NAME` reports the hard rules and any extra `--rules`. A new tile type needs a
`Tile` value, a `TILE_RULES` entry, a layout character and a renderer colour.

**Change the result format**: bump `FORMAT_VERSION` in `simulation/result.py`. Old files are rejected
with a clear message; backward compatibility is not maintained at this stage.

**Tests**: `tests/golden/` holds fingerprints of reference runs. If they fail, behaviour changed; only
regenerate them (`python tests/make_golden.py`) when the change is intended, and say so.

## How to work

1. Read the relevant files before proposing changes; don't assume implementations.
2. For anything non-trivial, describe the design and the reasoning first and wait for agreement.
3. Make the smallest change that does the job. No drive-by refactors or reformatting of unrelated code.
4. Verify: run a simulation, an experiment and a replay that exercise the change.
   When tests exist, run them; when adding logic that is easy to get wrong, propose a test.
5. Summarize what changed and why, and flag any behaviour change to saved results.
6. Do not commit, push or delete files unless asked.

## Known open points (discuss before fixing)

- `statistics_/metrics.py` and `simulation/result.py` import `SimulationEngine`; metrics could instead be
  computed from a recorded history, keeping statistics independent of the live engine.
- The tunnel row in the classic maze has no wrap-around.
- No frightened/scatter modes or power pellets yet. Pac-Man turns only at tile centres (no mid-edge reversal), and
  after arriving with leftover progress he is drawn at the centre until his next decision.
- `src/test.py` is an old manual script; the real tests live in `tests/`.
