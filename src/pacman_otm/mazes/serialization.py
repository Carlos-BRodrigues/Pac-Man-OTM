"""Maze <-> plain dict, shared by simulation results and experiment summaries."""

from typing import Any

from pacman_otm.mazes.maze import Maze
from pacman_otm.mazes.origin import MazeOrigin


def maze_to_dict(maze: Maze) -> dict[str, Any]:
    return {
        "origin": maze.origin.to_dict() if maze.origin is not None else None,
        "dimensions": [maze.height, maze.width],
        "topography": maze.topography.tolist(),
        "pacman_start": list(maze.pacman_start),
        "initial_pellets": [
            list(position) for position in sorted(maze.initial_pellets)
        ],
    }


def maze_from_dict(data: dict[str, Any]) -> Maze:
    origin_data = data.get("origin")

    return Maze(
        topography=data["topography"],
        pacman_start=tuple(data["pacman_start"]),
        pellets={tuple(position) for position in data["initial_pellets"]},
        origin=MazeOrigin.from_dict(origin_data) if origin_data is not None else None,
    )
