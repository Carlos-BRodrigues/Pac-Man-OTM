from pacman_otm.controllers.base import Controller
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.state import SimulationState


class ManualController(Controller):
    def __init__(self):
        super().__init__()

    def select_action(self, state: SimulationState) -> Action:

        print(f"\nPac-Man position: {state.pacman_position}")

        print("Remaining pellets:", len(state.remaining_pellets))

        print("Choose an action:")
        print("W - Up")
        print("S - Down")
        print("A - Left")
        print("D - Right")

        commands = {
            "w": Action.UP,
            "s": Action.DOWN,
            "a": Action.LEFT,
            "d": Action.RIGHT,
        }

        while True:

            command = input("Action: ").lower().strip()

            if command in commands:
                return commands[command]

            print("Invalid command. Try again.")
