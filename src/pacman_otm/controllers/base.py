from abc import ABC, abstractmethod

from pacman_otm.controllers.status import ControllerStatus
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.state import SimulationState


class Controller(ABC):

    def __init__(self) -> None:
        self._status_collection_enabled = True
        self._status: ControllerStatus | None = None

    @abstractmethod
    def select_action(self, state: SimulationState) -> Action:
        pass

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
