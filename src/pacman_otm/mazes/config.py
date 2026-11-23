"""
Checking plain config values (from TOML or JSON) against Python types, with
errors that name the field, e.g. "topography.spacing: expected [min, max]".
Shared by rules, recipes, shapes and content placers.
"""

import inspect
from collections.abc import Callable, Iterable
from typing import Any, Literal, get_args, get_origin, get_type_hints


class ConfigError(ValueError):
    """A config value or key that cannot be used; the message names the field."""


def convert(value: Any, expected: Any, where: str) -> Any:
    """`value` as type `expected` (int, float, str, bool, Literal[...], tuple[int, ...])."""

    if get_origin(expected) is Literal:
        choices = get_args(expected)

        if value not in choices:
            raise ConfigError(f"{where}: expected one of {', '.join(map(str, choices))}, got {value!r}.")

        return value

    if get_origin(expected) is tuple:
        items = get_args(expected)

        if not isinstance(value, list | tuple) or len(value) != len(items):
            raise ConfigError(f"{where}: expected a list of {len(items)} values, got {value!r}.")

        return tuple(convert(item, kind, f"{where}[{index}]") for index, (item, kind) in enumerate(zip(value, items)))

    # bool is an int subclass, but True is never a sensible count or size.
    if expected is bool:
        if not isinstance(value, bool):
            raise ConfigError(f"{where}: expected true or false, got {value!r}.")
        return value

    if expected is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{where}: expected an integer, got {value!r}.")
        return value

    if expected is float:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ConfigError(f"{where}: expected a number, got {value!r}.")
        return float(value)

    if expected is str:
        if not isinstance(value, str):
            raise ConfigError(f"{where}: expected text, got {value!r}.")
        return value

    raise TypeError(f"{where}: unsupported parameter type {expected!r}.")


def check_keys(params: dict[str, Any], known: Iterable[str], where: str, owner: str) -> None:
    unknown = sorted(set(params) - set(known))

    if unknown:
        expected = ", ".join(sorted(known)) or "none"
        raise ConfigError(
            f"{where}: unknown parameter(s) {', '.join(unknown)} for {owner}; "
            f"its parameters are: {expected}."
        )


def keyword_params(
    function: Callable[..., Any],
    params: dict[str, Any],
    where: str,
    owner: str,
    skip: int,
) -> dict[str, Any]:
    """
    Check params against a function's keyword parameters (after the first
    `skip` positional ones) and convert them to the annotated types.
    """
    signature = inspect.signature(function)
    hints = get_type_hints(function)
    accepted = list(signature.parameters.values())[skip:]

    check_keys(params, [parameter.name for parameter in accepted], where, owner)

    values = {}

    for parameter in accepted:
        if parameter.name in params:
            values[parameter.name] = convert(params[parameter.name], hints[parameter.name], f"{where}.{parameter.name}")
        elif parameter.default is inspect.Parameter.empty:
            raise ConfigError(f"{where}.{parameter.name}: missing for {owner}.")

    return values
