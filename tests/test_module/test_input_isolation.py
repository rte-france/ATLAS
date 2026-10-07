"""
Check that no module pollutes the Current Input State through the copy it is given.

Each workflow is replayed job by job: the module runs on ``cis.get_data(copy=True)``, as in the
orchestrator, and the CIS must be exactly the same afterwards. The CIS then only changes through
the change sets of the module.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.abstract_scenario_matrix import AbstractScenarioMatrix
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.timeseries import Timeseries
from atlas.objects.business_model import BusinessModel
from atlas.orchestrator.current_input_state import CurrentInputState
from atlas.orchestrator.handler.cis_handler import CISHandler
from atlas.orchestrator.workflow.workflow import Workflow

WORKFLOW_CONFIGS = [
    pytest.param(Path("tests/dataset/parameters/day_ahead/workflow.yml"), id="day_ahead"),
    pytest.param(Path("tests/dataset/parameters/intraday/workflow.yml"), id="intraday"),
]


IMMUTABLE_TYPES = (type(None), bool, int, float, str, Enum, date, time, timedelta)


def _fingerprint(value: Any) -> Any:
    """Comparable view of a value: business objects by identity, everything else by content.

    Unknown types are rejected: keeping them as is would compare an object with itself, so an
    in-place mutation would go unnoticed.
    """
    if isinstance(value, IMMUTABLE_TYPES):
        return value
    if isinstance(value, BusinessModel):
        return ("ref", id(value))
    if isinstance(value, (AbstractTimeseries, AbstractScenarioMatrix)):
        state = {name: _fingerprint(attr) for name, attr in vars(value).items() if "cache" not in name}
        return (type(value).__name__, state)
    if isinstance(value, pl.LazyFrame):
        value = value.collect()
    if isinstance(value, pl.DataFrame):
        return ("frame", tuple(value.schema.items()), tuple(value.hash_rows()))
    if isinstance(value, list | tuple):
        return [_fingerprint(item) for item in value]
    if isinstance(value, dict):
        return {key: _fingerprint(item) for key, item in value.items()}
    raise TypeError(f"No fingerprint for {type(value).__name__}: add it to _fingerprint")


def _dataset_fingerprint(dataset: AtlasDataset) -> dict[tuple[str, str], Any]:
    return {
        (type_name, obj.name): (id(obj), {field: _fingerprint(getattr(obj, field)) for field in type(obj).model_fields})
        for type_name in type(dataset).model_fields
        for obj in getattr(dataset, type_name)
    }


def _differences(before: dict[tuple[str, str], Any], after: dict[tuple[str, str], Any]) -> list[str]:
    differences = [f"{key} removed" for key in before.keys() - after.keys()]
    differences += [f"{key} added" for key in after.keys() - before.keys()]
    for key in before.keys() & after.keys():
        (id_before, fields_before), (id_after, fields_after) = before[key], after[key]
        if id_before != id_after:
            differences.append(f"{key} replaced by another object")
        differences += [
            f"{key}.{field} modified" for field in fields_before if fields_before[field] != fields_after[field]
        ]
    return sorted(differences)


def test_fingerprint_rejects_unknown_types():
    with pytest.raises(TypeError, match="set"):
        _fingerprint({1, 2})


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda values: values.append(4.0), id="list"),
        pytest.param(lambda values: values[0].set_value(datetime(2025, 1, 1), 99.0), id="timeseries"),
    ],
)
def test_fingerprint_detects_in_place_mutations(mutate):
    values: list[Any] = [Timeseries(pl.DataFrame({"time": [datetime(2025, 1, 1)], "value": [1.0]}))]
    before = _fingerprint(values)

    mutate(values)

    assert _fingerprint(values) != before


@pytest.mark.parametrize("workflow_config", WORKFLOW_CONFIGS)
def test_modules_do_not_pollute_the_current_input_state(workflow_config):
    workflow = Workflow.from_file(workflow_config)
    cis = CurrentInputState.from_directory(workflow.parameters.resolve_path(workflow.parameters.dataset_path))

    for job in workflow.jobs:
        before = _dataset_fingerprint(cis.data)

        job.run(cis.get_data(copy=True))

        differences = _differences(before, _dataset_fingerprint(cis.data))
        assert not differences, f"{job.name} modified the CIS through its copy: {differences[:10]}"
        assert job.result is not None
        CISHandler.apply(job.result.change_sets, cis)
