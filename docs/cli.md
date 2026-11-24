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
| `--maze`, `--maze-seed`, `--maze-set` | `classic`, random | See [Choosing a maze](#choosing-a-maze). |
| `--controller` | `nearest-pellet` | `nearest-pellet`, `random-walk`, or a tour controller over the metric closure: `nearest-pellet-tour`, `two-opt` (nearest neighbour + 2-opt), `held-karp` (optimal, at most 16 pellets). Tour controllers print their tour length, MST lower bound and gap. |
| `--seed N` | `42` | Seed for stochastic controllers such as `random-walk`. |
| `--max-steps N` | `3000` | Stop after this many steps. |
| `--visualize` | off | Show the run live. |
| `--scale N` | fits the screen | Whole-number pixel scale: each 8×8 tile is drawn N times larger, pixel-exact. Without it the window fills 85% of the screen's height or width (whichever the maze's shape reaches first), so every maze gets a window of about the same size. |
| `--save` | off | Save the result to `results/<controller>_<maze>_<timestamp>.json`. A recipe maze is named `<recipe>-seed<N>`. |
| `--output NAME` | none | Save to this file instead; implies `--save`. A bare name goes into `results/`. |
| `--show-history` | off | Print every recorded step. |

**Results are not saved unless you pass `--save` or `--output`.** A saved result holds the whole run and its maze,
so `replay` needs nothing else.

While visualizing: **T** toggles the controller's target, **P** its planned path. Close the window to stop.

---

## `play`

Play a maze yourself.

```powershell
python -m pacman_otm play --maze small
python -m pacman_otm play --maze classic-like --save
```

After a 2-second "READY!" Pac-Man starts moving left and keeps moving. Steer with the **arrow keys** or **WASD**; a
turn pressed early is taken at the next opening. **Esc** quits.

The options are the same as `simulate` (`--maze…`, `--max-steps`, `--scale`, `--save`, `--output`).
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
| `--maze`, `--maze-set` | `classic` | See [Choosing a maze](#choosing-a-maze). |
| `--maze-seed N` | none | With a recipe: one maze (seed N) for every run. Without it, each run gets its own maze. |
| `--controller` | `nearest-pellet` | The controller to test. |
| `--runs N` | `10`, or the set size | Number of runs. With a maze set, the default is one run per maze; more runs cycle through the set. |
| `--seed N` | `42` | The **experiment seed**. Run *i* gets its maze seed and controller seed from it. |
| `--max-steps N` | `3000` | Per run. |
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
2. Run metrics: `total_steps`, `collected_pellets`, `completion_rate`, …
3. Maze metrics: `maze_walkable_tiles`, `maze_loops`, `maze_dead_ends`, `maze_junction_share`,
   `maze_longest_straight_run`, `maze_longest_corridor`.
4. Tour controllers only: `tour_pellets`, `tour_length`, and where reported `tour_lower_bound` (MST),
   `tour_gap_percent` (at most this far above optimal), `tour_nn_length`, `tour_improvement_percent`
   (2-opt over nearest neighbour). These are also aggregated under `aggregates.tour_metrics`.

`maze_seed` is the seed that built that run's maze. `mazes show RECIPE --maze-seed <maze_seed>`, with the same
`--maze-set` overrides, shows it again. Simpler still, every run file holds the full maze: `replay` it.

---

## `replay`

Plays back saved runs. A replay only reads the files; nothing is run again.

```powershell
python -m pacman_otm replay run.json                                # one result (also looked up in results/)
python -m pacman_otm replay results/nearest-pellet_open-lattice     # every run of an experiment, in order
python -m pacman_otm replay nearest-pellet_open-lattice --fps 20    # bare names are looked up in results/
```

| Option | Default | Meaning |
|---|---|---|
| `--fps N` | `10` | Starting speed (steps per second). |
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
| Esc | Quit. |

For experiments, the HUD shows `RUN 3/20` and the window title shows which run folder is playing.

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
| `H`, `-` | ghost house and ghost gate (decorative only) |

The usual way to get a layout: generate a maze you like, save it with `--layout`, then edit it.

1. `python -m pacman_otm mazes save classic-like mine --maze-seed 12 --layout`
2. Open `src/pacman_otm/mazes/layouts/mine.txt`. Move the `P`, turn `.` into space to remove pellets (or the
   reverse to add them), or turn `#` into `.` to open a wall.
3. `python -m pacman_otm mazes check mine` validates it, then `simulate --maze mine --visualize` plays it.

When a layout loads, it is checked for size (5..101), exactly one `P`, and that every pellet can be reached from
the start. Errors name the row and column. The hard rules aren't enforced for layouts (`classic` has a tunnel that
touches the edge), but `mazes check` reports them.

---

## `sprites`

`python -m pacman_otm sprites [--scale N]` previews the player and death animations.

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
