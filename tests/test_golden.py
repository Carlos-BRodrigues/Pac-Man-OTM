"""Re-run recorded simulations and require identical actions, states and metrics."""

import json

import pytest

from golden_tools import GOLDEN_CASES, GOLDEN_DIR, run_case, summarize


@pytest.mark.parametrize(
    ("file_name", "controller", "maze", "seed"),
    GOLDEN_CASES,
    ids=[case[0] for case in GOLDEN_CASES],
)
def test_matches_golden(file_name: str, controller: str, maze: str, seed: int) -> None:
    expected = json.loads(
        (GOLDEN_DIR / f"{file_name}.json").read_text(encoding="utf-8")
    )

    actual = summarize(run_case(controller, maze, seed))

    assert actual["actions"] == expected["actions"]
    assert actual["states"] == expected["states"]
    assert actual["status_targets"] == expected["status_targets"]
    assert actual["metrics"] == expected["metrics"]
    assert actual["controller"] == expected["controller"]
