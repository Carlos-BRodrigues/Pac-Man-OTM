from collections import deque
from .base import Controller


class NearestPelletBFS(Controller):
    name = "BFS nearest pellet"

    def choose_action(self, obs):
        start = obs.player
        if not obs.pellets:
            return "LEFT"
        queue = deque([start])
        parent = {start: None}
        goal = None
        while queue:
            p = queue.popleft()
            if p in obs.pellets:
                goal = p
                break
            for q in obs.maze.neighbors(p):
                if q not in parent:
                    parent[q] = p
                    queue.append(q)
        if goal is None or goal == start:
            return "LEFT"
        node = goal
        while parent[node] != start:
            node = parent[node]
        return obs.maze.action_between(start, node)
