import json
from pathlib import Path


def load_threshold(workflow_config: Path) -> float | None:
    threshold_path = Path(__file__).parent / "dataset" / "performance_thresholds.json"
    if not threshold_path.exists():
        return None
    thresholds = json.loads(threshold_path.read_text())
    return thresholds.get(workflow_config.parent.name, {}).get("workflow_execution_max_seconds")


def load_threshold_for_module(module_name: str) -> float | None:
    threshold_path = Path(__file__).parent / "dataset" / "performance_thresholds.json"
    if not threshold_path.exists():
        return None
    thresholds = json.loads(threshold_path.read_text())
    return thresholds.get(module_name, {}).get("execution_max_seconds")
