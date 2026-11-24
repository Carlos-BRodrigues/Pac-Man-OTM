from time import perf_counter
from collections.abc import Callable

from pacman_otm.controllers.controller import Controller, ControllerAborted

from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.result import SimulationResult
from pacman_otm.statistics_.metrics import SimulationMetrics
from pacman_otm.simulation.frame import SimulationFrame

# Steps before a run is stopped ("max_steps"); large saved mazes need well over 1000.
DEFAULT_MAX_STEPS = 3000


def run_simulation(
    engine: SimulationEngine,
    controller: Controller,
    max_steps: int = DEFAULT_MAX_STEPS,
    on_frame: Callable[[SimulationFrame], bool | None] | None = None,
) -> SimulationResult:

    controller.reset()

    statuses = []
    controller.clear_status()

    start_time = perf_counter()
    controller_time = 0.0

    if on_frame is not None:
        should_continue = on_frame(SimulationFrame(state=engine.state.copy()))

        if should_continue is False:
            engine.terminate("visualization_closed")

    while not engine.state.terminated:

        if engine.state.steps >= max_steps:
            engine.terminate("max_steps")
            break

        decision_start = perf_counter()

        try:
            action = controller.select_action(engine.state)
        except ControllerAborted as abort:
            engine.terminate(abort.reason)
            break
        finally:
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
                engine.terminate("visualization_closed")

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
        controller=controller.describe(),
    )
