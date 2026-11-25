# Design brief — Movement speeds (ticks, progress, sub-tile motion)

Status: **implemented** on branch `speeds` (decisions: Pac-Man 1 tile per tick, reversal only at tile centres,
half-tile occupancy collisions, arcade speeds by default; ghosts keep their one-tile-ahead commitment in
`GhostState.next_heading`). Originally a proposal for discussion. Written 2026-11-24 against commit `4c914d8`
("Ghosts: Blinky, ghost spawns as maze content, compact result format 4").
Read `AGENTS.md` first; every architectural rule there still applies.

**How to use this file (for Claude Code):** this is a discussion document, not a work order.
1. Read the files listed under "Code involved" and check each claim in "Current situation" against the code.
2. Go through "Feasibility questions" and answer each one: confirm, reject, or propose an alternative, with
   reasons and file/line references. Flag anything this brief got wrong.
3. Answer or ask about the "Open decisions" before any code is written.
4. Only after the owner agrees, implement **one step of the plan per session**, verify it, and report.
Do not commit, push or delete files unless asked.

---

## Problem

One simulation step is currently three things at once:

1. one unit of game time (`SimulationState.steps`),
2. one tile of movement for **every** mover (Pac-Man and all ghosts), and
3. one animation cycle (`SUBFRAMES = 5` in-between frames gliding one tile).

So every mover has the same speed. Ghosts move exactly as fast as Pac-Man, and Pac-Man can never gain
distance on a chasing ghost. The arcade relationships we want (level 1):

| Mover | Arcade speed | Relative to Pac-Man |
|---|---|---|
| Pac-Man, empty corridor | 80% | 1.0 |
| Ghost | 75% | 0.9375 |
| Pac-Man eating dots | ~71% | ~0.8875 (about 11% slower) |

Net effect wanted: Pac-Man pulls away in cleared corridors and loses ground while eating.

## Current situation (verify these)

- `SimulationEngine.step(action, ghost_actions)` moves Pac-Man (blocked by walls) and every ghost one tile,
  increments `state.steps`, collects the pellet, then checks `caught` (same tile or head-on swap).
- `GhostState(kind, position, direction)` is frozen; `direction` is the move that brought it there.
- `run_simulation` asks Pac-Man's controller and then every ghost controller **every** step.
- `GhostController` assumes it moves on every call: `direction` = the committed move out of the current tile,
  `next_direction` = the exit out of the tile it moves onto, decided one step early (juking).
- `ManualController` keeps Pac-Man moving and buffers a requested turn until it is open.
- `visualization/animation.py` derives poses from recorded positions only. "No position change" means
  blocked, so the pose freezes. `PygameRenderer._glide` interpolates prev → current over `progress`.
- Result format 4 stores Pac-Man's actions and each ghost's moves as one letter **per step**
  (`encode_moves`); `_ghost_track` checks `len(moves) == steps`.
- `SimulationMetrics.total_steps = engine.state.steps`. `DEFAULT_MAX_STEPS = 3000`.

## Proposed design: whole tiles plus integer progress

Positions stay whole tiles, so pathfinding, tour controllers, the metric closure and ghost logic keep
working. Time becomes a **tick**. Each mover gets:

- `position`: the tile it is on (or leaving),
- `heading`: the move in progress, or `None` when stopped,
- `progress`: integer, `0 ≤ progress < MOVE_COST` (it can go negative during a pellet pause).

Per tick:

1. **Decide.** Only movers at a tile centre (stopped, or just arrived) are asked for an action.
   One decision = one tile, as now.
2. **Advance.** Each moving mover adds its speed to `progress`.
3. **Arrive.** When `progress >= MOVE_COST`: move one tile, `progress -= MOVE_COST`. The leftover carries,
   so fractional speeds average out exactly.
4. **Pellet pause.** Pac-Man arriving on a pellet loses `PELLET_PAUSE` progress, a short freeze (the arcade
   freezes him one frame per dot).
5. **Collisions.**

Speed rules as a frozen dataclass, e.g. `simulation/speeds.py`:

