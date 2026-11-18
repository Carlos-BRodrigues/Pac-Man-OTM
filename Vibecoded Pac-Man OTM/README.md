# Pac-Man OTM v2

Grid-based Pac-Man foundation for graph and optimization experiments.

## Install and run

Windows PowerShell:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

macOS/Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

Controls: arrows/WASD move, M toggles BFS, R restarts, Esc quits.

## Maps
Edit `maps/custom_map.py`. Values: 0=void, 1=wall, 2=corridor. Rows are top-to-bottom and cells left-to-right. Short rows are padded with void on the right; use leading zeroes to indent. Pellets are a separate set of `(x,y)` positions.

Tunnel example: `TUNNELS = [((0, 3), (10, 3))]`. Endpoints must be corridor tiles on opposite left/right edges in the same row, or top/bottom edges in the same column. Tunnel links are bidirectional graph edges.

## Random connected maps
```python
from maps.generation import generate_connected_maze
maze = generate_connected_maze(20, 15, corridor_fraction=0.55, min_edges=180, min_average_degree=1.8, seed=42)
```
The generator grows a connected corridor set, then opens cells with at least two corridor neighbors to create cycles and increase average degree. It verifies connectivity, minimum edge count and requested average degree, and raises an error if the requested bounds cannot be met. To launch a generated map, set `RANDOM_GENERATION = True` in `maps/custom_map.py`; dimensions, graph constraints, seed and random pellet fraction are configured there. Set it back to `False` to use the hand-authored map. Random mode currently generates pellet positions automatically; custom mode keeps your manually specified `PELLETS` set.

## Architecture
- `game/model.py`: tile types, map topology, neighbors, tunnels, graph connectivity and degree.
- `game/simulation.py`: discrete transitions and simulation clock; independent of Pygame.
- `game/state.py`: state and statistics.
- `game/rendering.py`: drawing, smooth wall joins and animated Pac-Man.
- `game/app.py`: Pygame input/rendering adapter.
- `algorithms/base.py`: common controller interface.
- `algorithms/bfs.py`: nearest-pellet BFS baseline.
- `maps/custom_map.py`: editable map, start, pellets and tunnels.
- `maps/generation.py`: connected random maze generator.

## Time and movement
Movement decisions occur at discrete `MOVE_INTERVAL` steps. Rendering interpolates between tile centers for smooth motion. The simulation records wall-clock elapsed time, simulated game time, and algorithm computation time separately. Controller computation is measured with a high-resolution wall clock and excluded from simulated game time, so a slower algorithm does not silently consume more in-game time.

## Current scope and caveats
No ghosts yet. BFS targets the nearest remaining pellet and replans; it is not a globally optimal pellet-collection solver. Random map generation currently creates connected topology only, not pellet layouts or tunnels.
