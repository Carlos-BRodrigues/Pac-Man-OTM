"""
Maze rules: checks on a tile grid that say where they fail.

Rules see only tiles, never pellets or the start, so the same rule applies to
hand-written layouts, generated topography and repair steps alike.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, fields
from typing import Any, ClassVar

import numpy as np

Position = tuple[int, int]


@dataclass(frozen=True)
class Violation:
    rule: str
    message: str
    # Where the rule fails; empty for global rules such as a loop count.
    positions: tuple[Position, ...] = ()


class Rule(ABC):
    """
    Subclasses are frozen dataclasses whose fields are the rule's parameters,
    so a rule can be built from a recipe and saved back as plain data.
    """

    name: ClassVar[str]

    @abstractmethod
    def violations(self, grid: np.ndarray) -> list[Violation]: ...

    def holds_after_change(self, grid: np.ndarray, position: Position) -> bool:
        """Incremental check after one tile changed. Default: full check.
        Local rules can override this with a check of the neighbourhood."""
        return not self.violations(grid)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.name,
            **{field.name: getattr(self, field.name) for field in fields(self)},
        }

    def describe(self) -> str:
        """'max_block(tile=wall, size=5)': how the rule is shown to people."""
        params = ", ".join(
            f"{field.name}={getattr(self, field.name)}" for field in fields(self)
        )
        return f"{self.name}({params})"

    def _violation(self, message: str, positions: Iterable[Position] = ()) -> Violation:
        return Violation(
            rule=self.describe(), message=message, positions=tuple(positions)
        )


class RuleSet:
    """An ordered collection of rules, checked together."""

    def __init__(self, rules: Iterable[Rule]) -> None:
        self.rules: tuple[Rule, ...] = tuple(rules)

    def violations(self, grid: np.ndarray) -> list[Violation]:
        grid = np.asarray(grid)
        return [violation for rule in self.rules for violation in rule.violations(grid)]

    def holds(self, grid: np.ndarray) -> bool:
        return not self.violations(grid)

    def __iter__(self):
        return iter(self.rules)

    def __len__(self) -> int:
        return len(self.rules)

    def __add__(self, other: RuleSet) -> RuleSet:
        return RuleSet(self.rules + other.rules)
