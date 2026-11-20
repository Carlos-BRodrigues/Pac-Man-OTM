from dataclasses import dataclass

from pacman_otm.controllers.status import ControllerStatus
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.state import SimulationState


@dataclass(frozen=True)
class SimulationFrame:
    """
    A snapshot of the simulation at a particular moment.
    """

    state: SimulationState
    action: Action | None = None
    status: ControllerStatus | None = None
