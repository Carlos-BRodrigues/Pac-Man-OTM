from dataclasses import dataclass, asdict
from typing import Any

from pacman_otm.simulation.engine import SimulationEngine


@dataclass
class SimulationMetrics:
    total_steps: int
    initial_pellets: int
    collected_pellets: int
    remaining_pellets: int
    completion_rate: float
    completed: bool
    termination_reason: str | None
    # Ghosts in the run; a run they end has termination_reason "caught".
    ghosts: int = 0

    elapsed_time_seconds: float | None = None
    controller_time_seconds: float | None = None

    @classmethod
    def from_engine(
        cls,
        engine: SimulationEngine,
        elapsed_time_seconds: float | None = None,
        controller_time_seconds: float | None = None,
    ) -> "SimulationMetrics":

        initial_pellets = len(engine.maze.initial_pellets)
        remaining_pellets = len(engine.state.remaining_pellets)
        collected_pellets = initial_pellets - remaining_pellets

        completion_rate = (
            collected_pellets / initial_pellets if initial_pellets > 0 else 1.0
        )

        return cls(
            total_steps=engine.state.steps,
            initial_pellets=initial_pellets,
            collected_pellets=collected_pellets,
            remaining_pellets=remaining_pellets,
            completion_rate=completion_rate,
            completed=engine.state.termination_reason == "completed",
            termination_reason=engine.state.termination_reason,
            ghosts=len(engine.state.ghosts),
            elapsed_time_seconds=elapsed_time_seconds,
            controller_time_seconds=controller_time_seconds,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __str__(self) -> str:
        from pacman_otm.statistics_.serialization import pretty_json
        return pretty_json(self.to_dict())
