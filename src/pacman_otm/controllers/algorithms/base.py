from abc import abstractmethod

from pacman_otm.controllers.base import Controller


class AlgorithmicController(Controller):
    """
    Base class for autonomous controllers that make decisions
    and play the simulation without human intervention.
    """

    def __init__(self):
        super().__init__()

    @abstractmethod
    def reset(self) -> None:
        """
        Reset the controller's internal memory before a new run.
        """
