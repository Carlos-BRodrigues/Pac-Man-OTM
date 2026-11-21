from dataclasses import dataclass, field
from typing import Any, Literal

MazeSource = Literal["layout", "generated"]


@dataclass(frozen=True)
class MazeOrigin:
    """
    How a maze was made. Saved with every result, so a run can say which maze
    it used and, for generated mazes, how to make the same maze again.
    """

    source: MazeSource
    name: str
    generator: str | None = None
    params: frozendict[str, Any] = field(default_factory=frozendict)
    seed: int | None = None

    def __post_init__(self) -> None:
        if self.source not in ("layout", "generated"):
            raise ValueError(f"Unknown maze source '{self.source}'.")

        # Accept a plain dict but always store a read-only one.
        object.__setattr__(self, "params", frozendict(self.params))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "name": self.name,
            "generator": self.generator,
            "params": dict(self.params),
            "seed": self.seed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MazeOrigin:
        return cls(
            source=data["source"],
            name=data["name"],
            generator=data.get("generator"),
            params=frozendict(data.get("params") or {}),
            seed=data.get("seed"),
        )
