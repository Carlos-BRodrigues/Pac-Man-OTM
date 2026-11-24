from collections.abc import Sequence

from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.ghosts import CAUGHT_REASON, GhostState
from pacman_otm.simulation.state import SimulationState


class SimulationEngine:
    """
    The game rules. Executes the moves it is given and records every state;
    it never chooses a move, for Pac-Man or for a ghost.

    `ghosts` are the kinds of the ghosts in this run, one per ghost spawn of the
    maze in order (ghost i starts on spawn i); () plays without ghosts.
    """

    def __init__(self, maze: Maze, ghosts: Sequence[str] = ()):

        if len(ghosts) > len(maze.ghost_spawns):
            raise ValueError(
                f"{len(ghosts)} ghost(s) but the maze '{maze.name}' has only "
                f"{len(maze.ghost_spawns)} ghost spawn(s)."
            )

        self.maze = maze
        self.ghost_kinds: tuple[str, ...] = tuple(ghosts)

        self.reset()

    def reset(self) -> None:

        self.state = SimulationState(self.maze)
        self.state.ghosts = tuple(
            GhostState(kind=kind, position=spawn)
            for kind, spawn in zip(self.ghost_kinds, self.maze.ghost_spawns)
        )

        # Complete simulation history
        self.states: list[SimulationState] = [self.state.copy()]

        self.actions: list[Action] = []

    def step(self, action: Action, ghost_actions: Sequence[Action] = ()) -> SimulationState:
        """
        One step: Pac-Man and every ghost move at the same time. Pac-Man is
        stopped by walls; a ghost must make a legal move (see _move_ghost).
        Pac-Man is caught when a ghost ends on his tile or they swap tiles
        head-on; being caught overrides eating the last pellet.
        """

        if self.state.terminated:
            raise RuntimeError("Simulation has already terminated.")

        if len(ghost_actions) != len(self.state.ghosts):
            raise ValueError(
                f"Expected {len(self.state.ghosts)} ghost action(s), got {len(ghost_actions)}."
            )

        pacman_before = self.state.pacman_position
        ghosts_before = self.state.ghosts

        destination = self.maze.get_destination(pacman_before, action)

        if self.maze.is_walkable(destination):
            self.state.pacman_position = destination

        self.state.ghosts = tuple(
            self._move_ghost(index, ghost, ghost_action)
            for index, (ghost, ghost_action) in enumerate(zip(ghosts_before, ghost_actions))
        )

        # Every attempted action consumes one step
        self.state.steps += 1

        # Collect pellet at the resulting position
        self.state.collect_pellet()

        if self._caught(pacman_before, ghosts_before):
            self.state.terminated = True
            self.state.termination_reason = CAUGHT_REASON

        # Record the action and resulting state
        self.actions.append(action)
        self.states.append(self.state.copy())

        return self.state

    def _move_ghost(self, index: int, ghost: GhostState, action: Action) -> GhostState:
        """
        The ghost movement rule: a ghost moves every step to a walkable neighbour
        and never reverses, except at a dead end where reversing is the only move.
        A controller that breaks it is a bug, so it raises instead of being corrected.
        """
        exits = self.maze.get_valid_movements(ghost.position)

        if action not in exits:
            raise RuntimeError(
                f"Ghost {index} ({ghost.kind}) at {ghost.position} cannot move {action.value}: wall."
            )

        if ghost.direction is not None and action == ghost.direction.reverse and len(exits) > 1:
            raise RuntimeError(
                f"Ghost {index} ({ghost.kind}) at {ghost.position} cannot reverse "
                f"({ghost.direction.value} -> {action.value}) outside a dead end."
            )

        return GhostState(kind=ghost.kind, position=exits[action], direction=action)

    def _caught(self, pacman_before, ghosts_before: tuple[GhostState, ...]) -> bool:
        pacman = self.state.pacman_position

        return any(
            ghost.position == pacman
            or (ghost.position == pacman_before and before.position == pacman)
            for ghost, before in zip(self.state.ghosts, ghosts_before)
        )

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
