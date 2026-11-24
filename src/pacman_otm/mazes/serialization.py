"""Maze <-> plain dict, shared by simulation results and experiment summaries."""

from typing import Any

from pacman_otm.mazes.maze import Maze
from pacman_otm.mazes.origin import MazeOrigin


def maze_to_dict(maze: Maze) -> dict[str, Any]:
    data: dict[str, Any] = {
        "origin": maze.origin.to_dict() if maze.origin is not None else None,
        "dimensions": [maze.height, maze.width],
        "topography": maze.topography.tolist(),
        "pacman_start": list(maze.pacman_start),
        "initial_pellets": [
            list(position) for position in sorted(maze.initial_pellets)
        ],
    }
    if maze.ghost_start is not None:
        data["ghost_start"] = list(maze.ghost_start)
        data["ghost_period"] = maze.ghost_period
    return data


def maze_from_dict(data: dict[str, Any]) -> Maze:
    origin_data = data.get("origin")
    ghost_start_data = data.get("ghost_start")

    return Maze(
        topography=data["topography"],
        pacman_start=tuple(data["pacman_start"]),
        pellets={tuple(position) for position in data["initial_pellets"]},
        origin=MazeOrigin.from_dict(origin_data) if origin_data is not None else None,
        ghost_start=tuple(ghost_start_data) if ghost_start_data is not None else None,
        ghost_period=data.get("ghost_period", 1),
    )