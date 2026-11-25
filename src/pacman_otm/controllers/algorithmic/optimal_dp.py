from collections import deque
import heapq
from typing import Any

from pacman_otm.controllers.algorithmic.base import AlgorithmicController
from pacman_otm.controllers.controller import ControllerAborted
from pacman_otm.controllers.status import ControllerStatus
from pacman_otm.mazes.maze import Maze, Position
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.state import SimulationState

# (posição_atual, direção_atual, próxima_direção_comprometida, progresso)
GhostDPState = tuple[Position, Action | None, Action | None, int]


def _mst_lower_bound(pos: Position, remaining: list[Position]) -> int:
    """Limitante inferior admissível: distância Manhattan até a mais próxima + custo da MST."""
    if not remaining:
        return 0

    dist_to_nearest = min(
        abs(pos[0] - p[0]) + abs(pos[1] - p[1]) for p in remaining
    )
    if len(remaining) == 1:
        return dist_to_nearest

    n = len(remaining)
    visited = [False] * n
    min_edge = [10**9] * n
    min_edge[0] = 0
    mst_cost = 0

    for _ in range(n):
        u = -1
        for i in range(n):
            if not visited[i] and (u == -1 or min_edge[i] < min_edge[u]):
                u = i
        visited[u] = True
        mst_cost += min_edge[u]
        ux, uy = remaining[u]
        for v in range(n):
            if not visited[v]:
                vx, vy = remaining[v]
                d = abs(ux - vx) + abs(uy - vy)
                if d < min_edge[v]:
                    min_edge[v] = d

    return dist_to_nearest + mst_cost


