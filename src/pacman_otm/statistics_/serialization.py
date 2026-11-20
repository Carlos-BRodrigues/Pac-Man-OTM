import json
from typing import Any


def pretty_json(data: Any, indent: int = 4) -> str:

    def format_value(value: Any, level: int) -> str:
        spacing = " " * (indent * level)

        # Keep coordinate pairs on one line.
        if (
            isinstance(value, (list, tuple))
            and len(value) == 2
            and all(isinstance(item, (int, float)) for item in value)
        ):
            return json.dumps(list(value))

        if isinstance(value, dict):
            if not value:
                return "{}"

            lines = ["{"]
            for key, item in value.items():
                formatted_item = format_value(item, level + 1)
                lines.append(
                    " " * (indent * (level + 1))
                    + json.dumps(str(key))
                    + ": "
                    + formatted_item
                    + ","
                )

            lines[-1] = lines[-1].rstrip(",")
            lines.append(spacing + "}")
            return "\n".join(lines)

        if isinstance(value, (list, tuple)):
            if not value:
                return "[]"

            lines = ["["]
            for item in value:
                lines.append(
                    " " * (indent * (level + 1))
                    + format_value(item, level + 1)
                    + ","
                )

            lines[-1] = lines[-1].rstrip(",")
            lines.append(spacing + "]")
            return "\n".join(lines)

        return json.dumps(value)

    return format_value(data, 0)