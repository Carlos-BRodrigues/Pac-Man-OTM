import numpy as np
from collections import deque
import math
from pacman_otm.mazes.maze import Maze
from pacman_otm.algorithms.pathfinding.bfs import BreadthFirstSearch
from pacman_otm.simulation.actions import Action

Position = tuple[int, int]


class MetricClosure:

    def __init__(self, maze: Maze):
        self.maze = maze
        self.bfs = BreadthFirstSearch()
        self.metric_closure = None
        self.labels = None

        self.build_metric_closure()

    def build_metric_closure(self):
        """
        For every node run BFS and build distance matrix
        """
        start = self.maze.pacman_start
        pellets = sorted(set(self.maze.initial_pellets) - {start})
        nodes = [start, *pellets]
        V = len(nodes)

        self.labels = {nodes[i]: i for i in range(V)}

        distance_matrix = [[0 for i in range(V)] for j in range(V)]
        # distance from i to j

        def bfs(node):
            frontier = deque([node])

            visited: set[Position] = {node}
            distance_vector = {
                position: math.inf for position in self.maze.walkable_positions()
            }
            distance_vector[node] = 0

            while frontier:

                current = frontier.popleft()

                movements = self.maze.get_valid_movements(current)

                for neighbor in movements.values():

                    if neighbor in visited:
                        continue

                    visited.add(neighbor)
                    distance_vector[neighbor] = distance_vector[current] + 1
                    frontier.append(neighbor)

            return distance_vector

        for i in range(V):
            source = nodes[i]
            distance_vector = bfs(source)
            for j in range(V):
                if i == j:
                    continue
                target = nodes[j]
                distance_matrix[i][j] = distance_vector[target]

        self.metric_closure = distance_matrix