```python
@dataclass(frozen=True)
class SpeedRules:
    move_cost: int = 16
    pacman: int = 16       # 1.0 tile per tick
    ghost: int = 15        # 0.9375
    pellet_pause: int = 2  # dot corridors: 16 / 18 = 0.889
```

- Integer arithmetic only, so runs stay deterministic (rule 9) and there is no float drift.
- Speeds are game rules (like walls), so the engine owns them. That keeps rule 1 ("executes, never decides").
- The rules used in a run are saved in the result.
- Later speeds (frightened, tunnel, "Elroy") become more fields.

**Backward-compatibility anchor:** with `pellet_pause = 0` and `ghost = 16`, every run should be
**identical** to today's (Pac-Man decides at tick start, arrives at tick end, as one step does now).
That gives a regression test against the existing golden files.

### Layer by layer

| Layer | Change |
|---|---|
| `simulation/speeds.py` (new) | `SpeedRules`. |
| `simulation/ghosts.py`, `state.py` | `progress` on `GhostState`; heading + progress for Pac-Man (maybe a shared frozen `MoverState`). |
| `simulation/engine.py` | `SimulationEngine(maze, ghosts, speeds=SpeedRules())`. `step()` takes an action only for movers due a decision (`None` otherwise) and raises if that is violated. Exposes `needs_decision()`. |
| `simulation/runner.py` | Ask a controller only when its mover needs a decision; record `None` status on other ticks. |
| `controllers/ghosts/ghost.py` | Expected: **no change** (still called once per tile, so one-tile-ahead commits and juking stay). |
| Pac-Man controllers | Expected: no change (called once per tile). |
| `controllers/manual/` | Expected: no change (turn buffer already handles calls at tile centres only). |
| `visualization/` | Draw at `tile + heading × progress / move_cost`; interpolate between consecutive ticks. Smooth at any speed, live and replay, without knowing the future. Chomp freezes during the pellet pause. |
| `simulation/result.py`, `encoding.py` | Format 5: per-tick "no move" marker and progress (stored, or rebuilt from `SpeedRules`). |
| `statistics_/metrics.py` | `total_steps` means ticks (time); add `pacman_moves` (path length). |

### Collision

With different speeds, two movers can pass through each other mid-edge. Proposal: the arcade rule. A mover
occupies its destination tile once `progress >= move_cost / 2`, and "caught" = same occupied tile, plus the
existing swap check when both arrive in the same tick. Without this, a catch can be detected up to half a
tile late, with the sprites visibly overlapping.

### Effect on route optimisation

Ticks ≈ moves + pellets × `pellet_pause` / `move_cost`, and each pellet is eaten exactly once, so the pellet
term is roughly constant. The TSP objective (Held–Karp, 2-opt, MST bound) should be essentially unchanged.
**Check whether integer carry makes this "roughly" rather than "exactly", and by how much.**

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| **A. Progress model (proposed)** | Tile-based logic untouched; smooth visuals; exact arcade ratios; extensible | Touches engine, runner, state, result format, renderer |
| B. Skip a ghost move every 16th step (counter only, no visual model) | ~20 lines | Visible one-step stalls; pellet slowdown looks like a hiccup; controllers called on ticks they don't move unless runner also changes |
| C. True sub-tile positions (8 px per tile, as in the arcade) | Most faithful (cornering, mid-tile reversal) | Breaks tile-based controllers, pathfinding and collision; large redesign for a testbed whose purpose is optimisation |

## Feasibility questions (please answer each)

1. **Decision timing.** Is "ask only movers at a tile centre" compatible with every controller? In
   particular: does `TourController` or `NearestPelletController` use `state.steps` or assume one call per
   tick? Does `ControllerAborted` still work when Pac-Man is not asked on some ticks?
2. **Ghost memory.** Confirm `GhostController.direction / next_direction` stay correct when calls are spaced
   unevenly in ticks. Does the commit "using Pac-Man's position at that moment" still give fair juking when
   Pac-Man is at a different progress?
3. **Blocked Pac-Man.** Proposed: an action into a wall leaves him stopped, progress resets to 0 (no banking),
   and he is asked again next tick. Any interaction with `ManualController`'s "always moving" behaviour?
