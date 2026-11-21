import json
from typing import Any


def _is_scalar(value: Any) -> bool:
    return not isinstance(value, (list, tuple, dict))


def _is_inline_list(value: list | tuple) -> bool:
    """
    Lists of scalars (a topography row, a coordinate) and lists of scalar
    pairs (pellets, a planned path) go on one line. Putting every element on
    its own line made result files many times larger without adding readability.
    """
    if all(_is_scalar(item) for item in value):
        return True

    return all(
        isinstance(item, (list, tuple))
        and len(item) == 2
        and all(_is_scalar(part) for part in item)
        for item in value
    )


def pretty_json(data: Any, indent: int = 4) -> str:

    def format_value(value: Any, level: int) -> str:
        spacing = " " * (indent * level)
        inner_spacing = " " * (indent * (level + 1))

        if isinstance(value, dict):
            if not value:
                return "{}"

            items = [
                inner_spacing
                + json.dumps(str(key))
                + ": "
                + format_value(item, level + 1)
                for key, item in value.items()
            ]
            return "{\n" + ",\n".join(items) + "\n" + spacing + "}"

        if isinstance(value, (list, tuple)):
            if not value:
                return "[]"

            if _is_inline_list(value):
                # json.dumps turns nested tuples into lists, matching json.dump
                return json.dumps(value, separators=(", ", ": "))

            items = [
                inner_spacing + format_value(item, level + 1)
                for item in value
            ]
            return "[\n" + ",\n".join(items) + "\n" + spacing + "]"

        return json.dumps(value)

    return format_value(data, 0)
