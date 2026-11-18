from abc import ABC, abstractmethod


class Controller(ABC):
    name = "Controller"
    is_algorithm = True

    @abstractmethod
    def choose_action(self, observation):
        raise NotImplementedError


class ManualController(Controller):
    name = "Manual"
    is_algorithm = False

    def __init__(self):
        self.action = "LEFT"

    def set_action(self, action):
        self.action = action

    def choose_action(self, observation):
        return self.action
