"""
Rule names -> rule classes, and building rules from plain config (TOML or JSON).
Errors name the offending field, e.g. "rules[2].size: expected an integer".
"""

import tomllib
from dataclasses import MISSING, fields
from pathlib import Path
from typing import Any, get_type_hints

from pacman_otm.mazes.config import ConfigError, convert
from pacman_otm.mazes.rules.base import Rule, RuleSet
from pacman_otm.mazes.rules.hard import Connected, Enclosed, SizeBounds
from pacman_otm.mazes.rules.local import MaxBlock, NoDiagonalContact
from pacman_otm.mazes.rules.structure import (
    MaxCorridorLength,
    MaxDeadEnds,
    MaxStraightRun,
    MinJunctionShare,
    MinLoops,
    MirrorSymmetric,
    WalkableFraction,
)

RULES: frozendict[str, type[Rule]] = frozendict(
    {
        rule.name: rule
        for rule in (
            SizeBounds,
            Connected,
            Enclosed,
            MaxBlock,
            NoDiagonalContact,
            MaxDeadEnds,
            MaxStraightRun,
            MaxCorridorLength,
            MinJunctionShare,
            MinLoops,
            WalkableFraction,
            MirrorSymmetric,
        )
    }
)


class RuleConfigError(ConfigError):
    """A rule config that names an unknown rule or has a bad parameter."""


def rule_from_config(config: dict[str, Any], where: str = "rule") -> Rule:
    """Build one rule from {"rule": name, **params}."""

    if not isinstance(config, dict):
        raise RuleConfigError(f"{where}: expected a table with a 'rule' key.")

    name = config.get("rule")

    if name not in RULES:
        raise RuleConfigError(
            f"{where}: unknown rule {name!r}; known rules are {', '.join(sorted(RULES))}."
        )

    rule_class = RULES[name]
    hints = get_type_hints(rule_class)
    params = {key: value for key, value in config.items() if key != "rule"}
    known = {field.name for field in fields(rule_class)}

    unknown = sorted(set(params) - known)

    if unknown:
        expected = ", ".join(sorted(known)) or "none"
        raise RuleConfigError(
            f"{where}: unknown parameter(s) {', '.join(unknown)} for rule '{name}'; "
            f"its parameters are: {expected}."
        )

    values = {}

    for field in fields(rule_class):
        if field.name not in params:
            if field.default is MISSING:
                raise RuleConfigError(
                    f"{where}.{field.name}: missing for rule '{name}'."
                )
            continue

        values[field.name] = _convert(
            params[field.name], hints[field.name], f"{where}.{field.name}"
        )

    try:
        return rule_class(**values)
    except ValueError as error:
        raise RuleConfigError(f"{where} ({name}): {error}") from error


def rules_from_config(configs: list[dict[str, Any]], where: str = "rules") -> RuleSet:
    if not isinstance(configs, list):
        raise RuleConfigError(
            f"{where}: expected a list of rule tables ([[rules]] in TOML)."
        )

    return RuleSet(
        rule_from_config(config, f"{where}[{index}]")
        for index, config in enumerate(configs)
    )


def rules_from_toml(path: Path) -> RuleSet:
    """The [[rules]] tables of a TOML file; other keys are ignored."""

    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
    except tomllib.TOMLDecodeError as error:
        raise RuleConfigError(f"{path}: invalid TOML: {error}") from error

    return rules_from_config(data.get("rules", []), where=f"{path.name}: rules")


def _convert(value: Any, expected: Any, where: str) -> Any:
    try:
        return convert(value, expected, where)
    except ConfigError as error:
        raise RuleConfigError(str(error)) from None
