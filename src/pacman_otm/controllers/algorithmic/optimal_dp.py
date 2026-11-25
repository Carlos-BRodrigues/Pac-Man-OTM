from collections import deque
import heapq
from typing import Any

from pacman_otm.algorithms.pathfinding.no_reverse import NoReverseSearch
from pacman_otm.controllers.algorithmic.base import AlgorithmicController
from pacman_otm.controllers.controller import ControllerAborted
from pacman_otm.controllers.status import ControllerStatus
from pacman_otm.mazes.maze import Maze, Position
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.state import SimulationState

# Estado interno de cada fantasma na DP:
# (posição_atual, direção_atual, próxima_direção_já_comprometida)
GhostDPState = tuple[Position, Action | None, Action | None]


def _mst_lower_bound(pos: Position, remaining: list[Position]) -> int:
    """Limitante inferior admissível: distância Manhattan até a pastilha mais próxima + MST."""
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


class OptimalDPController(AlgorithmicController):
    """
    Programação Dinâmica Exata no espaço de estados aumentado (Pac-Man + bitmask
    de pastilhas + estado exato dos fantasmas com lookahead de 1 casa), com poda
    admissível A* via Árvore Geradora Mínima (MST) e Horizonte Deslizante (MPC)
    automático para mapas grandes.
    """

    def __init__(
        self,
        maze: Maze,
        use_astar: bool = False,
        max_exact_pellets: int = 16,
        horizon_pellets: int = 8,
    ) -> None:
        super().__init__()
        self.maze = maze
        self.use_astar = use_astar
        self.max_exact_pellets = max_exact_pellets
        self.horizon_pellets = horizon_pellets
        self._ghost_search = NoReverseSearch(maze)
        self._ghost_move_cache: dict[
            tuple[Position, Action | None, Position], Action
        ] = {}
        self.reset()

    def reset(self) -> None:
        self._plan: deque[Action] = deque()
        self._planned_positions: tuple[Position, ...] = ()
        self._path_index: int = 0
        self._current_target: Position | None = None
        self.visited_states: int = 0
        self.used_receding_horizon: bool = False
        self._shadow_ghosts: list[GhostDPState] | None = None
        self.clear_status()

    def describe(self) -> dict[str, Any]:
        return {
            **super().describe(),
            "use_astar": self.use_astar,
            "max_exact_pellets": self.max_exact_pellets,
            "horizon_pellets": self.horizon_pellets,
            "visited_states": self.visited_states,
            "receding_horizon": self.used_receding_horizon,
        }

    def select_action(self, state: SimulationState) -> Action:
        if not state.remaining_pellets:
            raise RuntimeError("No reachable remaining pellets.")

        ghost_dp_states = self._sync_ghost_states(state)

        # Caso 1: Instância tratável globalmente -> resolve uma única vez e segue o plano ótimo
        if len(state.remaining_pellets) <= self.max_exact_pellets and not self.used_receding_horizon:
            if not self._plan:
                actions = self._solve_subset(
                    state=state,
                    ghost_states=ghost_dp_states,
                    target_pellets=sorted(state.remaining_pellets),
                )
                self._set_plan(state.pacman_position, actions)
            return self._consume_next_action(state)

        # Caso 2: Mapa grande (ex: classic) -> Horizonte Deslizante (MPC) sobre as H mais próximas
        self.used_receding_horizon = True
        if not self._plan or bool(ghost_dp_states):
            px, py = state.pacman_position
            nearest_subset = sorted(
                state.remaining_pellets,
                key=lambda p: (abs(p[0] - px) + abs(p[1] - py), p[0], p[1]),
            )[: self.horizon_pellets]

            actions = self._solve_mpc_with_fallback(
                state=state,
                ghost_states=ghost_dp_states,
                nearest_subset=nearest_subset,
            )
            self._set_plan(state.pacman_position, actions)

        return self._consume_next_action(state)

    def _solve_mpc_with_fallback(
        self,
        state: SimulationState,
        ghost_states: tuple[GhostDPState, ...],
        nearest_subset: list[Position],
    ) -> deque[Action]:
        """Tenta o horizonte local H; se um fantasma bloquear o subconjunto, reduz o horizonte."""
        try:
            return self._solve_subset(
                state,
                ghost_states,
                nearest_subset,
                max_states=200_000,
            )
        except ControllerAborted:
            if len(nearest_subset) > 1:
                try:
                    return self._solve_subset(
                        state,
                        ghost_states,
                        nearest_subset[:1],
                        max_states=50_000,
                    )
                except ControllerAborted:
                    pass

            safe_step = self._best_evasion_step(state, ghost_states)
            if safe_step is not None:
                return deque([safe_step])
            raise

    def _best_evasion_step(
        self,
        state: SimulationState,
        ghost_states: tuple[GhostDPState, ...],
    ) -> Action | None:
        """Fallback de sobrevivência: escolhe um passo sem colisão que afasta dos fantasmas."""
        v = state.pacman_position
        next_ghosts = tuple(
            self._step_ghost_lookahead(gs, v) for gs in ghost_states
        )
        best_action: Action | None = None
        best_dist = -1

        for action, next_v in self.maze.get_valid_movements(v).items():
            if self._is_collision(v, next_v, ghost_states, next_ghosts):
                continue
            min_g_dist = min(
                abs(next_v[0] - ng[0][0]) + abs(next_v[1] - ng[0][1])
                for ng in next_ghosts
            )
            if min_g_dist > best_dist:
                best_dist = min_g_dist
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

    def _consume_next_action(self, state: SimulationState) -> Action:
        if not self._plan:
            raise ControllerAborted("no_safe_path")

        action = self._plan.popleft()
        self._path_index += 1

        # Avança o rastreador sombra dos fantasmas para manter o compromisso de 1 casa sincronizado
        if state.ghosts:
            if self._shadow_ghosts is None:
                self._shadow_ghosts = [
                    (g.position, g.direction, None) for g in state.ghosts
                ]
            self._shadow_ghosts = [
                self._step_ghost_lookahead(gs, state.pacman_position)
                for gs in self._shadow_ghosts
            ]

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
        """
        Reconstrói (posição, direção_atual, próxima_direção_comprometida) de cada
        fantasma para que a DP preveja exatamente o movimento do Blinky.
        """
        if not state.ghosts:
            self._shadow_ghosts = []
            return ()

        if (
            self._shadow_ghosts is not None
            and len(self._shadow_ghosts) == len(state.ghosts)
            and all(
                sh[0] == g.position and sh[1] == g.direction
                for sh, g in zip(self._shadow_ghosts, state.ghosts)
            )
        ):
            return tuple(sorted(self._shadow_ghosts, key=self._ghost_sort_key))

        synced: list[GhostDPState] = [
            (g.position, g.direction, None) for g in state.ghosts
        ]
        self._shadow_ghosts = synced
        return tuple(sorted(synced, key=self._ghost_sort_key))

    @staticmethod
    def _ghost_sort_key(gs: GhostDPState) -> tuple[int, int, str, str]:
        pos, d1, d2 = gs
        return (
            pos[0],
            pos[1],
            d1.value if d1 is not None else "",
            d2.value if d2 is not None else "",
        )

    def _first_no_reverse_move(
        self,
        pos: Position,
        heading: Action | None,
        target: Position,
    ) -> Action:
        """Replica exatamente a escolha de saída do GhostController / Blinky."""
        key = (pos, heading, target)
        cached = self._ghost_move_cache.get(key)
        if cached is not None:
            return cached

        if heading is None:
            path = self._ghost_search.find_path(pos, None, target)
            move = (
                path[0]
                if path
                else self._ghost_search.legal_moves(pos, None)[0]
            )
        else:
            options = self._ghost_search.legal_moves(pos, heading)
            if len(options) > 1:
                path = self._ghost_search.find_path(pos, heading, target)
                move = path[0] if path else options[0]
            else:
                move = options[0]

        self._ghost_move_cache[key] = move
        return move

    def _step_ghost_lookahead(
        self,
        g_state: GhostDPState,
        pacman_pos: Position,
    ) -> GhostDPState:
        """
        Simula 1 turno do Blinky com lookahead: executa `committed` agora e
        já compromete a saída de `next_g` usando a posição atual `pacman_pos`.
        """
        g_pos, g_dir, committed = g_state
        act = (
            self._first_no_reverse_move(g_pos, g_dir, pacman_pos)
            if committed is None
            else committed
        )
        next_g = self.maze.get_destination(g_pos, act)
        next_committed = self._first_no_reverse_move(next_g, act, pacman_pos)
        return (next_g, act, next_committed)

    @staticmethod
    def _is_collision(
        pacman_before: Position,
        pacman_after: Position,
        ghosts_before: tuple[GhostDPState, ...],
        ghosts_after: tuple[GhostDPState, ...],
    ) -> bool:
        """Mesma regra do SimulationEngine._caught: mesma casa ou troca frontal."""
        for g_before, g_after in zip(ghosts_before, ghosts_after):
            gb_pos = g_before[0]
            ga_pos = g_after[0]
            if ga_pos == pacman_after or (
                ga_pos == pacman_before and gb_pos == pacman_after
            ):
                return True
        return False

    def _solve_subset(
        self,
        state: SimulationState,
        ghost_states: tuple[GhostDPState, ...],
        target_pellets: list[Position],
        max_states: int | None = None,
    ) -> deque[Action]:
        pellet_list = sorted(target_pellets)
        pellet_idx = {pos: i for i, pos in enumerate(pellet_list)}
        target_mask = (1 << len(pellet_list)) - 1

        if target_mask == 0:
            return deque()

        s0 = (state.pacman_position, 0, ghost_states)

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

            next_ghosts_raw = tuple(
                self._step_ghost_lookahead(gs, v) for gs in ghosts
            )
            next_ghosts = tuple(
                sorted(next_ghosts_raw, key=self._ghost_sort_key)
            )

            for action, next_v in self.maze.get_valid_movements(v).items():
                if ghosts and self._is_collision(
                    v, next_v, ghosts, next_ghosts_raw
                ):
                    continue

                next_mask = mask
                if next_v in pellet_idx:
                    next_mask |= 1 << pellet_idx[next_v]

                nxt = (next_v, next_mask, next_ghosts)
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
            raise ControllerAborted("no_safe_path")

        actions: deque[Action] = deque()
        curr = goal_state
        while parent[curr][0] is not None:
            prev_s, act = parent[curr]
            actions.appendleft(act)  # type: ignore[arg-type]
            curr = prev_s

        return actions