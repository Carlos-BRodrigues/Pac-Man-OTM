from collections.abc import Sequence

from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.ghosts import CAUGHT_REASON, GhostState
from pacman_otm.simulation.speeds import ARCADE, SpeedRules
from pacman_otm.simulation.state import SimulationState

Position = tuple[int, int]


class SimulationEngine:
    """
    The game rules. Executes the moves it is given and records every tick; it
    never chooses a move, for Pac-Man or for a ghost.

    Time runs in ticks. A mover is on a whole tile plus a progress toward the
    next one (see simulation/speeds.py), and is asked for a decision only at a
    tile centre, so every controller still makes one decision per tile:

    - Pac-Man needs a decision when he has no heading (at a tile centre).
    - A ghost needs one when it has no heading (at its spawn) or has not yet
      chosen the exit of the tile it is moving to (`next_heading`): ghosts
      decide one tile ahead, and keep moving through tile centres without stopping.

    A tick: decisions (decide_pacman / decide_ghost), then advance(): everyone
    moves by its speed, arrivals happen, Pac-Man eats the pellet he arrives on
    (and pauses), and he is caught if a ghost occupies his tile or they swap
    tiles. Being caught beats eating the last pellet.

    `ghosts` are the kinds of the ghosts in this run, one per ghost spawn of the
    maze in order (ghost i starts on spawn i); () plays without ghosts.
    """

    def __init__(self, maze: Maze, ghosts: Sequence[str] = (), speeds: SpeedRules = ARCADE):

        if len(ghosts) > len(maze.ghost_spawns):
            raise ValueError(
                f"{len(ghosts)} ghost(s) but the maze '{maze.name}' has only "
                f"{len(maze.ghost_spawns)} ghost spawn(s)."
            )

        self.maze = maze
        self.ghost_kinds: tuple[str, ...] = tuple(ghosts)
        self.speeds = speeds

        self.reset()

    def reset(self) -> None:

        self.state = SimulationState(self.maze, self.speeds.move_cost)
        self.state.ghosts = tuple(
            GhostState(kind=kind, position=spawn)
            for kind, spawn in zip(self.ghost_kinds, self.maze.ghost_spawns)
        )

        # Complete simulation history: one state per tick, and Pac-Man's decision
        # in each tick (None in ticks where he was moving and not asked).
        self.states: list[SimulationState] = [self.state.copy()]
        self.actions: list[Action | None] = []

        self._tick_action: Action | None = None
        self._pacman_decided = False

    # Decisions

    def pacman_needs_decision(self) -> bool:
        return not self.state.terminated and self.state.pacman_heading is None and not self._pacman_decided

    def ghost_needs_decision(self, index: int) -> bool:
        ghost = self.state.ghosts[index]
        return not self.state.terminated and (ghost.heading is None or ghost.next_heading is None)

    def decide_pacman(self, action: Action) -> None:
        """
        Pac-Man's move out of his tile. Into a wall he stays where he is, keeps no
        progress beyond the tile centre (a pellet pause still counts), and is asked
        again next tick.
        """
        if not self.pacman_needs_decision():
            raise RuntimeError("Pac-Man is not due a decision this tick.")

        self._tick_action = action
        self._pacman_decided = True

        if self.maze.is_walkable(self.maze.get_destination(self.state.pacman_position, action)):
            self.state.pacman_heading = action
        else:
            self.state.pacman_progress = min(self.state.pacman_progress, 0)

    def decide_ghost(self, index: int, action: Action) -> None:
        """
        A ghost's decision. At the spawn: its first move, any open direction.
        Otherwise: the exit of the tile it is moving to, which must be open and
        must not reverse unless that tile is a dead end. A controller that breaks
        the rule is a bug, so it raises instead of being corrected.
        """
        if not self.ghost_needs_decision(index):
            raise RuntimeError(f"Ghost {index} is not due a decision this tick.")

        ghost = self.state.ghosts[index]

        if ghost.heading is None:
            if action not in self.maze.get_valid_movements(ghost.position):
                raise RuntimeError(
                    f"Ghost {index} ({ghost.kind}) at {ghost.position} cannot move {action.value}: wall."
                )

            updated = GhostState(kind=ghost.kind, position=ghost.position, heading=action, progress=ghost.progress)
        else:
            tile = self.maze.get_destination(ghost.position, ghost.heading)
            exits = self.maze.get_valid_movements(tile)

            if action not in exits:
                raise RuntimeError(
                    f"Ghost {index} ({ghost.kind}) cannot leave {tile} {action.value}: wall."
                )

            if action == ghost.heading.reverse and len(exits) > 1:
                raise RuntimeError(
                    f"Ghost {index} ({ghost.kind}) cannot reverse at {tile} "
                    f"({ghost.heading.value} -> {action.value}) outside a dead end."
                )

            updated = GhostState(
                kind=ghost.kind,
                position=ghost.position,
                heading=ghost.heading,
                next_heading=action,
                progress=ghost.progress,
            )

        ghosts = list(self.state.ghosts)
        ghosts[index] = updated
        self.state.ghosts = tuple(ghosts)

    # Time

    def advance(self) -> SimulationState:
        """One tick of movement, pellets and collisions, after every due decision was made."""

        if self.state.terminated:
            raise RuntimeError("Simulation has already terminated.")

        if self.pacman_needs_decision():
            raise RuntimeError("Pac-Man is due a decision before the tick can run.")

        pending = [index for index in range(len(self.state.ghosts)) if self.ghost_needs_decision(index)]

        if pending:
            raise RuntimeError(f"Ghost(s) {pending} are due a decision before the tick can run.")

        state = self.state
        speeds = self.speeds
        # Where everyone was at the start of the tick, before this tick's decisions:
        # a heading chosen with leftover progress can put a mover past halfway at once.
        start = self.states[-1]
        pacman_before = start.pacman_occupied
        ghosts_before = [start.ghost_occupied(index) for index in range(len(start.ghosts))]

        arrived = False

        if state.pacman_heading is not None:
            state.pacman_progress += speeds.pacman

            if state.pacman_progress >= speeds.move_cost:
                state.pacman_position = self.maze.get_destination(state.pacman_position, state.pacman_heading)
                state.pacman_heading = None
                state.pacman_progress -= speeds.move_cost
                arrived = True

        state.ghosts = tuple(self._move_ghost(ghost) for ghost in state.ghosts)
        state.steps += 1

        if state.collect_pellet() and arrived:
            state.pacman_progress -= speeds.pellet_pause

        if self._caught(pacman_before, ghosts_before):
            state.terminated = True
            state.termination_reason = CAUGHT_REASON

        self.actions.append(self._tick_action)
        self.states.append(state.copy())
        self._tick_action = None
        self._pacman_decided = False

        return state

    def step(
        self,
        action: Action | None = None,
        ghost_actions: Sequence[Action | tuple[Action, ...] | None] = (),
    ) -> SimulationState:
        """
        Decide and advance in one call (tests and simple drivers). Each ghost gets
        an action, a tuple of actions (its first move and its next exit at the
        spawn), or None when it is not due a decision.
        """
        if action is not None:
            self.decide_pacman(action)

        if len(ghost_actions) not in (0, len(self.state.ghosts)):
            raise ValueError(
                f"Expected {len(self.state.ghosts)} ghost action(s), got {len(ghost_actions)}."
            )

        for index, ghost_action in enumerate(ghost_actions):
            for single in ghost_action if isinstance(ghost_action, tuple) else (ghost_action,):
                if single is not None:
                    self.decide_ghost(index, single)

        return self.advance()

    def _move_ghost(self, ghost: GhostState) -> GhostState:
        progress = ghost.progress + self.speeds.ghost

        if progress < self.speeds.move_cost:
            return GhostState(
                kind=ghost.kind,
                position=ghost.position,
                heading=ghost.heading,
                next_heading=ghost.next_heading,
                progress=progress,
            )

        # Through the tile centre without stopping: the exit was chosen one tile ahead.
        return GhostState(
            kind=ghost.kind,
            position=self.maze.get_destination(ghost.position, ghost.heading),
            heading=ghost.next_heading,
            progress=progress - self.speeds.move_cost,
        )

    def _caught(self, pacman_before: Position, ghosts_before: list[Position]) -> bool:
        """A ghost occupies Pac-Man's tile, or they swapped tiles this tick (passing head-on)."""

        pacman = self.state.pacman_occupied

        return any(
            ghost == pacman or (ghost == pacman_before and before == pacman)
            for ghost, before in zip(
                (self.state.ghost_occupied(index) for index in range(len(self.state.ghosts))),
                ghosts_before,
            )
        )

    def terminate(self, reason: str) -> None:
        """End the run for a reason outside the game rules (step limit, viewer closed).

        No tick is run, so the latest history entry is amended rather than a new
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

    def get_action(self, index: int) -> Action | None:
        return self.actions[index]
