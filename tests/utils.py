import json
import os
from pathlib import Path

# Multiplier applied to all thresholds to absorb OS scheduling noise and system load variance.
THRESHOLD_MARGIN = 1.05


def _load_thresholds() -> dict:
    threshold_path = Path(__file__).parent / "dataset" / "performance_thresholds.json"
    if not threshold_path.exists():
        return {}
    return json.loads(threshold_path.read_text())


def load_threshold(workflow_config: Path) -> float | None:
    if not os.environ.get("CI"):
        return None
    value = _load_thresholds().get(workflow_config.parent.name, {}).get("workflow_execution_max_seconds")
    return value * THRESHOLD_MARGIN if value is not None else None


def load_threshold_for_module(module_name: str) -> float | None:
    if not os.environ.get("CI"):
        return None
    value = _load_thresholds().get(module_name, {}).get("execution_max_seconds")
    return value * THRESHOLD_MARGIN if value is not None else None
