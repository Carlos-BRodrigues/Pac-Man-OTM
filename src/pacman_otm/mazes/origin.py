from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Literal

MazeSource = Literal["layout", "generated"]


def package_version() -> str:
    """The installed pacman-otm version: a generator change may change what a seed makes."""
    try:
        return version("pacman-otm")
    except PackageNotFoundError:
        return "unknown"


def deep_freeze(value: Any) -> Any:
    """dicts -> frozendict, lists -> tuples, recursively: recorded params cannot change."""

    if isinstance(value, dict | frozendict):
        return frozendict({key: deep_freeze(item) for key, item in value.items()})

    if isinstance(value, list | tuple):
        return tuple(deep_freeze(item) for item in value)

    return value


def deep_thaw(value: Any) -> Any:
    """The inverse of deep_freeze, for JSON."""

    if isinstance(value, dict | frozendict):
        return {key: deep_thaw(item) for key, item in value.items()}

    if isinstance(value, list | tuple):
        return [deep_thaw(item) for item in value]

    return value


@dataclass(frozen=True)
class MazeOrigin:
    """
    How a maze was made. Saved with every result, so a run can say which maze
    it used and, for generated mazes, how to make the same maze again: the full
    recipe (params), the seed, and the package version that generated it.
    """

    source: MazeSource
    name: str
    generator: str | None = None
    params: frozendict[str, Any] = field(default_factory=frozendict)
    seed: int | None = None
    package_version: str | None = None

    def __post_init__(self) -> None:
        if self.source not in ("layout", "generated"):
            raise ValueError(f"Unknown maze source '{self.source}'.")

        # Accept plain nested dicts and lists but always store read-only ones.
        object.__setattr__(self, "params", deep_freeze(self.params))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "name": self.name,
            "generator": self.generator,
            "params": deep_thaw(self.params),
            "seed": self.seed,
            "package_version": self.package_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MazeOrigin:
        return cls(
            source=data["source"],
            name=data["name"],
            generator=data.get("generator"),
            params=data.get("params") or {},
            seed=data.get("seed"),
            package_version=data.get("package_version"),
        )
