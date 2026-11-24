from pacman_otm.mazes.registry import resolve_maze
from pacman_otm.algorithms.graph.metric_closure import MetricClosure

maze = resolve_maze("classic")

mc = MetricClosure(maze)

mc.build_metric_closure()

print(mc.metric_closure[:1])
# print(mc.labels)
