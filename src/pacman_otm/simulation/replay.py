from pathlib import Path

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


class ResultSequence:
    """
    Recorded runs to replay one after another: a single result file, or the
    runs of an experiment folder (runs/run_0001/result.json, ...) in run order.
    Results are loaded when first shown; a few are kept in memory.
    """

    CACHE_SIZE = 3

    def __init__(self, paths: list[Path], title: str) -> None:
        if not paths:
            raise ValueError("Nothing to replay.")

        self.paths = list(paths)
        self.title = title
        self._cache: dict[int, SimulationResult] = {}

    @classmethod
    def from_path(cls, path: Path) -> ResultSequence:
        if path.is_file():
            return cls([path], path.stem)

        if path.is_dir():
            # An experiment folder, or its runs/ folder.
            files = sorted(path.glob("runs/*/result.json")) or sorted(path.glob("*/result.json"))

            if not files:
                raise ValueError(
                    f"'{path}' holds no run files; expected an experiment folder "
                    f"with runs/run_0001/result.json, ... ('experiment' writes these)."
                )

            return cls(files, path.name)

        raise ValueError(f"'{path}' does not exist.")

    def __len__(self) -> int:
        return len(self.paths)

    def load(self, index: int) -> SimulationResult:
        if not 0 <= index < len(self.paths):
            raise IndexError(f"Invalid run index: {index}")

        if index not in self._cache:
            if len(self._cache) >= self.CACHE_SIZE:
                self._cache.pop(next(iter(self._cache)))

            self._cache[index] = SimulationResult.load_json(self.paths[index])

        return self._cache[index]

    def label(self, index: int) -> str:
        if len(self.paths) == 1:
            return self.title

        return f"run {index + 1}/{len(self.paths)} ({self.paths[index].parent.name})"
