import json
import os
from dataclasses import dataclass
from pathlib import Path

import pytest

# Multiplier applied to all thresholds to absorb OS scheduling noise and system load variance.
THRESHOLD_MARGIN = 1.05


@dataclass(frozen=True)
class Timing:
    """Execution time measured by a performance test, and the threshold it is checked against."""

    name: str
    elapsed: float
    threshold: float | None


# Filled by check_execution_time, reported at the end of the session by tests/conftest.py.
TIMINGS: list[Timing] = []


def _load_thresholds() -> dict:
    threshold_path = Path(__file__).parent / "dataset" / "performance_thresholds.json"
    if not threshold_path.exists():
        return {}
    return json.loads(threshold_path.read_text())


def get_threshold(key: str, field: str = "execution_max_seconds") -> float | None:
    """
    Return the threshold of ``key`` in ``performance_thresholds.json``, margin included.

    :param key: Module name, or workflow config directory name.
    :param field: ``execution_max_seconds`` for modules, ``workflow_execution_max_seconds`` for workflows.
    :return: The threshold in seconds, or None if it is not defined.
    """
    value = _load_thresholds().get(key, {}).get(field)
    return value * THRESHOLD_MARGIN if value is not None else None


def check_execution_time(name: str, elapsed: float, key: str, field: str = "execution_max_seconds") -> None:
    """
    Record ``elapsed`` for the end-of-session report, then check it against the threshold of ``key``.

    The time is always recorded. The threshold is only enforced on CI, the test is skipped elsewhere
    or when no threshold is defined.

    :param name: Label shown in the report, e.g. ``DayAheadOrdersThermal[1]``.
    :param elapsed: Measured execution time in seconds.
    :param key: Module name, or workflow config directory name.
    :param field: ``execution_max_seconds`` for modules, ``workflow_execution_max_seconds`` for workflows.
    """
    threshold = get_threshold(key, field)
    TIMINGS.append(Timing(name, elapsed, threshold))
    if threshold is None:
        pytest.skip(f"No performance threshold defined for {key}")
    if not os.environ.get("CI"):
        pytest.skip(f"Performance threshold of {key} is only enforced on CI")
    assert elapsed <= threshold, f"{name} took {elapsed:.2f}s, expected <= {threshold:.2f}s"


def format_timings(timings: list[Timing], markdown: bool = False) -> list[str]:
    """
    Format timings as a table: name, measured time, threshold and share of the threshold used.

    :param markdown: Return a GitHub-flavoured markdown table instead of aligned text.
    """
    rows = [
        (
            t.name,
            f"{t.elapsed:.2f}s",
            f"{t.threshold:.2f}s" if t.threshold is not None else "-",
            f"{t.elapsed / t.threshold:.0%}" if t.threshold else "-",
        )
        for t in timings
    ]
    header = ("test", "elapsed", "threshold", "used")
    if markdown:
        return [
            "| " + " | ".join(header) + " |",
            "|---|---:|---:|---:|",
            *("| " + " | ".join(row) + " |" for row in rows),
        ]
    widths = [max(len(row[i]) for row in [header, *rows]) for i in range(len(header))]
    return [
        "  ".join(
            cell.ljust(w) if i == 0 else cell.rjust(w) for i, (cell, w) in enumerate(zip(row, widths, strict=True))
        )
        for row in [header, *rows]
    ]
