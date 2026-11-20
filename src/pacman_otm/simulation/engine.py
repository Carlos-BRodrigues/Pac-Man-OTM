from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.state import SimulationState


class SimulationEngine:

    def __init__(self, maze: Maze):

        self.maze = maze

        self.reset()

    def reset(self) -> None:

        self.state = SimulationState(self.maze)

        # Complete simulation history
        self.states: list[SimulationState] = [self.state.copy()]

        self.actions: list[Action] = []

    def step(self, action: Action) -> SimulationState:

        if self.state.terminated:
            raise RuntimeError("Simulation has already terminated.")

        destination = self.maze.get_destination(
            self.state.pacman_position,
            action,
        )

        if self.maze.is_walkable(destination):
            self.state.pacman_position = destination

        # Every attempted action consumes one step
        self.state.steps += 1

        # Collect pellet at the resulting position
        self.state.collect_pellet()

        # Record the action and resulting state
        self.actions.append(action)
        self.states.append(self.state.copy())

        return self.state

    def get_state(self, index: int) -> SimulationState:
        return self.states[index].copy()

    def get_action(self, index: int) -> Action:
        return self.actions[index]