4. **Pellet pause semantics.** Pause on arrival (progress goes negative) vs. a higher move cost onto pellet
   tiles. The pause keeps decision timing independent of the chosen action. Is that right, and do pellets get
   collected on arrival or at the half-tile point?
5. **Order of a tick.** Decide → advance → arrive → pellet → collision. Any case where a ghost and Pac-Man
   arriving in the same tick gives a different outcome than today's rule ("caught beats completed")?
6. **History size and format.** States are recorded per tick; ticks grow ~12% in dot-heavy runs. Is storing
   progress per tick acceptable in format 5, or should progress be rebuilt on load from `SpeedRules`?
   Does rebuilding count as running game rules in replay (rule 6)?
7. **Statuses.** Per-tick `statuses` / `ghost_statuses` with `None` on non-decision ticks, or one entry per
   decision with a tick index? Which is simpler for replay overlays (T/P/G)?
8. **Live timing.** `LivePygameVisualizer` ticks at `fps × subframes`. Does one tick still map well to a
   display step, and do `SUBFRAMES` and the chomp loop need retuning?
9. **Metrics and experiments.** `total_steps` changes meaning. Which CSV columns and aggregates must be
   renamed or added (`pacman_moves`, `ticks`)? New `DEFAULT_MAX_STEPS`?
10. **Golden tests.** Can the existing golden runs be reproduced exactly with "compatibility" speed rules
    (`ghost = 16`, `pellet_pause = 0`) as a regression check before switching the defaults?
11. **Dependency direction.** `speeds.py` sits at the state/engine level; the renderer needs `move_cost` to
    draw progress. Is reading it from the result/frame fine, or should frames carry a 0–1 fraction?

## Open decisions for the owner

- **Tick vs. Pac-Man speed.** Pac-Man = 1 tile per tick (least disruption), or a tick faster than Pac-Man
  (e.g. `move_cost = 20`, Pac-Man 16, ghost 15) to leave headroom for ghosts faster than Pac-Man later?
- **Mid-tile reversal.** Only at tile centres for now (as today), or arcade-style anytime reversal
  (`progress = move_cost − progress`, heading flips)? It matters for escaping ghosts.
- **Collision rule.** Adopt the half-tile occupancy rule?
- **Defaults.** Switch the default to arcade speeds immediately, or keep compatibility speeds as default and
  enable arcade speeds with a CLI flag (e.g. `--speeds arcade`) first?

## Proposed step plan (one step per session, after agreement)

1. **Engine + runner:** `SpeedRules`, `progress`, `needs_decision()`, decisions only at tile centres,
   whole-tile collision. *Done when:* compatibility speeds reproduce every golden fingerprint exactly;
   with arcade speeds a test shows a ghost losing ground in an empty corridor and gaining in a dot corridor.
2. **Collision:** half-tile occupancy. *Done when:* tests cover passing mid-edge at different speeds,
   same-tick arrival, and "caught beats completed".
3. **Visualization:** draw from progress in live and replay; chomp freezes on pellet pauses.
   *Done when:* `play --maze classic` and a replay look smooth at both speeds.
4. **Result format 5 + metrics:** progress and no-move markers, `pacman_moves`, ticks, new max-steps default.
   *Done when:* a saved run replays on its own; old format-4 files are rejected with a clear message;
   golden files regenerated **on purpose**, and the change is stated.

After that, update `AGENTS.md` (package map, "Known open points": ghosts no longer at Pac-Man's speed) and
the roadmap.

## Code involved

`simulation/engine.py`, `state.py`, `ghosts.py`, `runner.py`, `frame.py`, `result.py`, `encoding.py`,
`replay.py`; `controllers/ghosts/ghost.py`, `controllers/manual/manual.py`,
`controllers/algorithmic/tours/tour_controller.py`, `controllers/algorithmic/simple/nearest_pellet.py`;
`visualization/animation.py`, `live.py`, `replay.py`, `pygame_renderer.py`; `statistics_/metrics.py`;
`experiments/runner.py`; `tests/test_ghosts.py`, `tests/test_golden.py`, `tests/golden/`.