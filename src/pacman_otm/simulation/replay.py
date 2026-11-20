from pacman_otm.simulation.result import SimulationResult
from pacman_otm.simulation.frame import SimulationFrame


class ReplayPlayer:

    def __init__(self, result: SimulationResult) -> None:

        if not result.states:
            raise ValueError("Cannot replay an empty simulation result.")

        self.result = result
        self.current_index = 0

    @property
    def total_frames(self) -> int:
        return len(self.result.states)

    @property
    def at_start(self) -> bool:
        return self.current_index == 0

    @property
    def at_end(self) -> bool:
        return self.current_index == self.total_frames - 1

    @property
    def current_frame(self) -> SimulationFrame:
        return self.get_frame(self.current_index)

    def get_frame(self, index: int) -> SimulationFrame:

        if not 0 <= index < self.total_frames:
            raise IndexError(f"Invalid replay frame: {index}")

        action = None
        status = None

        if index > 0:

            action_index = index - 1

            if action_index < len(self.result.actions):
                action = self.result.get_action(action_index)

            if action_index < len(self.result.statuses):
                status = self.result.statuses[action_index]

        return SimulationFrame(
            state=self.result.get_state(index),
            action=action,
            status=status,
        )

    def seek(self, index: int) -> SimulationFrame:

        if not 0 <= index < self.total_frames:
            raise IndexError(f"Invalid replay frame: {index}")

        self.current_index = index

        return self.current_frame

    def next_frame(self) -> SimulationFrame:

        if not self.at_end:
            self.current_index += 1

        return self.current_frame

    def previous_frame(self) -> SimulationFrame:

        if not self.at_start:
            self.current_index -= 1

        return self.current_frame

    def first_frame(self) -> SimulationFrame:
        return self.seek(0)

    def last_frame(self) -> SimulationFrame:
        return self.seek(self.total_frames - 1)
