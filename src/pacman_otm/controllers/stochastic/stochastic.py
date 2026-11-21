from typing import Any

import numpy as np

from pacman_otm.controllers.controller import Controller


class StochasticController(Controller):
    """
    Base class for controllers whose decisions depend on randomness.

    All randomness must come from `self.rng`, a numpy Generator seeded at
    construction, so the same maze + controller + seed gives the same run.
    """

    controller_type = "stochastic"

    def __init__(self, seed: int | None = 42) -> None:
        super().__init__()
        self.seed = seed
        self.reset()

    def reset(self) -> None:
        """
        Re-seed the generator so a reused controller replays the same run.

        Subclasses with their own memory should extend this and call super().reset().
        """
        self.rng = np.random.default_rng(self.seed)

    def describe(self) -> dict[str, Any]:
        return {
            **super().describe(),
            "seed": self.seed,
        }
