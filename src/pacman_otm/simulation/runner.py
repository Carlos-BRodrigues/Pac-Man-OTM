from time import perf_counter
from collections.abc import Callable

from pacman_otm.controllers.base import Controller
from pacman_otm.controllers.algorithms.base import AlgorithmicController

from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.result import SimulationResult
from pacman_otm.statistics_.metrics import SimulationMetrics
from pacman_otm.simulation.frame import SimulationFrame


def run_simulation(
    engine: SimulationEngine,
    controller: Controller,
    max_steps: int = 1000,
    on_frame: Callable[[SimulationFrame], bool | None] | None = None,
) -> SimulationResult:

    if isinstance(controller, AlgorithmicController):
        controller.reset()

    statuses = []
    controller.clear_status()

    start_time = perf_counter()
    controller_time = 0.0

    def stop_simulation(reason: str) -> None:
        if not engine.state.terminated:
            engine.state.terminated = True
            engine.state.termination_reason = reason
            engine.states[-1] = engine.state.copy()

    if on_frame is not None:
        should_continue = on_frame(SimulationFrame(state=engine.state.copy()))

        if should_continue is False:
            stop_simulation("visualization_closed")

    while not engine.state.terminated:

        if engine.state.steps >= max_steps:
            engine.state.terminated = True
            engine.state.termination_reason = "max_steps"
            engine.states[-1] = engine.state.copy()
            break

        decision_start = perf_counter()
        action = controller.select_action(engine.state)
        controller_time += perf_counter() - decision_start

        status = controller.get_status()
        statuses.append(status)

        engine.step(action)

        if on_frame is not None:
            should_continue = on_frame(
                SimulationFrame(
                    state=engine.state.copy(),
                    action=action,
                    status=status,
                )
            )

            if should_continue is False:
                stop_simulation("visualization_closed")

    elapsed_time = perf_counter() - start_time

    metrics = SimulationMetrics.from_engine(
        engine=engine,
        elapsed_time_seconds=elapsed_time,
        controller_time_seconds=controller_time,
    )

    return SimulationResult.from_engine(
        engine,
        metrics,
        statuses=statuses,
    )
