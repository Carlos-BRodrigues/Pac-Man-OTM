# Design brief — Pinky, Inky, Clyde, the ghost house, the classic tunnel, ghost overlays and replay export

Status: **proposal for discussion, nothing implemented.** Written 2026-11-25 against branch `ghost-avoidance`
(`a2b0b48`); revised the same day with the owner's decisions. Read `AGENTS.md` first; every rule there applies.

**How to use this file (for Claude Code):**
1. Read the files under "Code involved" and check the claims in "Where we are" against the code.
2. Answer every question in "Questions to discuss", with file/line references, and flag anything this brief
   gets wrong.
3. **Discuss all steps together** with the owner: the full design, the order of the steps, and what each one
   changes. Implement only after the whole plan is agreed, then verify every "Done when" and report.
Do not commit, push or delete files unless asked.

---

## Decisions already made by the owner

| Topic | Decision |
|---|---|
| Movement | **All ghosts share the current steering** (shortest no-reverse path, one-tile-ahead commitment). The arcade's straight-line steering is **not** used. Kinds differ only in their target. |
| Targeting | Follow the original rules **as intended, without the overflow bug** (no extra left offset when Pac-Man faces up). |
| Inky without Blinky | **An error**, not a fallback. |
| Clyde | **Chases only when more than 8 tiles away** (Euclidean). At 8 tiles or closer he flees to the **bottom-left corner of the map he is on**. |
| Default lineup | **4 ghosts in total, one of each kind**: Blinky, Pinky, Inky, Clyde. |
| Per-ghost spawns | Optional per kind in a layout; unspecified or extra ghosts get random spawns as today. |
| Spawn for a kind not in the run | Tentatively: **used as a generic spawn** (owner unsure; see open decision 1). |
| Ghost house | Discuss feasibility (section 6): on `classic`, Pinky, Inky and Clyde start inside the house in the original arrangement, all active from the first tick; the gate is **one-way out**. |
| Tunnel | Implement the **classic map's tunnel** with proper visuals. No tunnel generation for random mazes. |
| Ghost overlays | **Every ghost** has target and path overlays in **its own colour**, and they stay **clean when ghosts' paths cross or overlap** (section 8). |
| Replay export | **Required:** `replay` can export a run from its result file as an **MP4 or GIF of the full run** (section 9). Claude Code proposes the best way to do it with the current data and pygame. |

## Targets

| Ghost | Target | Notes |
|---|---|---|
| Blinky | Pac-Man's occupied tile | Exists. |
| Pinky | 4 tiles ahead of Pac-Man, in the direction he faces | Facing up = 4 tiles up, nothing to the left. |
| Inky | P = 2 tiles ahead of Pac-Man; B = Blinky's occupied tile; target = P + (P − B) = **2P − B** | No up bug. Needs a Blinky in the run. |
| Clyde | Pac-Man's occupied tile if `dr² + dc² > 64`; otherwise his corner | Squared integers, exact. 8 tiles exactly → corner. |

Scatter corners for a later scatter mode (not part of this work): Blinky top-right, Pinky top-left, Inky
bottom-right, Clyde bottom-left. Each class defines its corner now; only Clyde uses it yet.

## Where we are (verify)

- `GhostController` (`controllers/ghosts/ghost.py`) holds all ghost movement: never reverses except at a dead
  end, commits the exit of the tile ahead one tile early (`GhostState.next_heading`), steers with
  `NoReverseSearch.find_path` to `target(state)`. Stateless between calls.
- `Blinky.target` returns `state.pacman_occupied`. `GHOST_KINDS` holds only Blinky.
- `ghost_lineup(maze)` = one Blinky per maze spawn; the CLI uses it in `create_engine_and_ghosts`.
- Spawns: layout `G`/`g` (without/with pellet) in reading order; `Maze.ghost_spawns` is ordered and ghost i starts
  on spawn i; `with_ghost_count` / `place_ghost_spawns` add seeded random spawns after the fixed ones
  (prefix-stable). Starter recipes have `content.ghosts.count = 1`.
- `SimulationState.pacman_heading` is `None` at tile centres, exactly when ghosts decide: **the state doesn't say
  which way Pac-Man faces.**
