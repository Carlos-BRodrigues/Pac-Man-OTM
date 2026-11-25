# Command-line guide

Every command runs as `python -m pacman_otm <command> …` (or `pacman_otm <command> …` after
`pip install -e .`). Add `--help` to any command for its options.

| Command | What it does |
|---|---|
| [`simulate`](#simulate) | Run one controller on one maze, optionally watching it. |
| [`play`](#play) | Play a maze yourself with the keyboard. |
| [`experiment`](#experiment) | Run a controller many times (a new maze per run with a recipe), and save everything. |
| [`replay`](#replay) | Watch a saved run, or every run of an experiment. |
| [`mazes`](#mazes) | List, show, check, preview, generate and save mazes. |
| [`sprites`](#sprites) | Preview the player and death animations. |

---

## Choosing a maze

`simulate`, `play`, `experiment` and the `mazes` commands all take a maze the same way.

### `--maze SPEC`

`SPEC` is one of:

| SPEC | Kind | Where it lives |
|---|---|---|
| `classic`, `small` | **layout**: a hand-drawn text file | `src/pacman_otm/mazes/layouts/*.txt` |
| `open-lattice`, `twisty`, … | **recipe**: a description that generates mazes | `src/pacman_otm/mazes/recipes/*.toml` |
| a name you saved | **saved maze**: a generated maze, kept as is | `src/pacman_otm/mazes/saved/*.json` |
| `path/to/file.txt`, `.toml`, `.json` | one-off layout, recipe or saved maze | anywhere |

The default is `classic`. `mazes list` shows every registered name. Any file you drop into one of those three
folders is registered under its file name; a name may only be used once across all three folders.

### `--maze-seed N`

Picks which maze a recipe makes. The same recipe and seed always give the same maze.

- Without it, `simulate`, `play` and the `mazes` commands pick a **random seed** and print it:

  ```
  Maze seed: 2937922887  (repeat this maze with --maze-seed 2937922887)
  ```

  The seed is also recorded in the result file. A strict recipe may fail for some seeds; a random seed that fails
  is replaced by another (up to 10 tries, each failure printed). A seed you give is used as is, or fails.
- In `experiment`, leaving it out means **a new maze per run**. Giving it means one maze for every run (see
  [experiment](#experiment)).
- Layouts and saved mazes ignore it.

### `--maze-set KEY=VALUE`

Changes one recipe value for this command only, and can be repeated. Some examples:

```powershell
--maze-set size=41x41                  # fixed size
--maze-set size=11x21..51x51           # a size range: each maze's size is drawn from its seed
--maze-set topography.straightness=-0.8
--maze-set rules.max_block.wall.size=4
--maze-set rules.max_dead_ends=off     # remove a rule
--maze-set content.pellets.placer=density --maze-set content.pellets.p=0.3
```

Every key and value is described in the [recipe guide](recipes.md#changing-a-recipe-from-the-command-line---maze-set).
`--maze-set` on a layout or saved maze is an error.

### `--ghosts N` and `--ghost-kinds K,K,...`

A ghost catches Pac-Man by ending a step on his tile or by swapping tiles with him head-on (neighbouring tiles are
safe). There are four kinds. They all move the same way and differ only in where they aim:

| Kind | Aims at |
|---|---|
| **Blinky** (red) | Pac-Man's tile. |
| **Pinky** (pink) | 4 tiles ahead of Pac-Man, in the direction he faces (facing up: straight up). |
| **Inky** (cyan) | Twice the point 2 tiles ahead of Pac-Man, minus Blinky's tile: the two close in from opposite sides. Needs a Blinky in the run. |
| **Clyde** (orange) | Pac-Man's tile while more than 8 tiles away (straight line); closer, his corner at the bottom left of the map. |

A target on a wall or off the map is replaced by the nearest corridor tile; with **G** the overlay shows both.

By default a maze brings its own ghosts, one per spawn: `classic` has Blinky above the ghost house and Pinky, Inky and
Clyde inside it; every starter recipe has 4 (`content.ghosts.count`); `small` has none.

- `--ghosts N`: N ghosts, cycling Blinky, Pinky, Inky, Clyde (`--ghosts 2` = Blinky and Pinky, 5 = a second Blinky).
  `--ghosts 0` plays without ghosts.
- `--ghost-kinds blinky,clyde`: exactly these ghosts, in this order. With `--ghosts` too, the counts must match.
  Inky without a Blinky is an error.
- Each ghost starts on a spawn marked for its kind if there is one, then on a spawn for any ghost (or for a kind
  that is not playing), then on a random tile from `--maze-seed` (default 0), at least 10 steps from the start.
- On a recipe, the count sets `content.ghosts.count`: the same seed gives the same corridors and pellets.

**How ghosts move.** Ghosts in the house leave through the gate at once; the gate is one way, so no ghost ever
goes back in, and Pac-Man can never enter. On `classic`, the middle row is a tunnel: leaving the left edge
arrives on the right and back, for everyone. A ghost keeps moving and never turns back, except at a dead end. It always knows the
shortest path to its target that it can drive without reversing, but it can only choose at junctions. It decides
one tile early: as it moves onto a junction, the exit it will take there is already fixed, using where Pac-Man
was at that moment. A late turn by Pac-Man can therefore juke it.

### `--speeds easy|arcade|equal`

Time runs in **ticks**. A move to the next tile costs 16 units of progress; every tick a mover gains its speed,
and leftover progress carries into the next tile, so the ratios are exact.

| Preset | Pac-Man | Ghosts | Pellet eaten |
|---|---|---|---|
| `easy` (default) | 16 (1 tile per tick) | 15 (15/16 of Pac-Man) | no cost: Pac-Man always outruns a ghost |
| `arcade` | 16 | 15 | costs Pac-Man 2 units: a corridor of dots at 16/18 |
| `equal` | 16 | 16 | no cost: the game before speeds existed |

With `arcade`, Pac-Man pulls away from a ghost in a cleared corridor and loses ground while eating. Everyone
still decides once per tile, at the tile centre, so controllers and pathfinding work in whole tiles. A ghost
catches Pac-Man when it occupies his tile (a mover occupies its next tile once halfway there) or when they swap
tiles. Results count `total_steps` in ticks (time) and `pacman_moves` in tiles (path length).

---

## `simulate`

Runs one controller on one maze.

```powershell
python -m pacman_otm simulate --maze twisty --visualize                 # a random twisty maze
python -m pacman_otm simulate --maze organic --visualize                # a random grown, organic maze
python -m pacman_otm simulate --maze grotto --visualize                 # a mirrored, oval cave
python -m pacman_otm simulate --maze open-lattice --maze-seed 7 --save  # save the result
python -m pacman_otm simulate --maze small --controller random-walk --seed 7 --output run.json --show-history
```

| Option | Default | Meaning |
|---|---|---|
| `--maze`, `--maze-seed`, `--maze-set`, `--ghosts`, `--ghost-kinds` | `classic`, random, the maze's ghosts | See [Choosing a maze](#choosing-a-maze). |
| `--controller` | `two-opt-safe` | `nearest-pellet`, `random-walk`, or a tour controller over the metric closure: `nearest-pellet-tour`, `two-opt` (nearest neighbour + 2-opt), `two-opt-avoid` (2-opt tour that flees one tile when a ghost is near its next tiles), `two-opt-safe` (2-opt tour with timed danger checks, safe detours, escapes and re-planning), `held-karp` (optimal, at most 16 pellets). Tour controllers print their tour length, MST lower bound and gap. |
| `--seed N` | `42` | Seed for stochastic controllers such as `random-walk`. |
| `--speeds` | `easy` | `easy`, `arcade` or `equal`; see [`--speeds`](#--speeds-easyarcadeequal). |
| `--max-steps N` | `3500` | Stop after this many ticks. |
| `--visualize` | off | Show the run live. |
| `--scale N` | fits the screen | Whole-number pixel scale: each 8×8 tile is drawn N times larger, pixel-exact. Without it the window fills 85% of the screen's height or width (whichever the maze's shape reaches first), so every maze gets a window of about the same size. |
| `--save` | off | Save the result to `results/<controller>_<maze>_<timestamp>.json`. A recipe maze is named `<recipe>-seed<N>`. |
| `--output NAME` | none | Save to this file instead; implies `--save`. A bare name goes into `results/`. |
| `--show-history` | off | Print every recorded step. |

**Results are not saved unless you pass `--save` or `--output`.** A saved result holds the whole run and its maze,
so `replay` needs nothing else.

While visualizing: **T** toggles the controller's target, **P** its planned path, **G** every ghost's path and
target, each in its ghost's colour: the paths run side by side where they share a corridor, each target has its own
marker shape (Blinky ring, Pinky square, Inky diamond, Clyde cross, shown in the top bar), and a small dot joined to a
marker is the raw target when it lay on a wall or off the map. Close the window to stop. A run ends as `caught` when a ghost catches Pac-Man,
and the death animation plays. When a run ends the overlays disappear and a banner shows **COMPLETE!** or
**GAME OVER!** (also in replays).

---

## `play`

Play a maze yourself.

```powershell
python -m pacman_otm play --maze small
python -m pacman_otm play --maze classic-like --save
```

After a 2-second "READY!" Pac-Man starts moving left and keeps moving. Steer with the **arrow keys** or **WASD**; a
turn pressed early is taken at the next opening. **Esc** quits.

The options are the same as `simulate` (`--maze…`, `--ghosts`, `--speeds`, `--max-steps`, `--scale`, `--save`,
`--output`).
Use `--ghosts 0` for a ghost-free run.
Results are named `manual_<maze>_<timestamp>.json` and are saved only on request.

---

## `experiment`

Runs one controller many times and **always saves**: one file per run, plus a summary.

```powershell
python -m pacman_otm experiment --maze open-lattice --runs 20 --seed 42                  # a new maze per run
python -m pacman_otm experiment --maze open-lattice --runs 20 --seed 42 --controller random-walk
python -m pacman_otm experiment --maze blob-lattice --runs 10 --visualize                # watch it
python -m pacman_otm experiment --maze open-lattice --maze-set size=11x11..41x41 --runs 50
python -m pacman_otm experiment --maze classic --runs 20                                 # one fixed layout
python -m pacman_otm experiment --maze my-mazes --controller nearest-pellet-tour         # a maze set: run i plays maze i
```

| Option | Default | Meaning |
|---|---|---|
| `--maze`, `--maze-set`, `--ghosts`, `--ghost-kinds` | `classic`, the maze's ghosts | See [Choosing a maze](#choosing-a-maze). Every controller meets the same ghosts on the same maze. `results.json` counts `caught_runs`; every run record has `ghosts`. |
| `--maze-seed N` | none | With a recipe: one maze (seed N) for every run. Without it, each run gets its own maze. |
| `--controller` | `two-opt-safe` | The controller to test. |
| `--runs N` | `10`, or the set size | Number of runs. With a maze set, the default is one run per maze; more runs cycle through the set. |
| `--seed N` | `42` | The **experiment seed**. Run *i* gets its maze seed and controller seed from it. |
| `--max-steps N` | `3500` | Ticks per run. |
| `--speeds` | `easy` | See [`--speeds`](#--speeds-easyarcadeequal); recorded in `results.json`. |
| `--name NAME` | `<controller>_<maze>` | Folder name; `_001`, `_002`, … is added if it already exists. |
| `--output-dir DIR` | `results` | Where the experiment folder goes. |
| `--visualize` | off | Show every run live in one window. Each run's maze appears in turn. |
| `--fps N` | `30` | Steps per second while visualizing. |
| `--scale N` | fits the screen | Window scale. |

**Comparing controllers fairly.** Run *i*'s maze depends only on `--seed` and *i*. Two controllers run with the same
`--seed` therefore play exactly the same sequence of mazes. A recipe with a size range also gives each run its own
size, drawn from the same seed.

**Maze sets.** A set is a fixed list of mazes to reuse across controllers: a TOML file in
`src/pacman_otm/mazes/sets/`, named by its file stem, listed by `mazes list`:

```toml
description = "Hand-picked mazes."
mazes = ["classic", "classic-sparse", "grotto1"]
```

Entries are layout or saved-maze names (or `.txt`/`.json` paths). Recipes are refused, because a set must give the
same mazes every time: save one first with `mazes save RECIPE NAME --maze-seed N`. `--maze-seed` and `--maze-set`
don't apply to a set. `results.json` records the set name and its maze list. The starter set `my-mazes` holds
the saved mazes plus `classic` and `classic-sparse` (classic with 15 spread-out pellets).

**Stopping early.** Closing the visualization window stops the experiment. The runs finished so far are saved,
and `results.json` records `"stopped_early": true`. A run whose maze cannot be generated also stops the
experiment, with an error naming the seed.

**What is written:**

```
results/nearest-pellet_open-lattice/
  results.json        experiment settings (with the recipe, once), aggregates, one record per run
  results.csv         one row per run
  runs/
    run_0001/result.json
    run_0002/result.json
    …
```

`results.csv` columns, in order:

1. Run identity: `run`, `maze`, `maze_seed`, `controller_seed`.
2. Run metrics: `total_steps` (ticks), `collected_pellets`, `completion_rate`, …, `ghosts`, `pacman_moves` (tiles).
3. Maze metrics: `maze_walkable_tiles`, `maze_loops`, `maze_dead_ends`, `maze_junction_share`,
   `maze_longest_straight_run`, `maze_longest_corridor`.
4. Tour controllers only: `tour_pellets`, `tour_length`, and where reported `tour_lower_bound` (MST),
   `tour_gap_percent` (at most this far above optimal), `tour_nn_length`, `tour_improvement_percent`
   (2-opt over nearest neighbour). These are also aggregated under `aggregates.tour_metrics`.

`maze_seed` is the seed that built that run's maze. `mazes show RECIPE --maze-seed <maze_seed>`, with the same
`--maze-set` overrides, shows it again. Simpler still, every run file holds the full maze: `replay` it.

---

## `replay`

Plays back saved runs, ghosts included, or exports them as videos. A replay only reads the files; nothing is run
again. Result files from before speeds (format 4 or older) are rejected: run them again.

```powershell
python -m pacman_otm replay run.json                                # one result (also looked up in results/)
python -m pacman_otm replay results/nearest-pellet_open-lattice     # every run of an experiment, in order
python -m pacman_otm replay nearest-pellet_open-lattice --fps 20    # bare names are looked up in results/
```

| Option | Default | Meaning |
|---|---|---|
| `--fps N` | `10` | Starting speed (ticks per second). |
| `--no-auto-advance` | off | For experiments: stop at the end of each run instead of moving on to the next. |
| `--scale N` | fits the screen | Window scale. |

| Key | Action |
|---|---|
| Space | Play / pause. Pressed at the end of a run, it restarts the run. |
| ← / → | One step back / forward. |
| Home / End | First / last step. |
| ↑ / ↓ | Faster / slower. |
| PageDown or `]` | Next run (experiments). |
| PageUp or `[` | Previous run (experiments). |
| A | Auto-advance on/off: go on to the next run when one ends (on by default). |
| T / P | Show / hide the controller's target and planned path. |
| G | Show / hide every ghost's path and target. |
| Esc | Quit. |

For experiments, the HUD shows `RUN 3/20` and the window title shows which run folder is playing.

### Exporting videos

With `--export mp4` or `--export gif`, `replay` writes videos of the full runs instead of opening a window, exactly
as the replay window shows them: every tick with its in-between pictures, the death sequence or end banner, then a
one-second hold. It needs the [`ffmpeg`](https://ffmpeg.org) executable on `PATH` (Windows: `winget install
Gyan.FFmpeg`); without it the command says so. The same result always gives the same pictures.

```powershell
python -m pacman_otm replay two-opt-safe_classic --export mp4             # every run -> results/two-opt-safe_classic/videos/run_0001.mp4, ...
python -m pacman_otm replay two-opt-safe_classic --export gif --run 3     # only run 3 -> videos/run_0003.gif
python -m pacman_otm replay run.json --export mp4 --output clip.mp4 --no-overlays
```

| Option | Default | Meaning |
|---|---|---|
| `--export mp4\|gif` | off | Write videos. |
| `--output PATH` | see below | A file for one run, a folder for several. Without it: an experiment's `videos/` folder (`run_NNNN.<format>`), or next to a result file (`x.json` → `x.mp4`). |
| `--run N` | every run | Export run N of an experiment (1-based). Repeatable. |
| `--fps N` | `10` | Ticks per second, as in the window. |
| `--subframes N` | mp4 `5`, gif `2` | Pictures per tick; the video runs at fps × subframes (50 or 20 pictures/s). For GIFs keep that a divisor of 100. |
| `--scale N` | mp4 `3`, gif `2` | Pixel scale (whole numbers only, so pixels stay sharp). |
| `--overlays T,P,G` / `--no-overlays` | all on | Which overlays to draw. |

A long run is long on video too: 3,500 ticks at 10 ticks/s is almost 6 minutes. Raise `--fps` to shorten it.

---

## `mazes`

`mazes` on its own is the same as `mazes list`.

### `mazes list`

Every registered maze with its kind, size and description. Recipe sizes may be ranges (`11..41x21..51`).

### `mazes show SPEC`

Prints the maze as layout text and its metrics (size, walkable tiles, loops, dead ends, junctions, longest straight
run and corridor, largest wall block, symmetry, pellets). It takes `--maze-seed` and `--maze-set`.

### `mazes check SPEC`

Shows the metrics, then checks the rules: the hard rules (`size_bounds`, `connected`, `enclosed`), the recipe's own
rules, and any extra rules. Violations are listed with their positions. It exits with status 1 if any rule fails.

| Option | Meaning |
|---|---|
| `--rules FILE\|RECIPE` | Extra rules: the `[[rules]]` tables of a TOML file, or another recipe's rules. |
| `--max-positions N` | Positions shown per violation (default 10). |
| `--maze-seed`, `--maze-set` | As above. |

```powershell
python -m pacman_otm mazes check classic --rules classic-like     # how close is classic to classic-like?
python -m pacman_otm mazes check small --rules classic-like       # lists small's one-tile walls, among others
python -m pacman_otm mazes check open-lattice --maze-seed 3 --maze-set topography.spacing=[3,5] --maze-set rules.min_wall_thickness.size=2
```

### `mazes preview SPEC`

Opens a window with the maze, its pellets and the start, with any rule violations tinted red. It takes the same
options as `check`, plus `--scale`. Esc closes it.

### `mazes generate RECIPE`

Makes mazes from a recipe and prints each one as text, followed by a line of metrics. This is the quickest way to
see what a recipe does.

```powershell
python -m pacman_otm mazes generate twisty --count 6                  # six random seeds in a row
python -m pacman_otm mazes generate twisty --seed 100 --count 6 --quiet
python -m pacman_otm mazes generate classic-like --seed 7 --save demo
```

| Option | Default | Meaning |
|---|---|---|
| `--seed N` | random | The first seed; `--count K` makes seeds N … N+K−1. |
| `--count K` | `1` | How many mazes. A seed that fails is reported and skipped; the command fails only if all do. |
| `--quiet` | off | Metrics only, no maze text. |
| `--save NAME\|PATH` | none | Save each maze, as with `mazes save`. With `--count` above 1, the seed is added: `demo-7`, `demo-8`, … |
| `--layout` | off | Save as an editable `.txt` layout. |
| `--force` | off | Replace an existing file. |
| `--maze-set` | none | Recipe overrides. |

### `mazes save SPEC NAME|PATH`

Gives any maze a name, or writes it to a file.

```powershell
python -m pacman_otm mazes save twisty keeper --maze-seed 4                 # mazes/saved/keeper.json  -> --maze keeper
python -m pacman_otm mazes save twisty my-twisty --maze-seed 4 --layout     # mazes/layouts/my-twisty.txt
python -m pacman_otm mazes save open-lattice C:\mazes\big.txt --maze-set size=61x61
```

| Target | Result |
|---|---|
| `NAME` | Registered as `mazes/saved/NAME.json`. |
| `NAME --layout` | Registered as `mazes/layouts/NAME.txt`. |
| `….json` or `….txt` path | Written to that file only. You use it with `--maze path/to/file`. |

- **`.json` saved maze:** keeps everything, including how it was made (recipe, seed, package version). It does not
  change if the generator changes later.
- **`.txt` layout:** keeps tiles, pellets and the start, and you can **edit it by hand** (see below). How it was made
  is not kept.

The name must not already be in use by a different kind of maze. To replace a maze of the same kind, use `--force`.

---

## Making and editing layouts by hand

A layout is a text file with one character per tile. All rows must be the same length, and trailing spaces count.

| Character | Tile |
|---|---|
| `#` | wall |
| `.` or `o` | corridor with a pellet (both are ordinary pellets) |
| space | corridor without a pellet |
| `P` | Pac-Man's start: a corridor without a pellet. Exactly one is required. |
| `_` | void: outside the maze, drawn as background |
| `H`, `-` | ghost house and ghost gate: ghosts only, and the gate lets them out but never back in |
| `G` | ghost spawn for any ghost: a corridor without a pellet where a ghost starts |
| `B`, `K`, `I`, `C` | ghost spawn for Blinky, Pinky (`K`: `P` is Pac-Man), Inky, Clyde |
| `g`, `b`, `k`, `i`, `c` | the same spawns with a pellet |

A spawn letter next to an `H` (or to such a spawn) lies **inside the ghost house**, as on `classic`:
`#HIKHCH#` puts Inky, Pinky and Clyde in the house. Upper case only there: the house has no pellets. A gate tile
must touch the house and lead to a corridor.

A corridor tile on the edge of the grid whose tile on the opposite edge (same row or column) is also a corridor is a
**tunnel mouth**: moving off the edge arrives on the other side, as on `classic`'s middle row.

The usual way to get a layout: generate a maze you like, save it with `--layout`, then edit it.

1. `python -m pacman_otm mazes save classic-like mine --maze-seed 12 --layout`
2. Open `src/pacman_otm/mazes/layouts/mine.txt`. Move the `P`, turn `.` into space to remove pellets (or the
   reverse to add them), turn `#` into `.` to open a wall, or mark ghost spawns with `G`.
3. `python -m pacman_otm mazes check mine` validates it, then `simulate --maze mine --visualize` plays it.

When a layout loads, it is checked for size (5..101), exactly one `P`, and that every pellet can be reached from
the start. Errors name the row and column. The hard rules aren't enforced for layouts, but `mazes check` reports them
(tunnel mouths don't count as open edges).

---

## `sprites`

`python -m pacman_otm sprites [--scale N]` previews the player and death animations, and every ghost kind
looking each way with its spawn sticker.

---

## Where files go

| What | Where | Saved when |
|---|---|---|
| `simulate` / `play` results | `results/*.json` | Only with `--save` or `--output`. |
| Experiments | `results/<name>/` | Always. |
| Saved mazes | `src/pacman_otm/mazes/saved/*.json` | `mazes save NAME`, `mazes generate --save NAME`. |
| Layouts | `src/pacman_otm/mazes/layouts/*.txt` | By hand, or `mazes save NAME --layout`. |
| Recipes | `src/pacman_otm/mazes/recipes/*.toml` | By hand ([recipe guide](recipes.md)). |

Saving into the `mazes/` folders works with the development install (`pip install -e .`), which uses the source
tree directly.

Result files carry a format version; files from older versions of the program are rejected with a message
asking you to re-run them.