class OptimalDPController(AlgorithmicController):
    """
    Controlador de Programação Dinâmica / A* (MST) com Horizonte Deslizante (MPC),
    otimizado para execução rápida em Python puro no Pac-Man-OTM.
    """

    def __init__(
        self,
        maze: Maze,
        use_astar: bool = False,
        max_exact_pellets: int = 10,
        horizon_pellets: int = 5,
        mpc_max_states: int = 5_000,
        mpc_fallback_states: int = 2_000,
        replan_threat_distance: int = 3,
    ) -> None:
        super().__init__()
        self.maze = maze
        self.use_astar = use_astar
        self.max_exact_pellets = max_exact_pellets
        self.horizon_pellets = horizon_pellets
        self.mpc_max_states = mpc_max_states
        self.mpc_fallback_states = mpc_fallback_states
        self.replan_threat_distance = replan_threat_distance
        self.reset()

    def reset(self) -> None:
        self._plan: deque[Action] = deque()
        self._planned_positions: tuple[Position, ...] = ()
        self._path_index: int = 0
        self._current_target: Position | None = None
        self.visited_states: int = 0
        self.used_receding_horizon: bool = False
        self.clear_status()

    def describe(self) -> dict[str, Any]:
        return {
            **super().describe(),
            "use_astar": self.use_astar,
            "max_exact_pellets": self.max_exact_pellets,
            "horizon_pellets": self.horizon_pellets,
            "mpc_max_states": self.mpc_max_states,
            "mpc_fallback_states": self.mpc_fallback_states,
            "replan_threat_distance": self.replan_threat_distance,
            "visited_states": self.visited_states,
            "receding_horizon": self.used_receding_horizon,
        }

    def _has_nearby_ghost(
        self,
        pos: Position,
        ghost_states: tuple[GhostDPState, ...],
    ) -> bool:
        if not ghost_states:
            return False
        px, py = pos
        return any(
            abs(px - g[0][0]) + abs(py - g[0][1]) <= self.replan_threat_distance
            for g in ghost_states
        )

    def _tile_risk_penalty(
        self,
        curr_pos: Position,
        next_pos: Position,
        ghost_states: tuple[GhostDPState, ...],
    ) -> int:
        penalty = 0
        for g_pos, g_heading, g_next_heading, _ in ghost_states:
            dist = abs(next_pos[0] - g_pos[0]) + abs(next_pos[1] - g_pos[1])
            if dist <= 1:
                penalty += 6
            elif dist == 2:
                penalty += 3
            elif dist == 3:
                penalty += 1

            if g_heading is not None:
                g_dest = self.maze.get_destination(g_pos, g_heading)
                if next_pos == g_dest or (next_pos == g_pos and g_dest == curr_pos):
                    penalty += 8
                elif g_next_heading is not None and self.maze.is_walkable(g_dest):
                    g_after = self.maze.get_destination(g_dest, g_next_heading)
                    if next_pos == g_after:
                        penalty += 4
        return penalty

    def _next_planned_action_is_safe(
        self,
        pos: Position,
        ghost_states: tuple[GhostDPState, ...],
    ) -> bool:
        if not self._plan:
            return False
        action = self._plan[0]
        next_pos = self.maze.get_destination(pos, action)
        if not self.maze.is_walkable(next_pos):
            return False
        if not ghost_states:
            return True
        if self._has_nearby_ghost(pos, ghost_states):
            return not any(next_pos == g[0] for g in ghost_states)
        return True

    def select_action(self, state: SimulationState) -> Action:
        if not state.remaining_pellets:
            raise RuntimeError("No reachable remaining pellets.")

        pos = state.pacman_position
        ghost_dp_states = self._sync_ghost_states(state)

        if self._next_planned_action_is_safe(pos, ghost_dp_states):
            return self._consume_next_action()

        if (
            len(state.remaining_pellets) <= self.max_exact_pellets
            and not self.used_receding_horizon
        ):
            actions = self._solve_subset(
                start_pos=pos,
                ghost_states=ghost_dp_states,
                target_pellets=sorted(state.remaining_pellets),
            )
            self._set_plan(pos, actions)
            return self._consume_next_action()

        self.used_receding_horizon = True
        px, py = pos
        nearest_subset = sorted(
            state.remaining_pellets,
            key=lambda p: (abs(p[0] - px) + abs(p[1] - py), p[0], p[1]),
        )[: self.horizon_pellets]

        actions = self._solve_mpc_with_fallback(
            start_pos=pos,
            ghost_states=ghost_dp_states,
            nearest_subset=nearest_subset,
        )
        self._set_plan(pos, actions)
        return self._consume_next_action()

    def _solve_mpc_with_fallback(
        self,
        start_pos: Position,
        ghost_states: tuple[GhostDPState, ...],
        nearest_subset: list[Position],
    ) -> deque[Action]:
        try:
            return self._solve_subset(
                start_pos=start_pos,
                ghost_states=ghost_states,
                target_pellets=nearest_subset,
                max_states=self.mpc_max_states,
            )
        except ControllerAborted:
            if len(nearest_subset) > 1:
                try:
                    return self._solve_subset(
                        start_pos=start_pos,
                        ghost_states=ghost_states,
                        target_pellets=nearest_subset[:1],
                        max_states=self.mpc_fallback_states,
                    )
                except ControllerAborted:
                    pass

            safe_step = self._best_evasion_step(start_pos, ghost_states)
            if safe_step is not None:
                return deque([safe_step])
            raise

    def _best_evasion_step(
        self,
        pos: Position,
        ghost_states: tuple[GhostDPState, ...],
    ) -> Action | None:
        valid = self.maze.get_valid_movements(pos)
        if not valid:
            return None
        if not ghost_states:
            return next(iter(valid.keys()))

        best_action: Action | None = None
        best_score = -10**9

        for action, next_pos in valid.items():
            min_dist = min(
                abs(next_pos[0] - g[0][0]) + abs(next_pos[1] - g[0][1])
                for g in ghost_states
            )
            direct_hit = any(next_pos == g[0] for g in ghost_states)
            score = min_dist * 10 - (500 if direct_hit else 0)
            if score > best_score:
                best_score = score
                best_action = action

        return best_action

    def _set_plan(self, start_pos: Position, actions: deque[Action]) -> None:
        self._plan = actions
        self._path_index = 0

        if self._status_collection_enabled and actions:
            pos = start_pos
            positions: list[Position] = []
            for act in actions:
                pos = self.maze.get_destination(pos, act)
                positions.append(pos)
            self._planned_positions = tuple(positions)
            self._current_target = positions[-1]
        else:
            self._planned_positions = ()
            self._current_target = None

    def _consume_next_action(self) -> Action:
        if not self._plan:
            raise ControllerAborted("no_safe_path")

        action = self._plan.popleft()
        self._path_index += 1

        if self._status_collection_enabled:
            self._update_status(
                ControllerStatus(
                    target=self._current_target,
                    planned_path=self._planned_positions,
                    path_index=self._path_index,
                )
            )

        return action

    def _sync_ghost_states(self, state: SimulationState) -> tuple[GhostDPState, ...]:
        if not state.ghosts:
            return ()

        synced: list[GhostDPState] = [
            (
                g.position,
                getattr(g, "heading", None),
                getattr(g, "next_heading", None),
                0,
            )
            for g in state.ghosts
        ]
        return tuple(sorted(synced, key=self._ghost_sort_key))

    @staticmethod
    def _ghost_sort_key(gs: GhostDPState) -> tuple[int, int, str, str, int]:
        pos, h1, h2, prog = gs
        return (
            pos[0],
            pos[1],
            h1.value if h1 is not None else "",
            h2.value if h2 is not None else "",
            prog,
        )

    def _choose_fast_ghost_move(
        self,
        pos: Position,
        heading: Action | None,
        pacman_tile: Position,
    ) -> Action | None:
        valid = self.maze.get_valid_movements(pos)
        if not valid:
            return None

        candidates = list(valid.items())
        if heading is not None and len(candidates) > 1:
            rev = heading.reverse
            non_rev = [(act, dst) for act, dst in candidates if act != rev]
            if non_rev:
                candidates = non_rev

        px, py = pacman_tile
        best_act, _ = min(
            candidates,
            key=lambda item: abs(item[1][0] - px) + abs(item[1][1] - py),
        )
        return best_act

    def _step_ghosts_discrete(
        self,
        ghost_states: tuple[GhostDPState, ...],
        pacman_tile: Position,
    ) -> tuple[GhostDPState, ...]:
        if not ghost_states:
            return ()

        moved: list[GhostDPState] = []
        for pos, heading, next_heading, _ in ghost_states:
            cur_heading = heading or self._choose_fast_ghost_move(pos, None, pacman_tile)
            if cur_heading is None:
                moved.append((pos, None, None, 0))
                continue

            new_pos = self.maze.get_destination(pos, cur_heading)
            if not self.maze.is_walkable(new_pos):
                cur_heading = self._choose_fast_ghost_move(pos, None, pacman_tile)
                if cur_heading is None:
                    moved.append((pos, None, None, 0))
                    continue
                new_pos = self.maze.get_destination(pos, cur_heading)
                if not self.maze.is_walkable(new_pos):
                    moved.append((pos, None, None, 0))
                    continue

            new_heading = next_heading or self._choose_fast_ghost_move(
                new_pos, cur_heading, pacman_tile
            )
            moved.append((new_pos, new_heading, None, 0))

        return tuple(sorted(moved, key=self._ghost_sort_key))

    def _solve_subset(
        self,
        start_pos: Position,
        ghost_states: tuple[GhostDPState, ...],
        target_pellets: list[Position],
        max_states: int | None = None,
    ) -> deque[Action]:
        pellet_list = sorted(target_pellets)
        pellet_idx = {pos: i for i, pos in enumerate(pellet_list)}
        target_mask = (1 << len(pellet_list)) - 1

        if target_mask == 0:
            return deque()

        s0 = (start_pos, 0, ghost_states)
        parent: dict[Any, tuple[Any, Action | None]] = {s0: (None, None)}
        g_cost: dict[Any, int] = {s0: 0}

        heap: list[tuple[int, int, int, Any]] = []
        fifo: deque[Any] = deque()
        tie = 0

        if self.use_astar:
            h0 = _mst_lower_bound(start_pos, pellet_list)
            heapq.heappush(heap, (h0, 0, tie, s0))
        else:
            fifo.append(s0)

        goal_state = None
        while heap or fifo:
            if max_states is not None and len(g_cost) > max_states:
                break

            if self.use_astar:
                _, curr_g, _, curr = heapq.heappop(heap)
                if curr_g > g_cost.get(curr, 10**9):
                    continue
            else:
                curr = fifo.popleft()
                curr_g = g_cost[curr]

            v, mask, ghosts = curr
            if mask == target_mask:
                goal_state = curr
                break

            for action, next_v in self.maze.get_valid_movements(v).items():
                if ghosts and any(next_v == g[0] for g in ghosts):
                    continue

                next_ghosts = self._step_ghosts_discrete(ghosts, next_v)
                if next_ghosts and any(next_v == ng[0] for ng in next_ghosts):
                    continue

                next_mask = mask
                if next_v in pellet_idx:
                    next_mask |= 1 << pellet_idx[next_v]

                risk_penalty = (
                    self._tile_risk_penalty(v, next_v, ghosts) if ghosts else 0
                )
                step_cost = 1 + risk_penalty
                nxt = (next_v, next_mask, next_ghosts)
                new_cost = curr_g + step_cost

                if new_cost < g_cost.get(nxt, 10**9):
                    g_cost[nxt] = new_cost
                    parent[nxt] = (curr, action)
                    if self.use_astar:
                        rem = [
                            pellet_list[i]
                            for i in range(len(pellet_list))
                            if not (next_mask & (1 << i))
                        ]
                        tie += 1
                        f_score = new_cost + _mst_lower_bound(next_v, rem)
                        heapq.heappush(heap, (f_score, new_cost, tie, nxt))
                    else:
                        fifo.append(nxt)

        self.visited_states += len(g_cost)
        if goal_state is None:
            raise ControllerAborted("no_safe_path")

        actions: deque[Action] = deque()
        curr = goal_state
        while parent[curr][0] is not None:
            prev_s, act = parent[curr]
            actions.appendleft(act)  # type: ignore[arg-type]
            curr = prev_s

        return actions