from dataclasses import dataclass


@dataclass
class GameState:
    player: tuple
    pellets: set
    moves: int = 0
    score: int = 0
    game_time: float = 0.0
    won: bool = False
    previous_player: tuple | None = None
    movement_progress: float = 0.0

    def __post_init__(self):
        self.pellets = set(self.pellets)
        if self.previous_player is None:
            self.previous_player = self.player


@dataclass
class Statistics:
    game_time: float = 0.0
    wall_time: float = 0.0
    moves_attempted: int = 0
    successful_moves: int = 0
    pellets_collected: int = 0
    algorithm_decisions: int = 0
    algorithm_compute_seconds: float = 0.0

    def record_algorithm(self, dt):
        self.algorithm_decisions += 1
        self.algorithm_compute_seconds += dt
