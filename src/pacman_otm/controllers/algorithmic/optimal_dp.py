from collections import deque
import heapq
from typing import Any

from pacman_otm.controllers.controller import Controller
from pacman_otm.mazes.maze import Maze, Position
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.engine import ghost_step
from pacman_otm.simulation.state import SimulationState


def _mst_lower_bound(pos: Position, remaining: list[Position]) -> int:
    """Limitante inferior admissível: distância Manhattan mais próxima + custo da MST."""
    if not remaining:
        return 0

    dist_to_nearest = min(
        abs(pos[0] - p[0]) + abs(pos[1] - p[1]) for p in remaining
    )
    if len(remaining) == 1:
        return dist_to_nearest

    # Algoritmo de Prim em O(k^2) sobre distâncias de Manhattan
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


class OptimalDPController(Controller):
    """
    Programação Dinâmica Exata (Bellman / Held-Karp) com suporte a A* (MST),
    múltiplos fantasmas perseguidores com quebra de simetria e MPC.
    """

    controller_type = "algorithmic"

    def __init__(
        self,
        maze: Maze,
        use_astar: bool = False,
        max_exact_pellets: int = 12,
        horizon_pellets: int = 8,
    ) -> None:
        super().__init__()
        self.maze = maze
        self.use_astar = use_astar
        self.max_exact_pellets = max_exact_pellets
        self.horizon_pellets = horizon_pellets
        self._plan: deque[Action] | None = None
        self.visited_states: int = 0
        self.used_receding_horizon: bool = False

    def reset(self) -> None:
        self._plan = None
        self.visited_states = 0
        self.used_receding_horizon = False

    def describe(self) -> dict[str, Any]:
        info = super().describe()
        info["use_astar"] = self.use_astar
        info["visited_states"] = self.visited_states
        info["receding_horizon"] = self.used_receding_horizon
        return info

    def select_action(self, state: SimulationState) -> Action:
        if not state.remaining_pellets:
            return next(iter(self.maze.get_valid_movements(state.pacman_position)))

        # Caso 1: Instância tratável globalmente -> resolve uma única vez
        if len(state.remaining_pellets) <= self.max_exact_pellets and not self.used_receding_horizon:
            if self._plan is None:
                self._plan = self._solve_subset(state, sorted(state.remaining_pellets))
            if self._plan:
                return self._plan.popleft()

        # Caso 2: Mapa grande -> Horizonte Deslizante sobre as k_local mais próximas
        self.used_receding_horizon = True
        if not self._plan or bool(state.ghost_positions):
            px, py = state.pacman_position
            nearest_subset = sorted(
                state.remaining_pellets,
                key=lambda p: (abs(p[0] - px) + abs(p[1] - py), p[0], p[1]),
            )[: self.horizon_pellets]
            self._plan = self._solve_subset(state, nearest_subset)

        if not self._plan:
            return next(iter(self.maze.get_valid_movements(state.pacman_position)))

        return self._plan.popleft()

    def _solve_subset(
        self,
        state: SimulationState,
        target_pellets: list[Position],
    ) -> deque[Action]:
        pellet_list = sorted(target_pellets)
        pellet_idx = {pos: i for i, pos in enumerate(pellet_list)}
        target_mask = (1 << len(pellet_list)) - 1

        if target_mask == 0:
            return deque()

        m = state.ghost_period
        phi0 = state.steps % m
        init_ghosts = tuple(
            sorted(zip(state.ghost_positions, state.ghost_directions))
        )
        s0 = (
            state.pacman_position,
            0,
            init_ghosts,
            phi0,
        )

        parent: dict[Any, tuple[Any, Action | None]] = {s0: (None, None)}
        g_cost: dict[Any, int] = {s0: 0}

        heap: list[tuple[int, int, int, Any]] = []
        fifo: deque[Any] = deque()
        tie = 0

        if self.use_astar:
            h0 = _mst_lower_bound(state.pacman_position, pellet_list)
            heapq.heappush(heap, (h0, 0, tie, s0))
        else:
            fifo.append(s0)

        goal_state = None
        while heap or fifo:
            if self.use_astar:
                _, curr_g, _, curr = heapq.heappop(heap)
                if curr_g > g_cost.get(curr, 10**9):
                    continue
            else:
                curr = fifo.popleft()
                curr_g = g_cost[curr]

            v, mask, ghosts, phi = curr
            if mask == target_mask:
                goal_state = curr
                break

            if ghosts:
                if phi == 0:
                    moved = [
                        ghost_step(self.maze, g_pos, g_dir, v)
                        for g_pos, g_dir in ghosts
                    ]
                else:
                    moved = list(ghosts)
                # Quebra de simetria exata: fantasmas idênticos ordenados canonicamente
                next_ghosts = tuple(sorted(moved))
                next_phi = (phi + 1) % m
            else:
                moved = []
                next_ghosts = ()
                next_phi = 0

            for action, next_v in self.maze.get_valid_movements(v).items():
                if any(
                    next_v == next_g or (next_v == prev_g and v == next_g)
                    for (prev_g, _), (next_g, _) in zip(ghosts, moved)
                ):
                    continue

                next_mask = mask
                if next_v in pellet_idx:
                    next_mask |= 1 << pellet_idx[next_v]

                nxt = (next_v, next_mask, next_ghosts, next_phi)
                new_cost = curr_g + 1

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
            raise RuntimeError(
                "Nenhuma trajetória factível encontrada para o subconjunto alvo."
            )

        actions: deque[Action] = deque()
        curr = goal_state
        while parent[curr][0] is not None:
            prev_s, act = parent[curr]
            actions.appendleft(act)  # type: ignore[arg-type]
            curr = prev_s

        return actions