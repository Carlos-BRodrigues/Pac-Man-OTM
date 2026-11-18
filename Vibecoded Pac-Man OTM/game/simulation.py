from dataclasses import dataclass
from time import perf_counter
from .state import GameState, Statistics
from .model import DIRECTIONS


@dataclass(frozen=True)
class Observation:
    player: tuple
    pellets: frozenset
    maze: object
    legal_actions: tuple
    game_time: float


class Simulation:
    def __init__(self, maze, start, pellets, move_interval=0.12):
        if not maze.is_corridor(start):
            raise ValueError("Start must be corridor")
        if any(not maze.is_corridor(p) for p in pellets):
            raise ValueError("Pellets must be on corridors")
        self.maze = maze
        self.start = start
        self.initial_pellets = set(pellets)
        self.move_interval = move_interval
        self.reset()

    def reset(self):
        self.state = GameState(self.start, set(self.initial_pellets))
        self.statistics = Statistics()
        self.accumulator = 0.0
        self.last_action = None
        # A pellet is allowed on the starting tile and is collected immediately.
        if self.start in self.state.pellets:
            self.state.pellets.remove(self.start)
            self.state.score = 10
            self.statistics.pellets_collected = 1
        self.state.won = not self.state.pellets
        self.pending_algorithm_time = 0.0

    def observation(self):
        p = self.state.player
        legal = [
            a
            for a, (dx, dy) in DIRECTIONS.items()
            if self.maze.is_corridor((p[0] + dx, p[1] + dy))
        ]
        tunnel_action = self.maze.tunnel_exit_action(p)
        if tunnel_action and tunnel_action not in legal:
            legal.append(tunnel_action)
        return Observation(
            p,
            frozenset(self.state.pellets),
            self.maze,
            tuple(legal),
            self.state.game_time,
        )

    def _move(self, action):
        if action not in DIRECTIONS:
            return
        dx, dy = DIRECTIONS[action]
        p = self.state.player
        q = (p[0] + dx, p[1] + dy)
        if not self.maze.is_corridor(q):
            tunnel_action = self.maze.tunnel_exit_action(p)
            if tunnel_action != action:
                return
            q = self.maze.tunnel_lookup()[p]
        self.state.previous_player = p
        self.state.player = q
        self.state.moves += 1
        self.statistics.successful_moves += 1
        if q in self.state.pellets:
            self.state.pellets.remove(q)
            self.state.score += 10
            self.statistics.pellets_collected += 1
        self.state.won = not self.state.pellets

    def advance(self, dt, provider, is_algorithm=False):
        if self.state.won:
            return
        self.statistics.wall_time += dt
        # Controller execution is measured as wall time, then excluded from the
        # simulation clock on the next frame. This keeps the two clocks distinct.
        usable_dt = max(0.0, dt - self.pending_algorithm_time)
        self.pending_algorithm_time = max(0.0, self.pending_algorithm_time - dt)
        self.state.game_time += usable_dt
        self.statistics.game_time = self.state.game_time
        self.accumulator += usable_dt
        while self.accumulator >= self.move_interval and not self.state.won:
            self.statistics.moves_attempted += 1
            t = perf_counter()
            action = provider(self.observation())
            elapsed = perf_counter() - t
            if is_algorithm:
                self.statistics.record_algorithm(elapsed)
                self.pending_algorithm_time += elapsed
            self.last_action = action
            old_position = self.state.player
            self._move(action)
            if self.state.player == old_position:
                self.state.previous_player = self.state.player
            self.accumulator -= self.move_interval
        self.state.movement_progress = min(1.0, self.accumulator / self.move_interval)

    def interpolated_position(self):
        a = self.state.previous_player
        b = self.state.player
        t = self.state.movement_progress
        # A tunnel transition exits one edge and enters the opposite edge;
        # do not interpolate Pac-Man across the entire map interior.
        if self.maze.tunnel_lookup().get(a) == b:
            action = self.maze.tunnel_exit_action(a)
            if action == "LEFT":
                return (
                    (-2 * t, a[1])
                    if t < 0.5
                    else (self.maze.width - 2 * (t - 0.5), a[1])
                )
            if action == "RIGHT":
                return (
                    (self.maze.width - 1 + 2 * t, a[1])
                    if t < 0.5
                    else (-1 + 2 * (t - 0.5), a[1])
                )
            if action == "UP":
                return (
                    (a[0], -2 * t)
                    if t < 0.5
                    else (a[0], self.maze.height - 2 * (t - 0.5))
                )
            if action == "DOWN":
                return (
                    (a[0], self.maze.height - 1 + 2 * t)
                    if t < 0.5
                    else (a[0], -1 + 2 * (t - 0.5))
                )
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
