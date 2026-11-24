"""
Regenerate the golden results. Run only when a behaviour change is intended:

    python tests/make_golden.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from golden_tools import GOLDEN_CASES, GOLDEN_DIR, run_case, summarize  # noqa: E402


def main() -> None:
    GOLDEN_DIR.mkdir(exist_ok=True)

    for file_name, controller, maze, seed, speeds in GOLDEN_CASES:
        summary = summarize(run_case(controller, maze, seed, speeds))
        path = GOLDEN_DIR / f"{file_name}.json"
        path.write_text(json.dumps(summary) + "\n", encoding="utf-8")
        print(f"Wrote {path} ({len(summary['actions'])} actions)")


if __name__ == "__main__":
    main()