- `Tile.GHOST_HOUSE` and `Tile.GHOST_GATE` exist but are **decorative**: not walkable for anyone
  (`TILE_RULES`, `"Decorative only: no gate logic"`). Tile value 5 is reserved for `TUNNEL`.
- `classic.txt`: Blinky's spawn `G` sits above the gate (row 11, col 13); the gate `--` is row 12, cols 13–14;
  the house interior `HHHHHH` is rows 13–15, cols 11–16. Row 14 is the tunnel row: its walkable ends touch the
  grid edge at cols 0 and 27, with **no wrap-around** (a known open point in AGENTS.md; `mazes check classic`
  reports it as an `enclosed` violation).
- Movement uses one neighbour table for everyone: `Maze._neighbours`, `get_valid_movements`,
  `get_destination` (plain offset arithmetic, no wrap).
- Overlays (`visualization/pygame_renderer.py`): Pac-Man's target and path in `theme.target` / `theme.path`
  (green), toggled with T/P; ghost overlays (`_draw_ghost_overlays`, toggled with G) draw each ghost's remaining
  planned path through **tile centres** with `_draw_path_line`, plus a target marker, in
  `theme.ghost_overlay[kind]` (only `blinky` has a colour). Two ghosts in the same corridor draw lines **on top of
  each other**, and targets on the same tile hide each other.
- Rendering is tied to a window and wall-clock time: `PygameRenderer.__init__` calls `pygame.display.set_mode`,
  `_present` flips the display (drawing at the next whole scale and smoothly scaling down to fit the screen), the
  ghost hem frame comes from `pygame.time.get_ticks()` (`ghost_frame_at`), and the replay visualizer advances
  frames by elapsed milliseconds at its FPS. There is no offscreen or frame-by-frame rendering path yet.

---

## Design

### 1. Pac-Man's facing in the state

Add `pacman_facing: Action` to `SimulationState`: the last move Pac-Man started, initially `LEFT` (as `play` and
`INITIAL_FACING`), unchanged while blocked or paused. The engine sets it; controllers only read it. Ghost
controllers stay stateless.

### 2. Targets that are not walkable tiles

Pinky's, Inky's and Clyde's targets are often walls, void or **outside the grid**. Steering needs a reachable
tile, so:

- Pure helper, `nearest_walkable(maze, point) -> Position`: the **ghost-walkable** tile with the smallest
  squared Euclidean distance to any integer point (on or off the grid), ties in reading order. Cached per point.
- Targets are computed raw, then projected. `GhostStatus` carries both the **raw target** and the
  **projected tile**, so the G overlay shows why a ghost goes where it goes.
- Clyde's corner: `nearest_walkable(maze, (rows − 1, 0))`, once per maze, so it follows non-rectangular shapes.
  Targets ignore the tunnel (straight-line geometry, as in the original).

### 3. The ghost classes

In `controllers/ghosts/`, each implementing only `target(state)` (plus a `scatter_corner` constant). Offsets come
from `Maze.MOVEMENTS[state.pacman_facing]`.

