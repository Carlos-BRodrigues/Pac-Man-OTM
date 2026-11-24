# Writing maze recipes

For the commands that use recipes (`simulate`, `experiment`, `mazes generate`, …) see the
[command-line guide](cli.md).

A **recipe** is a small TOML file that describes how to make a maze. It doesn't contain the maze itself.
Given a seed, the recipe always produces the same maze, so any maze can be rebuilt from its
recipe and seed.

A recipe has seven parts, each covered below:

| Part | Says |
|---|---|
| [`[size]`](#size) | How big the grid is: a fixed size, or a range to draw from. |
| [`[shape]`](#shape) | Which part of the grid belongs to the maze (a rectangle, an ellipse, a random blob…). |
| [`[topography]`](#topography) | How the corridors are laid out: the generator and its parameters. |
| [`[[rules]]`](#rules) | Requirements the corridors must meet (no dead ends, no thick walls…). |
| [`[content.pellets]`](#contentpellets) | Where the pellets go. |
| [`[content.start]`](#contentstart) | Where Pac-Man starts. |
| [`[content.ghosts]`](#contentghosts) | How many ghosts there are and where they spawn. |

All you need to begin is a `[size]`; every other part has a default.

---

## Quick start

1. Create `src/pacman_otm/mazes/recipes/my-maze.toml`:

   ```toml
   name = "my-maze"
   description = "My first recipe."

   [size]
   height = 31
   width = 31

   [topography]
   spacing = [2, 4]
   extra_loops = 0.2

   [[rules]]
   rule = "max_dead_ends"
   count = 0
   ```

   The file name (without `.toml`) becomes the maze's name: `my-maze`. It must not match the name of a layout or saved maze.

2. Look at what it makes:

   ```powershell
   python -m pacman_otm mazes list                              # my-maze appears as a recipe
   python -m pacman_otm mazes generate my-maze --count 6        # six mazes as text, with numbers
   python -m pacman_otm mazes preview my-maze                   # a random one in a window
   python -m pacman_otm mazes check my-maze --maze-seed 3       # metrics and rule check
   ```

3. Play on it:

   ```powershell
   python -m pacman_otm simulate --maze my-maze --visualize            # a random maze
   python -m pacman_otm simulate --maze my-maze --maze-seed 3 --visualize
   python -m pacman_otm experiment --maze my-maze --runs 20 --visualize # a new maze every run
   ```

A recipe can also live anywhere else and be passed as a path: `--maze path/to/my-maze.toml`.

---

## Seeds

- **No `--maze-seed`** on `simulate`, `play`, `mazes show/check/preview`: a random seed is chosen and
  printed (`Maze seed: 2937922887 (repeat this maze with --maze-seed 2937922887)`). The seed is also
  saved in the result file, so every run can be repeated. If a strict recipe can't build a maze from that seed,
  another random seed is tried (up to 10), and the failure is printed. A seed you give is never replaced.
- **`--maze-seed N`**: exactly that maze.
- **`experiment`** without `--maze-seed`: every run gets its own maze. Run *i*'s maze seed comes from
  the experiment `--seed` and *i*, so two controllers run with the same `--seed` play the same mazes.
  `--maze-seed N` instead uses one maze for all runs.
- **`mazes generate`**: `--seed N` is the first seed and `--count K` makes seeds N to N+K−1.
  Without `--seed` the first seed is random. Every seed is printed.

A maze seed is split into six independent streams: the size (when it is a range), the shape, the corridors, the
start, the pellets and the ghost spawns. Changing one part of a recipe therefore leaves the others alone. For
example, a different pellet placer gives the same corridors and the same start, and a different number of ghosts
(`--ghosts N`) gives the same maze with other spawns.

**Keeping a maze.** If a generated maze is worth keeping, give it a name:

- `mazes save my-maze keeper --maze-seed 3` saves it as `mazes/saved/keeper.json`. It is then a named maze
  (`--maze keeper`) that keeps its recipe and seed but no longer depends on the generator's code.
- `mazes save my-maze keeper --maze-seed 3 --layout` saves it as an editable layout, `mazes/layouts/keeper.txt`.
  You can then move the start or place pellets by hand
  ([how](cli.md#making-and-editing-layouts-by-hand)).

---

## The whole file at a glance

Every key with its default value. Anything you leave out takes the default.

```toml
name = "my-maze"            # default: the file name
description = ""            # shown by 'mazes list'

[size]                      # required
height = 31                 # rows, 5..101, or a range: [11, 41]
width = 31                  # columns, 5..101, or a range: [21, 51]

[shape]
kind = "rectangle"          # rectangle | ellipse | blob | layout

[topography]
generator = "lattice"       # the only generator so far
spacing = [2, 4]            # [min, max] tiles between parallel corridor lines
corridor_width = 1          # tiles
extra_loops = 0.1           # 0..1
mirror = "none"             # none | horizontal | vertical | both
straightness = 0.0          # -1 (twisty) .. +1 (long halls)
node_dropout = 0.0          # 0 .. <0.5
max_repair_rounds = 200

# [[rules]] tables: none by default (the three hard rules always apply)

[content.pellets]
placer = "all_corridors"    # all_corridors | density | exclude_near_start

[content.start]
placer = "center"           # center | random | layout

[content.ghosts]
placer = "random"
count = 0                   # ghost spawns (one Blinky each); --ghosts N overrides
min_distance = 10           # BFS steps from the start
```

---

## `[size]`

| Key | Type | Meaning |
|---|---|---|
| `height` | integer, or `[min, max]`, within 5..101 | Rows of the grid. |
| `width` | integer, or `[min, max]`, within 5..101 | Columns of the grid. |

A **range** makes every maze a different size. Height and width are each drawn uniformly from their range, with the
maze seed, so a seed always gives the same size. In an experiment each run gets its own size. Ranges are inclusive.

```toml
[size]
height = [11, 41]     # 11..41 rows
width = [21, 51]      # 21..51 columns
```

On the command line: `--maze-set size=11x21..41x51`, or one dimension with `--maze-set size.width=[21,51]`.

Things to keep in mind with ranges:

- Rules must work at the smallest size. A shape that leaves no room for corridors, or a rule that cannot be met
  at 11×11, fails for the seeds that draw small sizes. Try `mazes generate RECIPE --count 20 --quiet` to check.
- A `layout` shape needs a fixed size equal to the layout's.

The outer ring of the shape is always wall, so the corridors have `height − 2` by `width − 2` tiles to use.

---

## `[shape]`

The shape marks which tiles of the grid belong to the maze. Everything outside it is *void*, which is drawn as
background. The shape's outermost ring of tiles becomes wall, so every maze is closed in.

| `kind` | Extra keys | Meaning |
|---|---|---|
| `rectangle` | none | The whole grid. |
| `ellipse` | none | The largest ellipse that fits the grid. It is symmetric both ways. |
| `blob` | `fill`, `mirror` | A random organic outline: a seeded random walk of overlapping discs from the centre, smoothed once. |
| `layout` | `path` | The outline of a layout file: every tile that isn't void (`_`). |

**`blob` keys**

| Key | Default | Meaning |
|---|---|---|
| `fill` | `0.6` | Share of the grid the blob covers, 0.1..0.95. Measured after mirroring. |
| `mirror` | `"none"` | `horizontal`, `vertical` or `both`: makes the outline symmetric. A blob only becomes a symmetric *maze* if you also set the same `topography.mirror`. |

**`layout` keys**

| Key | Default | Meaning |
|---|---|---|
| `path` | none (required) | A layout name such as `"classic"`, a path relative to the recipe file, or an absolute path. The layout's size must equal `[size]`. |

The visible outline follows the corridors rather than the shape. Wall that touches no corridor (not even
diagonally) and connects to the outside becomes void, so a curved or ragged shape edge doesn't show up as a
thick block of wall. It looks the same, because only wall next to corridors is ever drawn.

---

## `[topography]`

There are two generators, chosen with `generator`:

| `generator` | Makes | Good for |
|---|---|---|
| `"lattice"` (default) | Corridors along randomly spaced grid lines. | Fast, very configurable; wide corridors; a grid-like, tidy look. |
| `"grow"` | Winding corridors dug path by path. | Organic, hand-made-looking arcade mazes. |

### The `lattice` generator

The **lattice** generator builds the corridors in five steps:

1. Corridor **lines** (rows and columns) are placed at random spacings.
2. Each place two lines cross is a **node**. The piece of line between two neighbouring nodes is a **segment**.
3. A random **spanning tree** over the nodes makes the maze connected.
4. A share of the unused segments is added as **extra loops**.
5. **Repairs** add, or rarely remove, segments until every rule holds. A full rule check at the end must pass.

| Key | Default | Range | Meaning |
|---|---|---|---|
| `generator` | `"lattice"` | `lattice`, `grow` | The corridor generator. The keys below are the lattice's; `grow` has its own (see [below](#the-grow-generator)). |
| `spacing` | `[2, 4]` | `min ≥ corridor_width + 1`, `max ≥ min` | Distance from one corridor line to the next parallel one, in tiles, drawn at random from `[min, max]`. The wall between two lines is `spacing − corridor_width` thick. Small spacing gives a dense maze with thin walls; large spacing gives big wall blocks and long segments. |
| `corridor_width` | `1` | `≥ 1` | Width of each corridor. Use 2 or more for halls. See [Wide corridors](#wide-corridors). |
| `extra_loops` | `0.1` | 0..1 | Share of the unused segments added after the tree. `0` gives a tree (no loops, many dead ends, unless a rule closes them); `0.3` or more gives a very open maze. |
| `mirror` | `"none"` | `none`, `horizontal`, `vertical`, `both` | Symmetry. `horizontal` mirrors left ↔ right, like the classic maze; `vertical` mirrors top ↔ bottom. The shape must be symmetric the same way (rectangle and ellipse always are; a blob needs `shape.mirror`). |
| `straightness` | `0.0` | −1..1 | Texture. Above 0, the tree tends to keep going straight, giving long halls. Below 0, it tends to turn at every node, giving twisty corridors. Measured on 31×31 mazes, the mean straight stretch grows from about 4.0 tiles at −1 to 5.5 at +1. |
| `node_dropout` | `0.0` | 0..<0.5 | Share of nodes removed before the tree: irregular cells, bigger wall islands, fewer corridors. Repairs may bring a removed node back if a rule needs it. |
| `max_repair_rounds` | `200` | `≥ 1` | Safety limit for the repair loop. You should rarely need to raise it. |

### The `grow` generator

`grow` makes organic, hand-made-looking mazes: winding corridors, walls of the thickness you ask for, and no
dead ends. It doesn't use grid lines. It starts from a small maze and **digs one winding path at a time**
through solid wall, each from one corridor to another, until every rule holds.

1. **Start:** a ring corridor just inside the shape (for rectangles), or a small square loop at the shape's
   deepest point (any shape).
2. **Dig:** each path is aimed at what still needs work, in this order:
   1. an overlong corridor (`max_straight_run`, `max_corridor_length`), which gets a junction: a short straight
      bridge to the corridor next to it, or a new branch;
   2. a wall block that is too big (`max_block(wall)`);
   3. any part of the shape that is still far from a corridor, so the maze fills the shape (best effort);
   4. `min_loops`, `min_junction_share` and `walkable_fraction.min`.
3. **Shape of a path:** a path is the cheapest route through wall that keeps its distance from other corridors.
   Wall deep inside a block is cheaper (`depth_bonus`), every tile has a random extra cost (`noise`), and every
   turn costs extra (`turn_cost`). Each path leaves a corridor straight, at a right angle.
4. **Check:** every path must keep the rules it touches. If growth runs out of moves, it starts again (`attempts`),
   still from the same seed stream, so it stays reproducible. The finished maze must pass the full rule check.

```toml
[topography]
generator = "grow"
turn_cost = 4.0

[[rules]]
rule = "min_wall_thickness"   # walls at least 2 thick; without this rule grow uses 1
size = 2

[[rules]]
rule = "max_block"            # dig until no wall block is 7x7; without it, max_wall_block applies
tile = "wall"
size = 7
```

| Key | Default | Range | Meaning |
|---|---|---|---|
| `start` | `"auto"` | `auto`, `ring`, `center` | `ring`: a corridor along the inside of the shape, arcade-like. `center`: a small loop in the middle of the shape (its deepest point; with `mirror`, on the mirror axis), from which the maze grows outwards. It works for any shape, rectangles too, and gives a less regular border than the ring. `auto`: the ring for rectangular shapes, otherwise center. A ring along a curved edge is one long winding corridor, so for curved shapes ask for `ring` explicitly if you want it. |
| `turn_cost` | `4.0` | ≥ 0 | Extra cost of a turn. At `0` paths jog a lot (about 11% corner tiles in 31×31 mazes). From about `1` up, paths turn only where they must (about 7.5%), so values above that change little. |
| `noise` | `1.5` | ≥ 0 | Random extra cost per tile: varies which way paths go, so mazes from different seeds differ more. |
| `depth_bonus` | `3.0` | ≥ 0 | How much cheaper the middle of a wall block is than its edge: higher makes paths swing deeper into empty space. |
| `mirror` | `"none"` | `none`, `horizontal`, `vertical`, `both` | Every path is mirrored. The shape must be symmetric the same way. |
| `max_wall_block` | `7` | ≥ 3 | The largest wall block allowed when the recipe has no `max_block(wall)` rule. |
| `extra_paths` | `0` | ≥ 0 | Paths dug after every rule holds, for a more open maze. Each one must keep every rule. |
| `search_radius` | `16` | ≥ 6 | Each path is searched within this many tiles of its target. Larger allows longer detours, at some cost in speed. |
| `max_failures` | `80` | ≥ 1 | Failed digs in a row before an attempt gives up. |
| `attempts` | `6` | ≥ 1 | Fresh starts before generation fails. Strict run rules on large mazes sometimes need four or five; each costs as much time as a whole maze. |

**How `grow` meets each rule**

| Rule | How it is met |
|---|---|
| `connected`, `max_dead_ends` | By construction: both ends of every path attach to existing corridors. |
| `min_wall_thickness(t)` | By construction: paths cross only wall more than `t` tiles from any corridor. |
| `max_block(corridor, 2)`, `no_diagonal_contact` | Checked on every path (corridors are always one tile wide). |
| `max_block(wall, k)` | Paths are dug into every block that is too big. |
| `max_straight_run`, `max_corridor_length` | Overlong corridors get a junction: a straight bridge or a branch. |
| `min_loops`, `min_junction_share`, `walkable_fraction.min` | More paths are dug until they hold. |
| `walkable_fraction.max` | Checked: no path may cross it. |
| `mirror_symmetric` | Every path is mirrored when `topography.mirror` is set. |

**Limits:**

- `grow` makes one-tile corridors only (`corridor_width` is a lattice setting).
- `max_block(wall, k)` must be at least `2 × thickness + 1`: a path through a block needs `thickness` wall on
  each side. This is checked before generating.
- Curved and blob shapes are filled as far as paths reach, so the maze's outline can be a bit smaller than the shape.
- **Speed:** about 0.1–0.3 s for 31×31 and 2–10 s around 50×55. At 101×101 it takes 5–8 s without run rules;
  with `organic`'s run rules it is 5–30 s, and more when a seed needs several attempts. Higher `noise`,
  `depth_bonus` and `search_radius` make every path slower to find. The lattice takes under 1 s at any size.
- Rectangles and ellipses succeeded for every seed tested at the starter sizes. On small blobs with strict run rules
  (`max_straight_run = 9`, `max_corridor_length = 16`), about 1 seed in 12 fails with an error naming the rule.
  When you leave out `--maze-seed`, a seed that fails is replaced by another random one, and
  `mazes generate --count` reports a failed seed and goes on. An experiment stops at a failed run, naming the seed.

---

## `[[rules]]`

Each `[[rules]]` table adds one requirement. Rules look only at tiles, never at pellets or the start. For example:

```toml
[[rules]]
rule = "max_block"
tile = "wall"
size = 5
```

The three **hard rules** always apply to generated mazes; you don't need to list them:

| Rule | Meaning |
|---|---|
| `size_bounds` | Height and width are 5..101. |
| `connected` | All corridors form one connected region. |
| `enclosed` | No corridor tile touches void or the grid edge, not even diagonally, so every maze has walls around it. |

**Optional rules**

| Rule | Parameters | Meaning |
|---|---|---|
| `max_block` | `tile`: `corridor`, `wall` or `void`; `size`: integer ≥ 2 | No `size`×`size` square made entirely of that tile. `corridor, 2` means one-tile-wide corridors. `wall, 5` means no wall is 5 or more tiles thick in both directions. |
| `min_wall_thickness` | `size`: integer ≥ 2 | Every wall between corridors is at least `size` thick in both directions. `2` forbids one-tile walls, which look odd in an arcade-style maze. More precisely, every wall tile lies inside a `size`×`size` square with no corridor in it. Void, the outside of the grid and ghost-house tiles count as part of that square, so the outer border and the ghost-house walls may be one tile thick, as in the original. `classic` meets `size = 2`. |
| `no_diagonal_contact` | none | No two corridor tiles that touch only at a corner. |
| `max_dead_ends` | `count`: integer ≥ 0 | At most `count` dead ends (corridor tiles with a single neighbour). `0` means none. |
| `max_straight_run` | `length`: integer ≥ 2 | No straight stretch longer than `length` tiles without a junction. Long stretches give no choices. |
| `max_corridor_length` | `length`: integer ≥ 2 | No choice-free corridor longer than `length` tiles, counting turns, from one junction or dead end to the next. Catches long winding corridors that `max_straight_run` misses. |
| `min_junction_share` | `share`: 0..1 | At least this share of corridor tiles are junctions (3 or 4 neighbours). |
| `min_loops` | `count`: integer ≥ 0 | At least this many independent loops (edges − tiles + regions). |
| `walkable_fraction` | `min` (default 0), `max` (default 1): 0..1 | Corridor tiles as a share of the maze area. The area is every tile that isn't void, so after outer-wall trimming it is the corridors plus their visible walls. |
| `mirror_symmetric` | `axis`: `horizontal`, `vertical` or `both` | Corridors are unchanged by that mirror. Needs `topography.mirror` set to the same axis or `both`. |

**How the lattice generator meets each rule** (for `grow`, see [its own table](#the-grow-generator))

| Rule | How it is met |
|---|---|
| `enclosed`, `connected` | By construction. |
| `max_block(corridor, k)` with k > `corridor_width`, `no_diagonal_contact` | By construction, because parallel lines are at least `corridor_width + 1` apart. |
| `min_wall_thickness(k)` | By construction, when `spacing` min ≥ `k + corridor_width`: every wall between two lines is then at least `k` thick. |
| `mirror_symmetric` | By construction, when `topography.mirror` covers the axis. |
| `max_dead_ends` | Repaired: a segment is added at each dead end, joining two dead ends where possible. A dead end with nowhere to go is removed. |
| `max_block(wall, k)` | Repaired: a segment is added through the thick wall, or a removed node is brought back. |
| `max_straight_run`, `max_corridor_length` | Repaired: a branch is added near the middle. If no branch is possible, a segment is cut, as long as the maze stays connected. |
| `min_loops`, `min_junction_share`, `walkable_fraction.min` | Repaired by adding segments. |
| `walkable_fraction.max` | Only checked. Lower it with a larger `spacing` or fewer `extra_loops`. |
| `max_block(void, k)` | Only checked; it depends on the shape alone. |

**Limits checked before generating.** These combinations can never work, so they fail at once with a suggested fix:

- `max_block(wall, k)` needs `spacing` max ≤ `k + corridor_width − 1`.
- `max_straight_run(L)` and `max_corridor_length(L)` need `spacing` max ≤ `L − 1` (with one-tile corridors).
- `max_block(corridor, k)` needs `k > corridor_width`.
- `min_wall_thickness(k)` needs `spacing` min ≥ `k + corridor_width`. For example, one-tile corridors with
  two-tile walls need `spacing = [3, …]`.
- `mirror_symmetric(axis)` needs `topography.mirror` to be that axis or `both`.

---

## `[content.pellets]`

| `placer` | Extra keys | Meaning |
|---|---|---|
| `all_corridors` | none | A pellet on every corridor tile except the start. |
| `density` | `p` (default 0.5), in (0, 1] | Each corridor tile holds a pellet with probability `p`. |
| `exclude_near_start` | `distance` (default 3), integer ≥ 0 | Every corridor tile more than `distance` steps from the start. |

The start tile never has a pellet. There are no power pellets.

## `[content.start]`

| `placer` | Extra keys | Meaning |
|---|---|---|
| `center` | none | The corridor tile closest to the centre of the grid. |
| `random` | none | A random corridor tile. |
| `layout` | `path` (default: the shape's `path`) | The corridor tile closest to the `P` of a layout file. |

## `[content.ghosts]`

| `placer` | Extra keys | Meaning |
|---|---|---|
| `random` | `count` (default 0), `min_distance` (default 10) | `count` distinct corridor tiles at least `min_distance` steps (BFS) from the start. |

Each spawn gets one ghost (Blinky, the red ghost that chases Pac-Man), and ghost *i* starts on spawn *i*. A spawn
is an ordinary corridor tile: it may hold a pellet, and it is marked with a dim ghost sticker. Spawns come from
their own seed stream, so the count never changes the corridors, the start or the pellets, and a larger count only
adds spawns (the first ones stay put). Every starter recipe has `count = 1`; without this table a recipe has no
ghosts. `--ghosts N` on any command replaces the count, and `--ghosts 0` plays without ghosts.

---

## Changing a recipe from the command line: `--maze-set`

`--maze-set KEY=VALUE` changes one value of a recipe for a single command, without editing the file. It can be
repeated, and the overrides are applied in order.

| Key | Example | Effect |
|---|---|---|
| `size` | `size=41x45`, `size=41`, `size=11x21..41x51` | Height × width, a square, or a range from smallest to largest. |
| `size.height`, `size.width` | `size.height=41`, `size.width=[21,51]` | One dimension, fixed or a range. |
| `name`, `description` | `name=test` | |
| `shape.<key>` | `shape.kind=blob`, `shape.fill=0.5` | Setting `kind` clears the other shape keys. |
| `topography.<key>` | `topography.straightness=-0.5`, `topography.spacing=[2,3]` | Setting `generator` clears the others. |
| `rules.<rule>.<param>` | `rules.max_dead_ends.count=2` | Changes the rule, or adds it if the recipe doesn't have it. |
| `rules.max_block.<tile>.<param>` | `rules.max_block.wall.size=4` | `max_block` is picked by its tile. |
| `rules.<rule>=off` | `rules.max_dead_ends=off`, `rules.max_block.wall=off` | Removes the rule. |
| `content.pellets.<key>`, `content.start.<key>`, `content.ghosts.<key>` | `content.pellets.placer=density`, `content.ghosts.min_distance=15` | Setting `placer` clears the other keys. |

Values are read as TOML (`3`, `0.25`, `true`, `[2, 4]`, `"text"`), and anything else as plain text.
Example:

```powershell
python -m pacman_otm simulate --maze open-lattice --maze-set size=51x51 --maze-set topography.straightness=0.8 --visualize
```

---

## Recipes that come with the project

| Recipe | Idea | Key settings |
|---|---|---|
| `open-lattice` | Generic loopy maze, no dead ends. | 31×31, `extra_loops = 0.15`, no dead ends, one-tile corridors, walls < 5. |
| `classic-like` | Arcade feel. | 31×28, `mirror = "horizontal"`, `spacing = [3, 5]`, `min_wall_thickness = 2`, `straightness = 0.5`, `max_corridor_length = 14`. |
| `blob-lattice` | Organic outline, varying size. | 50..70 blob (`fill = 0.8`), `spacing = [3, 6]`, `node_dropout = 0.1`, walls 2..6 thick, runs ≤ 15, corridors ≤ 20. |
| `twisty` | Winding and tree-like. | `straightness = -0.8`, `extra_loops = 0.03`, up to 6 dead ends, random start. |
| `wide-halls` | Two-tile corridors. | `corridor_width = 2`, `spacing = [3, 5]`. |
| `organic` | Winding, hand-made-looking arcade maze. | `generator = "grow"`, 25..41 sizes, walls ≥ 2, wall blocks < 7, runs ≤ 12, corridors ≤ 20, no dead ends. |
| `grotto` | A mirrored, oval cave grown from its middle. | `grow` on an ellipse, `start = "center"`, `noise = 8`, `depth_bonus = 20`, `extra_paths = 4`, mirrored left-right, walls ≥ 2, corridors ≤ 16. About 1.5 s per maze. |

They are good starting points: copy one and change it.

---

## Recipe ideas

- **Organic arcade:** start from `organic`. For a more open maze use `extra_paths = 8`; for wider wall
  blocks use `max_block(wall, 9)`; for a symmetric maze use `mirror = "horizontal"`.
- **Arcade walls:** `spacing = [3, 5]` with `min_wall_thickness(2)` and `max_block(wall, 5)`: every wall 2 to 4 thick.
- **Dense and choiceful:** `spacing = [2, 3]`, `extra_loops = 0.3`, `min_junction_share = 0.2`.
- **Long halls with few choices:** `straightness = 1`, `extra_loops = 0.05`, and no `max_straight_run` rule.
- **Labyrinth:** `extra_loops = 0`, `straightness = -0.6`, no `max_dead_ends` rule.
- **Islands:** `node_dropout = 0.3`, `max_block(wall, 6)`, `spacing = [2, 4]`.
- **Symmetric blob:** `shape.kind = "blob"`, `shape.mirror = "horizontal"`, `topography.mirror = "horizontal"`.
- **Sparse pellets for search tests:** `[content.pellets] placer = "density"`, `p = 0.15`.
- **Many sizes in one experiment:** `height = [11, 51]`, `width = [11, 51]`, so controllers are tested on small and
  large mazes alike.

---

## Wide corridors

The structural rules and metrics (dead ends, junctions, loops, runs) count tiles. That suits one-tile corridors. In a
2-wide hall every tile has at least 3 neighbours, so it counts as a junction, and every 2×2 block counts as a loop.
For `corridor_width ≥ 2`, use the shape rules (`max_block`, `no_diagonal_contact`, `walkable_fraction`) and leave
out the degree-based ones.

---

## When generation fails

Errors name the field or rule and usually suggest a fix.

| Message starts with | What to do |
|---|---|
| `my-maze.toml: topography.spacing: …` | A value has the wrong type or range; the message says which. |
| `rules[2]: unknown rule 'max_blok'` | A typo; the message lists the known rules. |
| `max_block(tile=wall, size=4) needs topography.spacing max <= 4` | A limit checked before generating (see [Limits](#rules)). |
| `… cannot be met (e.g. at (7, 10)): …` | The repairs ran out of moves for this seed and shape. Relax the rule, lower `spacing`, or make the maze larger. A blob mirrored both ways (`mirror = "both"`) fails like this for about 1% of seeds. |
| `Repairs did not settle within 200 rounds` | Two rules work against each other, e.g. a very short `max_corridor_length` together with `max_dead_ends = 0`. Relax one of them. |

An experiment stops at the first maze that can't be generated and reports its seed, rather than skipping it. That
keeps the maze sequence the same for every controller.
