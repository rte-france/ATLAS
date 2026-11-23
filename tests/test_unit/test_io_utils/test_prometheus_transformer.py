import os

import pendulum
import pytest

from atlas.io_utils import prometheus_transformer
from atlas.io_utils.prometheus_transformer import (
    PrometheusToAtlasDataParser,
    _find_file_with_subpaths,
    _find_in_index,
    _index_paths_by_part,
    _list_all_files,
)


def _make_parser(tmp_path) -> PrometheusToAtlasDataParser:
    return PrometheusToAtlasDataParser(
        timeseries_path=tmp_path / "timeseries",
        hdf5_path=tmp_path / "data.hdf5",
        output_dir=tmp_path / "output",
        default_value=False,
    )


def test_read_and_parse_csv_infers_sparse_numeric_columns_across_full_file(tmp_path):
    # A forecasting matrix column whose first non-null value only appears after
    # row 100 must still be inferred as numeric, not silently typed as String
    # by polars' default 100-row schema inference sample.
    start = pendulum.datetime(2028, 1, 1)
    lines = ["TimeStep;01/07/2028 00:00:00;26/09/2028 15:00:00"]
    for i in range(150):
        timestep = start.add(hours=i).format("DD_MM_YYYY_HH_mm_ss")
        value = "-14739.57" if i == 149 else ""
        lines.append(f"{timestep};1.0;{value}")

    csv_file = tmp_path / "MaximumPowerForecast.csv"
    csv_file.write_text("\r\n".join(lines) + "\r\n")

    parser = _make_parser(tmp_path)
    df = parser._read_and_parse_csv(str(csv_file))

    assert df["26/09/2028 15:00:00"].dtype.is_numeric()
    assert df["26/09/2028 15:00:00"].drop_nulls().to_list() == [-14739.57]


def _tree_paths(root: str) -> list[str]:
    """Paths of a timeseries tree, in the order a walk could give them, with names that prefix one another."""
    parts = [
        ("Equipment", "Thermic", "unit_10", "timeseries", "VariableCost.csv"),
        ("Equipment", "Thermic", "unit_1", "timeseries", "VariableCost.csv"),
        ("Equipment", "Thermic", "unit_1", "timeseries", "old", "VariableCost.csv"),
        ("Equipment", "Thermic", "unit_1", "forecast_matrix", "MaximumPowerForecast.csv"),
        ("Equipment", "Wind", "unit_1", "timeseries", "VariableCost.csv"),
        ("Equipment", "Thermic", "unit_2", "unit_2", "timeseries", "MaximumPower.csv"),
    ]
    return [os.path.join(root, *p) for p in parts]


@pytest.mark.parametrize(
    ("object_type", "instance", "file_name"),
    [
        ("Thermic", "unit_1", "VariableCost.csv"),
        ("Thermic", "unit_10", "VariableCost.csv"),
        ("Wind", "unit_1", "VariableCost.csv"),
        ("Thermic", "unit_1", "MaximumPowerForecast.csv"),
        ("Thermic", "unit_2", "MaximumPower.csv"),
        ("Thermic", "unit_3", "VariableCost.csv"),
        ("Hydraulic", "unit_1", "VariableCost.csv"),
    ],
)
def test_the_index_finds_the_same_file_as_the_linear_search(object_type, instance, file_name):
    paths = _tree_paths(os.path.join(os.sep, "data"))

    found = _find_in_index(_index_paths_by_part(paths), object_type, instance, file_name)

    assert found == _find_file_with_subpaths(paths, object_type, instance, file_name)


def test_the_index_keeps_the_first_match_in_the_order_of_the_paths():
    paths = _tree_paths(os.path.join(os.sep, "data"))

    found = _find_in_index(_index_paths_by_part(paths), "Thermic", "unit_1", "VariableCost.csv")

    assert found == paths[1]


def test_the_timeseries_tree_is_walked_once_for_all_the_lookups(tmp_path, monkeypatch):
    for path in _tree_paths(str(tmp_path / "timeseries")):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").close()
    walks = []
    monkeypatch.setattr(
        prometheus_transformer, "_list_all_files", lambda root: walks.append(root) or _list_all_files(root)
    )
    parser = _make_parser(tmp_path)

    found = [
        parser._find_timeseries_file("Thermic", unit, "VariableCost.csv") for unit in ("unit_1", "unit_10", "unit_3")
    ]

    assert len(walks) == 1
    assert [None if f is None else os.path.relpath(f, tmp_path) for f in found] == [
        os.path.join("timeseries", "Equipment", "Thermic", "unit_1", "timeseries", "VariableCost.csv"),
        os.path.join("timeseries", "Equipment", "Thermic", "unit_10", "timeseries", "VariableCost.csv"),
        None,
    ]
