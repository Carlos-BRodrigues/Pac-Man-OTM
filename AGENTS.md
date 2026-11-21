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

Common commands:

```powershell
python -m pacman_otm mazes                       # list mazes; --show NAME prints one
python -m pacman_otm simulate --controller nearest-pellet --visualize
python -m pacman_otm simulate --maze small --controller random-walk --seed 7 --output run.json --show-history
python -m pacman_otm play --maze small
python -m pacman_otm experiment --controller random-walk --runs 20 --seed 42
python -m pacman_otm replay run.json
python -m pytest                                  # needs: pip install -e ".[dev]"
```

`--maze NAME|PATH` (simulate, play, experiment) takes a registered name or a path to a `.txt` layout;
the default is `classic` everywhere. In `experiment`, `--seed` is the experiment seed: run i gets a
maze seed and a controller seed from `derive_run_seeds(seed, i)`, so different controllers run with
the same `--seed` see the same maze sequence.

`simulate` and `play` always save to `results/` (auto-named `<controller>_<maze>_<timestamp>.json`, or
`--output NAME`; `--no-save` to skip). `replay` also looks up bare names in `results/`.
Play controls: after a 2 s "READY!" hold, Pac-Man always moves (starting left); arrows/WASD change direction, and a turn pressed
early is taken at the next opening. Esc quits.

Replay controls: Space play/pause, ←/→ step, Home/End jump, ↑/↓ speed, Esc quit.

## Package map

| Path | Responsibility |
|---|---|
| `simulation/actions.py` | `Action` enum (UP/DOWN/LEFT/RIGHT). A leaf module; imports nothing internal. |
| `mazes/tiles.py` | `Tile` enum and `TILE_RULES` (walkable, pellet allowed). Tile values are stored in results: never renumber. Behaviour comes from the rules, never from `== 0`. |
| `mazes/maze.py` | `Maze`: immutable grid, start, pellets, `origin`; validates tiles, positions and pellet reachability; precomputed neighbour table (`MOVEMENTS` order). |
| `mazes/layout.py`, `mazes/layouts/*.txt` | Text layouts (`# . o space P _ H -`): `parse_layout`, `load_layout`, `format_layout`. Trailing spaces are tiles. |
| `mazes/origin.py`, `mazes/serialization.py` | `MazeOrigin` (how a maze was made: layout/generated, name, generator, params, seed); maze ↔ dict for results. |
| `mazes/registry.py` | Every `layouts/*.txt` as a named maze; `resolve_maze(name or path)`; `DEFAULT_MAZE`. |
| `experiments/seeding.py` | `derive_run_seeds(experiment_seed, run_index)` → independent maze and controller seeds. |
| `simulation/state.py` | `SimulationState`: position, remaining pellets, steps, termination. `copy()` / `to_dict()`. |
| `simulation/engine.py` | `SimulationEngine`: the game rules. Executes an action, updates state, records history. Decides nothing. |
| `algorithms/pathfinding/` | Pathfinders (`BreadthFirstSearch.find_path(maze, start, goal) -> list[Action] \| None`). Pure; no game decisions. |
| `controllers/controller.py` | `Controller`: `select_action(state) -> Action`, `reset()`, `describe()` (saved in results), optional `ControllerStatus`. `ControllerAborted(reason)` ends a run from inside a decision. |
| `controllers/algorithmic/` | Deterministic autonomous controllers (`AlgorithmicController`), e.g. `simple/nearest_pellet.py`. |
| `controllers/stochastic/` | `StochasticController` owns a seeded `self.rng`; `describe()` records the seed. E.g. `random_walk.py`. |
| `controllers/manual/` | `ManualController(action_source)`: a human player; the input source is injected (no UI imports). |
| `controllers/registry.py` | `create_controller_registry()`: every controller buildable from `(maze, seed)`; the CLI choices. |
| `simulation/runner.py` | `run_simulation`: the loop that asks the controller, steps the engine, emits frames, times decisions. |
| `simulation/result.py` | `SimulationResult`: the complete recorded run (states, actions, statuses, metrics, maze) + JSON I/O. |
| `simulation/replay.py`, `frame.py` | `ReplayPlayer` navigates a `SimulationResult` only. `SimulationFrame` = state + action + status. |
| `statistics_/` | `SimulationMetrics` (aggregate numbers) and `pretty_json`. |
| `experiments/runner.py` | Batch runs with seeds; writes per-run JSON plus `results.json` / `results.csv` aggregates. |
| `visualization/` | Pygame renderer, live visualizer (an `on_frame` callback), replay visualizer, `keyboard.py` (action source for `play`). Draws frames and reads input, no game rules. |
| `cli.py` | Argument parsing and wiring. No logic beyond assembling components. |

## Architectural rules (do not break these)

1. **The engine executes, it never decides.** No controller or strategy logic in `SimulationEngine`.
2. **Pathfinding is a tool, not a player.** BFS (and future A*, Dijkstra…) answers "shortest path from A to B".
   Choosing *which* B is the controller's job.
3. **Controllers are the players.** They receive state, choose a target, plan, and return one `Action`.
   They must not mutate the state they receive or reach into the engine.
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

**Add a maze**: drop a `.txt` layout in `mazes/layouts/`; it is registered under its file stem.
`Maze` validates tiles, the start, pellet placement and reachability for you. A new tile type needs a
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
- `NearestPelletController` runs one BFS per remaining pellet; a single BFS that stops at the nearest
  pellet would be far faster on the classic maze, but tie-breaking between equally near pellets must be
  kept identical (currently lowest `(row, col)`) or baseline results will change.
- The tunnel row in the classic maze has no wrap-around.
- Each saved state carries the full remaining-pellet set; storing per-step deltas would shrink files
  further but changes the result format.
- `src/test.py` is an old manual script; the real tests live in `tests/`.
