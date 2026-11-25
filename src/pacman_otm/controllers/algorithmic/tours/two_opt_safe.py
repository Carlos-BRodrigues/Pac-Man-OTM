import math
from itertools import islice
from typing import Any

import numpy as np

from pacman_otm.algorithms.graph.dead_ends import dead_end_branches
from pacman_otm.algorithms.pathfinding.no_reverse import NoReverseSearch
from pacman_otm.algorithms.pathfinding.safe_route import SafeRoutes, safe_routes
from pacman_otm.algorithms.tours.nearest_neighbour import nearest_neighbour_tour
from pacman_otm.algorithms.tours.tour import tour_length
from pacman_otm.algorithms.tours.two_opt import two_opt
from pacman_otm.algorithms.safety.arrival import (
    earliest_ghost_ticks,
    ghost_occupancy_ticks,
    is_safe,
    pacman_occupancy_ticks,
)
from pacman_otm.controllers.algorithmic.tours.two_opt import TwoOptController
from pacman_otm.controllers.controller import ControllerStatus
from pacman_otm.mazes.maze import Maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.state import SimulationState

Position = tuple[int, int]


class TwoOptSafeController(TwoOptController):
    """
    The 2-opt tour with a tactical safety layer (Level 2, next.md).

    Danger is a race in ticks: a tile is safe when Pac-Man occupies it more than
    MARGIN ticks before any ghost can (algorithms/safety/arrival.py, exact for
    the run's speeds and pellet pauses). While the next HORIZON tiles of the
    tour are safe, Pac-Man follows the tour.

    Otherwise one safe-route search (algorithms/pathfinding/safe_route.py) gives
    every tile he can reach without losing a race, and he heads for the first of:
    the current target; the detour pellet he was already heading for; the first
    remaining pellet in tour order. A detour never advances the tour, so the
    target stays pending and is re-pathed to once the way is safe again.

    If no pellet is safely reachable he escapes: to the safely reachable tile
    outside dead-end branches with the largest lead over the ghosts. A goal
    inside a branch (algorithms/graph/dead_ends.py) is taken only if he can get
    there and back out past the branch entrance before a ghost can occupy it.

    Back on the tour after a detour, the old order may be poor (pellets skipped,
    Pac-Man elsewhere), so the rest of the tour is re-planned with nearest
    neighbour + 2-opt from where he stands (`replan`, on by default), when a
    pellet was deferred or the detour was long, at most every REPLAN_COOLDOWN decisions.
    """

    HORIZON = 6
    MARGIN = 1
    # A detour this long (decisions off the tour) is worth a re-plan even if no pellet was deferred.
    REPLAN_MIN_DETOUR = 4
    # Decisions between re-plans at least. 2-opt is the expensive part (about 150 ms on a
    # 1000-pellet maze); 20 was the best of 10/20/40 on the avoidance benchmark.
    REPLAN_COOLDOWN = 20

    def __init__(self, maze: Maze, replan: bool = True) -> None:
        self.replan_enabled = replan
        self.ghost_search = NoReverseSearch(maze)
        self.branches = dead_end_branches(maze)
        super().__init__(maze)

    def reset(self) -> None:
        super().reset()
        # Decisions where the tour's next tiles were unsafe, and how they were answered.
        self.flee_count = 0
        self.detours = 0
        self.escapes = 0
        self.cornered = 0
        self.replans = 0
        self.last_replan_length: float | None = None
        # The detour in progress: decisions off the tour, and whether a pellet was deferred.
        self._detour_decisions = 0
        self._deferred = False
        self._decisions_since_replan = self.REPLAN_COOLDOWN
        self._plan_stale = False
        self._detour_goal: Position | None = None

    def describe(self) -> dict[str, Any]:
        return {
            **super().describe(),
            "avoidance": {
                "horizon": self.HORIZON,
                "margin": self.MARGIN,
                "flee_count": self.flee_count,
                "detours": self.detours,
                "escapes": self.escapes,
                "cornered": self.cornered,
                "replan": self.replan_enabled,
                "replans": self.replans,
                "last_replan_length": self.last_replan_length,
            },
        }

    def select_action(self, state: SimulationState) -> Action:

        if self._plan_stale and self.current_target in state.remaining_pellets:
            self._repath(state)

        self._plan_stale = False
        action = super().select_action(state)

        if not state.ghosts:
            return action

        ghost_ticks = earliest_ghost_ticks(
            ghost_occupancy_ticks(self.ghost_search, self.maze, ghost, state.speeds) for ghost in state.ghosts
        )

        self._decisions_since_replan += 1
        safe = self._tour_is_safe(state, action, ghost_ticks)

        if safe and self._detour_decisions:
            if self._should_replan():
                self._replan(state)
                action = super().select_action(state)
                safe = self._tour_is_safe(state, action, ghost_ticks)

            self._detour_decisions = 0
            self._deferred = False

        if safe:
            self._detour_goal = None
            return action

        self._detour_decisions += 1
        self.flee_count += 1
        self._plan_stale = True
        routes = safe_routes(
            self.maze,
            state.pacman_position,
            state.pacman_progress,
            state.remaining_pellets,
            state.speeds,
            ghost_ticks,
            self.MARGIN,
        )
        goal = self._safe_goal(state, routes, ghost_ticks)

        if goal is None:
            return self._escape_action(state, routes, ghost_ticks)

        if goal != self.current_target:
            self._deferred = True

            if goal != self._detour_goal:
                self.detours += 1

            self._detour_goal = goal

        self._publish_route(routes, goal)
        return routes.route_to(goal)[0]

    def _tour_is_safe(self, state: SimulationState, action: Action, ghost_ticks: dict[Position, int]) -> bool:
        return self._moves_are_safe(
            state, [action, *islice(self.current_plan, self.HORIZON - 1)], ghost_ticks,
        ) and self._tour_target_is_no_trap(state, action, ghost_ticks)

    def _should_replan(self) -> bool:
        return (
            self.replan_enabled
            and (self._deferred or self._detour_decisions >= self.REPLAN_MIN_DETOUR)
            and self._decisions_since_replan >= self.REPLAN_COOLDOWN
        )

    def _replan(self, state: SimulationState) -> None:
        """The rest of the tour again, nearest neighbour + 2-opt, from Pac-Man's tile."""

        nodes = self.closure.nodes
        remaining = [index for index in self.order[1:] if nodes[index] in state.remaining_pellets]
        from_here = self.pathfinder.distances_from(self.maze, state.pacman_position)

        # Node 0 is Pac-Man's tile; the rest are the remaining pellets, with closure distances.
        distances = np.zeros((len(remaining) + 1, len(remaining) + 1))
        distances[1:, 1:] = self.closure.distances[np.ix_(remaining, remaining)]
        distances[0, 1:] = distances[1:, 0] = [from_here.get(nodes[index], math.inf) for index in remaining]

        local = two_opt(distances, nearest_neighbour_tour(distances))
        self._set_remaining_order(state, [remaining[node - 1] for node in local[1:]])
        self.replans += 1
        self.last_replan_length = tour_length(distances, local)
        self._decisions_since_replan = 0

    def _safe_goal(
        self,
        state: SimulationState,
        routes: SafeRoutes,
        ghost_ticks: dict[Position, int],
    ) -> Position | None:
        """The pellet to head for when the tour's way is unsafe: see the class docstring for the order."""

        candidates = [self.current_target, self._detour_goal]
        candidates += (self.closure.nodes[index] for index in self.order[self.order_index:])

        for goal in candidates:
            if (
                goal is not None
                and goal in state.remaining_pellets
                and routes.reachable(goal)
                and self._no_trap(goal, routes.occupancy[goal], state, ghost_ticks)
            ):
                return goal

        return None

    def _escape_action(self, state: SimulationState, routes: SafeRoutes, ghost_ticks: dict[Position, int]) -> Action:
        """
        No pellet is safely reachable: walk toward the safe tile with the largest
        lead over the ghosts, outside dead-end branches when there is one. Ties go
        to the tile reached first. Cornered (nothing safe): Level 1's flee.
        """
        safe = [tile for tile in routes.units if tile != state.pacman_position]
        open_tiles = [tile for tile in safe if tile not in self.branches]

        if not safe:
            self.cornered += 1
            return self._flee_action(state, ghost_ticks)

        def lead(tile: Position) -> float:
            ghost = ghost_ticks.get(tile)
            return math.inf if ghost is None else ghost - routes.occupancy[tile]

        goal = min(open_tiles or safe, key=lambda tile: (-lead(tile), routes.units[tile], tile))
        self.escapes += 1
        self._deferred = True
        self._publish_route(routes, goal)
        return routes.route_to(goal)[0]

    def _no_trap(self, goal: Position, tick: int, state: SimulationState, ghost_ticks: dict[Position, int]) -> bool:
        """Outside a dead-end branch, or there (at `tick`) and back out past its entrance before any ghost."""

        branch = self.branches.get(goal)

        if branch is None:
            return True

        speeds = state.speeds
        pause = speeds.pellet_pause if goal in state.remaining_pellets else 0
        back = -(-(branch.depth * speeds.move_cost + pause) // speeds.pacman)
        return is_safe(tick + back, ghost_ticks.get(branch.entrance), self.MARGIN)

    def _tour_target_is_no_trap(self, state: SimulationState, action: Action, ghost_ticks: dict[Position, int]) -> bool:
        """The trap check for the tour's own target, along the tour's path to it."""

        if self.current_target not in self.branches:
            return True

        moves = [action, *self.current_plan]
        ticks = pacman_occupancy_ticks(
            self.maze, state.pacman_position, state.pacman_progress, moves, state.remaining_pellets, state.speeds,
        )
        return self._no_trap(self.current_target, ticks[-1], state, ghost_ticks)

    def _publish_route(self, routes: SafeRoutes, goal: Position) -> None:
        # The route actually walked, so the target and path overlays show the detour.
        if self._status_collection_enabled:
            self._update_status(
                ControllerStatus(target=goal, planned_path=tuple(routes.first_tiles(goal)), path_index=1)
            )

    def _moves_are_safe(self, state: SimulationState, moves: list[Action], ghost_ticks: dict[Position, int]) -> bool:
        ticks = pacman_occupancy_ticks(
            self.maze, state.pacman_position, state.pacman_progress, moves, state.remaining_pellets, state.speeds,
        )
        position = state.pacman_position

        for move, tick in zip(moves, ticks):
            position = self.maze.get_destination(position, move)

            if not is_safe(tick, ghost_ticks.get(position), self.MARGIN):
                return False

        return True

    def _flee_action(self, state: SimulationState, ghost_ticks: dict[Position, int]) -> Action:
        """The neighbour the ghosts reach last (Level 1's flee, in ticks); ties in MOVEMENTS order."""

        # max keeps the first of equal scores; get_valid_movements is in MOVEMENTS order.
        return max(
            self.maze.get_valid_movements(state.pacman_position).items(),
            key=lambda move: ghost_ticks.get(move[1], math.inf),
        )[0]
