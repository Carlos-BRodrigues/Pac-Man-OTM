from pacman_otm.simulation.result import SimulationResult

result = SimulationResult.load_json("results/test_replay.json")

print("Maze:", result.maze.height, result.maze.width)
print("States:", len(result.states))
print("Actions:", len(result.actions))
print("Statuses:", len(result.statuses))
print("Metrics:", result.metrics)
print("Initial state:", result.get_state(0))
print("Final state:", result.final_state)
