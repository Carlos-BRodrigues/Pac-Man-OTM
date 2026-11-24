from pacman_otm.mazes.maze import Maze, Position
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.state import SimulationState


def ghost_step(
    maze: Maze,
    ghost_pos: Position,
    ghost_dir: tuple[int, int],
    target_pos: Position,
) -> tuple[Position, tuple[int, int]]:
    """Deterministic greedy pursuit f(g_t, d_t, v_t) used by each Blinky agent."""
    valid_moves = list(maze.get_valid_movements(ghost_pos).values())
    if not valid_moves:
        return ghost_pos, (0, 0)

    reverse_pos = (ghost_pos[0] - ghost_dir[0], ghost_pos[1] - ghost_dir[1])
    if len(valid_moves) > 1:
        candidates = [w for w in valid_moves if w != reverse_pos]
    else:
        candidates = valid_moves

    # Maze.MOVEMENTS is ordered UP, LEFT, DOWN, RIGHT, preserving tie-break order.
    best_pos = min(
        candidates,
        key=lambda w: (w[0] - target_pos[0]) ** 2 + (w[1] - target_pos[1]) ** 2,
    )
    new_dir = (best_pos[0] - ghost_pos[0], best_pos[1] - ghost_pos[1])
    return best_pos, new_dir


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

        prev_pacman = self.state.pacman_position
        destination = self.maze.get_destination(prev_pacman, action)

        if self.maze.is_walkable(destination):
            self.state.pacman_position = destination

        # Simultaneous ghost transitions using v_t (prev_pacman) and phase phi_t = t mod m
        prev_ghosts = self.state.ghost_positions
        prev_dirs = self.state.ghost_directions

        if prev_ghosts and self.state.steps % self.state.ghost_period == 0:
            next_positions: list[Position] = []
            next_directions: list[tuple[int, int]] = []
            for prev_g, prev_d in zip(prev_ghosts, prev_dirs):
                next_g, next_d = ghost_step(self.maze, prev_g, prev_d, prev_pacman)
                next_positions.append(next_g)
                next_directions.append(next_d)
            self.state.ghost_positions = tuple(next_positions)
            self.state.ghost_directions = tuple(next_directions)

        # Every attempted action consumes one step
        self.state.steps += 1

        # Check cell collision (v_{t+1} == g^{(i)}_{t+1}) and edge crossing for every ghost
        for prev_g, curr_g in zip(prev_ghosts, self.state.ghost_positions):
            same_cell = self.state.pacman_position == curr_g
            edge_swap = (
                self.state.pacman_position == prev_g
                and prev_pacman == curr_g
            )
            if same_cell or edge_swap:
                self.state.terminated = True
                self.state.termination_reason = "caught_by_ghost"
                self.actions.append(action)
                self.states.append(self.state.copy())
                return self.state

        # Collect pellet at the resulting position
        self.state.collect_pellet()

        # Record the action and resulting state
        self.actions.append(action)
        self.states.append(self.state.copy())

        return self.state

    def terminate(self, reason: str) -> None:
        """End the run for a reason outside the game rules (step limit, viewer closed).

        No action is taken, so the latest history entry is amended rather than a new
        one appended: len(states) == len(actions) + 1 must keep holding.
        If the run has already ended, the original reason is kept.
        """

        if self.state.terminated:
            return

        self.state.terminated = True
        self.state.termination_reason = reason
        self.states[-1] = self.state.copy()

    def get_state(self, index: int) -> SimulationState:
        return self.states[index].copy()

    def get_action(self, index: int) -> Action:
        return self.actions[index]