- **Pinky:** `pac + 4·facing`.
- **Inky:** `P = pac + 2·facing`; `B` = the occupied tile of the **first `blinky` in `state.ghosts`**, read from
  the state (never from Blinky's controller: rule 3); target `2P − B`.
  - The lineup is validated where it is built: `inky` without `blinky` raises `ValueError` with the fix in the
    message (`--ghost-kinds`, or add a Blinky). A second check at decision time raises `RuntimeError` (a bug).
- **Clyde:** `d² = (clyde_r − pac_r)² + (clyde_c − pac_c)²` between occupied tiles; `d² > 64` → Pac-Man's tile,
  else his corner.
- Colours per kind in `visualization/theme.py` (original procedural art, as now).

### 4. Lineup: 4 ghosts by default, and explicit kinds

- Default: **4 ghosts, Blinky, Pinky, Inky, Clyde.** For `--ghosts N` the lineup cycles in that order
  (N = 2 → Blinky, Pinky; N = 5 → a second Blinky).
- New `--ghost-kinds blinky,pinky,...` (simulate, play, experiment) sets the kinds exactly; its length is N
  (error if it contradicts `--ghosts`). Validates unknown kinds and Inky without Blinky.
- Golden tests and the ghost-avoidance benchmark (`design-ghost-avoidance.md`) assume all-Blinky lineups: pin them
  with explicit kinds so their numbers don't move.
- Results and experiment records name the lineup.

### 5. Per-ghost spawns in layouts

New layout letters, following `G`/`g` (upper case: no pellet; lower case: with pellet):

| Letters | Spawn for |
|---|---|
| `B` / `b` | Blinky |
| `K` / `k` | Pinky (`P` is Pac-Man) |
| `I` / `i` | Inky |
| `C` / `c` | Clyde |
| `G` / `g` | any ghost (as today) |

- `Maze` records a kind (or `None`) per spawn as plain strings; `mazes/` never imports the ghost registry.
  Serialization adds the kinds; saved mazes without them still load (all `None`). `format_layout` writes the
  letters back.
- **Assignment** of spawns to the lineup, deterministic, in reading order:
  1. each ghost takes the first unused spawn marked with **its own kind**;
  2. ghosts still without one take unused **generic** spawns: `G`/`g`, and (tentatively) spawns marked for a kind
     that is **not in this run**;
  3. any left get **seeded random** spawns (`place_ghost_spawns` with every layout spawn as `fixed`, so random
     ones never land on them and stay prefix-stable).
- The result is a maze whose `ghost_spawns` are ordered to match the lineup (as `with_ghost_count` does now), so
  the engine keeps pairing ghost i with spawn i.
- Random spawns are always on corridor tiles, never in the house.

### 6. The ghost house (feasibility to discuss)

**Goal:** on `classic`, Blinky starts above the gate and Pinky, Inky and Clyde start **inside** the house, in the
original arrangement (Inky left, Pinky centre, Clyde right). All are active from the first tick: no release
timers or dot counters. The gate is **one-way**: ghosts can leave the house but never come back in. Pac-Man can
never enter the house or the gate.

**What changes: two movement graphs.** Today one neighbour table serves every mover. With a house, ghosts and
Pac-Man walk different graphs:

- **Pac-Man:** corridors only (unchanged). BFS, the metric closure, tours and pellets are unaffected.
- **Ghosts:** corridors plus house and gate tiles, with **directed** edges at the gate:
  - allowed: house → house, house → gate, gate → corridor (and gate → gate sideways, if the gate is two wide: to
    discuss);
  - forbidden: corridor → gate, gate → house, corridor → house.

  Because the house is enclosed by walls and the gate, these rules come from tile types alone (no direction
  metadata). Once a ghost steps onto the gate it can only go out, and once out it can't come back.
- `Maze` exposes the ghost graph next to Pac-Man's (e.g. `ghost_moves(position)` in `MOVEMENTS` order), built once
  in its constructor. `TILE_RULES` gains a `ghost_walkable` flag (house and gate true, Pac-Man false), plus the
  gate direction rule.
- **Everything ghost-side must use the ghost graph:** `NoReverseSearch` (built for ghosts), the engine's ghost
  decision check (`decide_ghost`), `nearest_walkable` for ghost targets, and the avoidance controllers' ghost
  distances (`two-opt-avoid`, and the `two-opt-safe` work): a ghost still inside the house reaches the corridor
  through the gate.
- The house is an open block (6×3 on `classic`). The no-reverse rule and `NoReverseSearch` work on any graph, so a
  ghost at its spawn takes a free first move and its shortest path to any outside target goes through the gate.
- Collisions are unchanged: Pac-Man can't be in the house, so no catches happen there.
- `Maze` validation: spawns must be ghost-walkable and reach the corridors through the ghost graph; pellets are
  never allowed in the house or gate (already the case); every gate tile must border the house on one side and a
  corridor on the other.
- Rules and analysis keep seeing tiles. Generated mazes have no house, so nothing changes for them (a recipe house
  stays a later, separate feature).
- Visuals: ghosts are drawn inside the house; the gate is drawn as a door. `maze_art` already draws the house
  tiles; check it looks right with ghosts on them.
- Later, not now: eaten ghosts returning home (would need the gate inward for "eyes"), release timers, ghosts
  bobbing in the house.

**The layout problem: spawns on house tiles.** Spawn letters currently mean "corridor tile". Inside the house the
tile is `GHOST_HOUSE`. Options:

- **(a, proposed)** A spawn letter becomes a house tile when it is 4-adjacent to an `H` tile or to another spawn
  letter that is one. Since the house is enclosed by walls and the gate, a corridor tile can never touch an `H`,
  so this is unambiguous. No new characters; house spawns use upper-case letters (no pellets in the house; a
  lower-case letter there is an error).
- (b) A footer section in the `.txt` listing spawns by coordinates (`[spawns] pinky = 14,13`). Keeps the grid pure
  tiles, but coordinates are error-prone to edit by hand.
- (c) Separate letters for house spawns (runs out of letters fast).

`classic.txt` around the house, with (a):

```
######.##    B     ##.######    row 11: Blinky above the gate
######.## ###--### ##.######    row 12: gate (cols 13-14)
######.## #HHHHHH# ##.######    row 13
      .   #HIKHCH#   .          row 14: Inky (12), Pinky (13), Clyde (15); also the tunnel row
######.## #HHHHHH# ##.######    row 15
```

The exact columns are open (the original's centre falls between the two gate columns); keep the arrangement
Inky left, Pinky centre, Clyde right.

### 7. The classic tunnel

**Goal:** on `classic`, row 14 wraps: moving left from col 0 arrives at col 27 and vice versa, for Pac-Man and
ghosts, with sprites that slide out of one side and in at the other. No tunnels in generated mazes, and no
tunnel slowdown for ghosts (the original has one; possible later).

**Proposed model: portal edges on `Maze`.**

- **Which tiles:** automatic and simple. A walkable tile on the grid edge whose tile on the **opposite edge, same
  row** (or same column) is also walkable forms a portal pair. That gives `classic` its tunnel with no layout
  change. Generated mazes satisfy `enclosed` (no walkable tile on the edge), so they never get portals.
  Alternative to weigh: an explicit tunnel character (tile value 5 is reserved for `TUNNEL`).
- **Graph:** the portal move is an ordinary edge in both neighbour tables (Pac-Man's and the ghosts').
  `get_destination` wraps for portal moves. All graph-based code (BFS, metric closure, `NoReverseSearch`, tours,
  avoidance) then sees the tunnel for free. Check every place that does its own offset arithmetic instead of
  using the neighbour table.
- **Progress and occupancy:** `occupied_tile` and `mover_point` (`simulation/speeds.py`) add the heading's offset
  without knowing the maze. Across a portal, the occupied tile must wrap, and the drawn point runs off the edge
  (col −0.5) before reappearing at the other side. They need the maze (or the grid width) to wrap.
- **Collisions:** unchanged once occupied tiles wrap (same tile, or swap).
- **Result encoding:** `encode_path` stores adjacent steps as move letters and falls back to a position list for
  non-adjacent steps, so a wrap step is still lossless. Check decoding of tracks and paths (`decode_path` adds
  offsets) and whether a maze-aware encoding is wanted.
- **Visuals ("proper"):** the sprite is drawn partly at both edges while crossing, clipped to the maze area, as in
  the arcade where the tunnel mouths hide the sprite. The renderer's tracks (`pacman_track`, `ghost_track`,
  `point_along` in `animation.py`) must not interpolate across the whole maze during a wrap. The maze outline in
  `maze_art` should leave the tunnel mouths open.
- **Rules:** `enclosed` stops reporting the tunnel row once portal tiles are exempt, so `mazes check classic`
  becomes clean (update the test that expects that violation).
- **Targets** (Pinky, Inky, Clyde) ignore the tunnel: straight-line geometry, as in the original.

### 8. Ghost overlays: one colour per ghost, clean when they cross

**Goal:** with G on, every ghost shows its path and target in its own colour. With four ghosts (often in the same
corridors, often chasing the same tile) the picture must still read clearly: no line hidden under another, no
target marker hiding another.

Proposals to discuss:

- **Colours:** add `ghost_body` and `ghost_overlay` colours for `pinky`, `inky` and `clyde` in `theme.py`. Overlay
  colours must be distinct from each other, from Pac-Man's green path and from the walls, and readable on the
  dark background. Original palette choices, not copied arcade sprites.
- **Lanes for paths:** each ghost kind gets a fixed small **perpendicular offset** ("lane") from the tile centre,
  e.g. −1.5, −0.5, +0.5, +1.5 base pixels for Blinky, Pinky, Inky, Clyde (scaled with `--scale`). Where paths share
  a corridor the lines run side by side instead of on top of each other; at corners the offset turns with the
  path. Pac-Man's own path stays centred. A thin dark outline under each line keeps it readable where lines cross.
- **Draw order:** fixed (e.g. paths first, in ghost order, then targets, then sprites), so overlaps look the same
  every frame and in every replay.
- **Targets:** a marker per kind that stays distinguishable when several share a tile: different corner or
  quadrant of the tile per kind, or different shapes (cross, ring, square, diamond). With the raw target from
  section 2, show the **projected tile** as the marker, and the **raw target** as a small dot joined to it by a thin
  line (clipped to the window edge when the raw target is off the grid).
- **Ghosts in the house** (section 6) and **paths through the tunnel** (section 7): a path that wraps is drawn as
  two segments, never a line across the whole maze.
- Avoid alpha blending as the main tool: overlapping translucent lines turn into muddy mixed colours. Lanes plus
  outlines should be enough.
- The HUD keeps showing T/P/G state; consider a small legend (colour per ghost) when G is on.

### 9. Export a replay as MP4 or GIF (required)

**Goal:** `replay RESULT --export out.mp4` (or `out.gif`) writes a video of the **full run**, exactly as the replay
window would show it, from the result file alone (rule 6: no controller or engine, only the recorded
`SimulationResult`). For an experiment folder, export one file per run (or only `--run N`).

What the export must contain: the READY hold (if replay shows one), every tick with its in-between frames,
overlays according to flags, the death sequence or the end banner, and a short hold on the final frame.

**Rendering offscreen, frame by frame.** The pieces exist (`ReplayPlayer`, the renderer's `draw`, the animation
helpers), but they assume a window and wall-clock time. Needed:

- A renderer that can draw onto an **offscreen `pygame.Surface`** without opening a window (e.g. a "headless"
  flag, or `SDL_VIDEODRIVER=dummy` set before `pygame.init` in the export command). It still needs fonts and the
  sprite cache.
- An **injected clock**: everything that reads `pygame.time.get_ticks()` (the ghost hem frame) or elapsed
  milliseconds (in-between frames, death animation timing) takes a time value instead, so the export can render
  frame k at exactly `k / fps` seconds. Same images every export: deterministic.
- A **frame iterator** over a result: for each tick, the in-between frames (`SUBFRAMES`, or a rate derived from the
  output FPS), then the death frames at `DEATH_FPS`, then the hold. The live and replay visualizers should use the
  same iterator, so the export can't drift from what the window shows.
- Exact pixels: export at a whole-number `--scale` (no smooth downscaling); H.264 needs **even** width and height
  (pad by one pixel if needed).

**Encoding: options for Claude Code to weigh** (AGENTS.md: discuss dependencies before adding them):

| Option | MP4 | GIF | New dependency | Notes |
|---|---|---|---|---|
| A. Pipe raw frames to the `ffmpeg` executable (`subprocess`, `pygame.image.tobytes` → stdin) | yes | yes (with palette generation) | none in Python; needs `ffmpeg` installed (on Windows, on PATH) | Fast, streams (no temp files), best quality and size. Clear error if `ffmpeg` is missing. |
| B. `imageio` + `imageio-ffmpeg` | yes | yes | two pip packages (the second bundles an ffmpeg binary) | Works out of the box on Windows; heavier install. |
| C. Pillow for GIF only | no | yes | one pip package | Simple GIFs; no MP4. |
| D. Save PNG frames (`pygame.image.save`) and let the user encode | no | no | none | Fallback / debugging only. |

Recommendation to discuss: **A** as the main path (no Python dependency, both formats), possibly with D as a
`--frames DIR` fallback; make the encoder a small module behind one function so B can replace it later.

**Size and length.** A long run is big: 3,500 ticks × 5 in-between frames = 17,500 frames (about 6 minutes at
50 FPS). Options: `--fps`, `--speed` (ticks per second, as replay's ↑/↓), `--subframes`, and for GIFs a lower
default FPS and scale. GIF frame delays are in hundredths of a second, so pick FPS values that divide 100 (25 or
50) to keep timing exact. Report the output size and duration when done.

**CLI sketch** (to refine): `replay RESULT [--export PATH.mp4|.gif] [--fps N] [--speed TICKS_PER_SECOND]
[--scale N] [--overlays T,P,G | --no-overlays] [--run N]`. Export runs without opening a window and exits when done.

---

## Questions to discuss (please answer each)

1. Can `pacman_facing` be rebuilt on load from recorded data, or does it need recording (format bump)?
2. `nearest_walkable`: cost and cache on 101×101 mazes with 4 ghosts deciding every tile; deterministic ties?
3. Where must Inky's lineup check live so it covers every entry point (CLI, `ExperimentRunner`, tests)?
4. Does a raw-target field in `GhostStatus` affect result format 5 encoding (`=` repetition, decoding)?
5. Can spawn assignment replace `with_ghost_count` without moving any existing maze's spawns for all-Blinky
   lineups (prefix-stability)?
6. Which tests and golden files change, and can every existing golden case be kept by pinning kinds? Golden
   `classic` runs will change anyway with the tunnel and the house: say which, and regenerate only on purpose.
7. The avoidance time race (`two-opt-safe`) uses each ghost's shortest no-reverse arrival as a worst case.
   Confirm it still holds for every kind, and that it only needs the ghost graph (house) and portals (tunnel).
8. **Ghost house:** is a second (directed) neighbour table on `Maze` the cleanest way, or should mover type be a
   parameter of the existing one? What breaks in `NoReverseSearch`'s state table with directed edges? Should the
   two-wide gate allow sideways moves?
9. **House layout:** option (a), (b) or (c)? Any parsing ambiguity in (a)?
10. **Tunnel:** automatic edge portals or an explicit tunnel tile? Every place that bypasses the neighbour table
    (offset arithmetic in `speeds.py`, `encoding.py`, `animation.py`, `pygame_renderer.py`, controllers)?
11. **Tunnel visuals:** how should the renderer draw a mover crossing (two clipped copies?), and what changes in
    `maze_art` for the open mouths?
12. Any layout-letter clashes with planned features (power pellets, a recipe ghost house)?
13. The default of 4 ghosts: should it override recipe `content.ghosts.count` and layouts with fewer spawns, or
    apply only when a maze says nothing? On maps without a house, 4 random corridor spawns may land close to each
    other or to Pac-Man: is `min_distance` enough?
14. **Overlays:** lanes (perpendicular offsets) or another way to keep four ghost paths apart? How do lanes behave
    at corners, junctions and across the tunnel? Which target-marker scheme stays readable at the default scale?
15. **Export, rendering:** the cleanest way to render offscreen with the current `PygameRenderer` (constructor
    flag, separate surface target, dummy video driver)? Every place that reads wall-clock time or the display?
16. **Export, frames:** can live, replay and export share one frame iterator (ticks, in-between frames, death,
    banner)? How should output FPS map to ticks and in-between frames?
17. **Export, encoding:** option A (ffmpeg executable), B (imageio), C (Pillow) or D (PNG frames)? Performance of
    `pygame.image.tobytes` per frame at scale 3–4 on a 101×101 maze; expected file sizes for a 3,500-tick run.

## Open decisions for the owner

1. **Spawn for a kind not in the run:** use it as a generic spawn (tentative), or leave it empty?
2. **House layout format:** (a) adjacency rule, (b) coordinates footer, or (c) separate letters?
3. **Tunnel tiles:** automatic edge portals (proposed) or an explicit tunnel tile?
4. **Gate width:** may a ghost move sideways along a two-wide gate?
5. **Export encoder:** OK to require `ffmpeg` installed (option A), or add a Python dependency (B or C)?
6. **Export defaults:** FPS, speed and scale for MP4 and for GIF; overlays on or off by default in exports?

## Steps (to be discussed together, then implemented in the agreed order)

1. **Facing:** `pacman_facing` in the state and engine. *Done when:* golden tests unchanged; tests for facing after
   a move, when blocked, and at the start.
2. **Geometry:** `nearest_walkable` and the per-maze bottom-left corner. *Done when:* tests for walls, void, off-grid
   points (negative and beyond the size) and ties; corner correct on `classic` and a grotto.
3. **Ghosts:** Pinky, Inky, Clyde, registry, colours, raw target in status. *Done when:* tests for each facing
   (up has no left offset), Inky's 2P − B (including off-grid projection), Inky without Blinky raising, Clyde at
   d² = 64 (corner) and 65 (chase); `play --maze classic --ghost-kinds blinky,pinky,inky,clyde` looks right with
   the G overlay.
4. **Lineup:** default 4 cycling kinds, `--ghost-kinds`, validation, lineup in results. *Done when:* golden cases
   pinned and passing; `--ghosts 2` gives Blinky and Pinky; Inky without Blinky fails with a clear CLI message.
5. **Layout spawns:** letters, spawn kinds on `Maze`, serialization, assignment. *Done when:* tests for each
   assignment stage, a layout with all four letters, a kind spawn used as generic, too many ghosts (random
   extras), saved mazes without kinds loading, `format_layout` round trip.
6. **Ghost house:** ghost graph with the one-way gate, house spawns in the layout, `classic.txt` updated.
   *Done when:* tests that a ghost leaves through the gate, can never re-enter, and Pac-Man can never enter;
   `NoReverseSearch` paths from inside the house; the avoidance controllers measure ghost distances on the ghost
   graph; `play --maze classic` starts with three ghosts in the house that leave at once.
7. **Tunnel:** portal edges, wrap-aware occupancy and drawing, `enclosed` exemption. *Done when:* tests for both
   directions for Pac-Man and a ghost, a catch inside the tunnel, BFS and the metric closure using the wrap, a
   saved run with a wrap replaying correctly; visually, sprites slide out of one side and in at the other.
8. **Ghost overlays:** colours for every kind, lanes, outlines, distinct target markers, raw-target dots, wrap-aware
   path drawing, optional legend. *Done when:* a replay of `classic` with all four ghosts chasing through the same
   corridor shows four separate, readable lines and four distinguishable targets; screenshots of a few crossings
   are attached to the report.
9. **Replay export:** offscreen rendering, injected clock, shared frame iterator, encoder, CLI options.
   *Done when:* exporting the same result twice gives identical frames (test on a short run: hash of the raw frames);
   an MP4 and a GIF of a full `classic` run open and play at the right speed with the death sequence or end
   banner; a missing encoder fails with a clear message; export works on Windows without opening a window.

After the steps: update `AGENTS.md` (package map, layout legend, tiles, the export command, known open points:
tunnel and decorative house no longer open) and `docs/cli.md` (replay export options).

## Code involved

`controllers/ghosts/ghost.py`, `blinky.py`, `registry.py`; `controllers/status.py`;
`controllers/algorithmic/tours/two_opt_avoid.py`; `algorithms/pathfinding/no_reverse.py`, `bfs.py`;
`algorithms/graph/metric_closure.py`; `simulation/state.py`, `engine.py`, `speeds.py`, `result.py`,
`encoding.py`; `mazes/tiles.py`, `maze.py`, `layout.py`, `layouts/classic.txt`, `serialization.py`,
`rules/hard.py`, `generation/content.py`, `generation/pipeline.py`, `registry.py`; `maze_commands.py`, `cli.py`;
`visualization/animation.py`, `pygame_renderer.py`, `maze_art.py`, `theme.py`, `sprites.py`, `replay.py`,
`live.py`; `simulation/replay.py` (`ReplayPlayer`, `ResultSequence`);
`tests/test_ghosts.py`, `tests/test_ghost_spawns.py`, `tests/test_rules.py`, `tests/golden/`.

## Sources on the original behaviour

- Jamey Pittman, *The Pac-Man Dossier* (Pinky's offset and the overflow bug):
  https://jerz.setonhill.edu/blog/2009/02/20/the_pac-man_dossier/amp/
- Inky's 2P − B and Clyde's 8-tile rule: https://github.com/virgs/pacman, https://perfectpacman.com/?p=2169
- Scatter corners: https://gamedesignskills.com/game-design/pac-man-pathfinding/