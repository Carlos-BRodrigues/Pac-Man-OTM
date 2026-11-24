from time import perf_counter
from collections.abc import Callable, Sequence

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
    ghosts: Sequence[Controller] = (),
) -> SimulationResult:
    """
    Run until the engine ends the run. Each step, Pac-Man's controller and then
    every ghost decide on the same state, so all of them move at once. Ghost i
    controls engine.state.ghosts[i]. controller_time_seconds counts Pac-Man's
    thinking only; ghosts count in the elapsed time.
    """

    if len(ghosts) != len(engine.state.ghosts):
        raise ValueError(
            f"{len(ghosts)} ghost controller(s) for {len(engine.state.ghosts)} ghost(s) in the engine."
        )

    controller.reset()

    statuses = []
    ghost_statuses = []
    controller.clear_status()

    for ghost in ghosts:
        ghost.reset()

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

        ghost_actions = [ghost.select_action(engine.state) for ghost in ghosts]
        ghost_status = tuple(ghost.get_status() for ghost in ghosts)
        ghost_statuses.append(ghost_status)

        engine.step(action, ghost_actions)

        if on_frame is not None:
            should_continue = on_frame(
                SimulationFrame(
                    state=engine.state.copy(),
                    action=action,
                    status=status,
                    ghost_statuses=ghost_status,
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
        ghost_statuses=ghost_statuses,
        ghosts=[ghost.describe() for ghost in ghosts],
    )
