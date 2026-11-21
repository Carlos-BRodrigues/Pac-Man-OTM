from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pacman_otm.controllers.status import ControllerStatus
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.state import SimulationState


class ControllerAborted(Exception):
    """
    Raised from select_action to end the run without an action (e.g. the player quit).
    The runner turns it into a termination with this reason.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class Controller(ABC):

    # Controller family recorded in results: "algorithmic", "stochastic", "manual"
    controller_type: ClassVar[str]

    def __init__(self) -> None:
        self._status_collection_enabled = True
        self._status: ControllerStatus | None = None

    @abstractmethod
    def select_action(self, state: SimulationState) -> Action:
        pass

    def reset(self) -> None:
        """
        Reset internal memory before a new run. Stateless controllers need nothing.
        """

    def describe(self) -> dict[str, Any]:
        """
        Identify this controller in a saved result. Subclasses add the
        parameters needed to reproduce a run (e.g. the seed).
        """
        return {
            "type": self.controller_type,
            "class": type(self).__name__,
        }

    def clear_status(self) -> None:
        self._status = None

    def set_status_collection(self, enabled: bool) -> None:
        """
        Enable or disable optional controller status collection.
        """
        self._status_collection_enabled = enabled
        self._status = None

    def get_status(self) -> ControllerStatus | None:
        """
        Return the most recently calculated status.

        This method only returns a stored reference.
        It performs no calculations.
        """
        return self._status

    def _update_status(self, status: ControllerStatus) -> None:
        """
        Update the stored status if collection is enabled.
        """
        if self._status_collection_enabled:
            self._status = status
