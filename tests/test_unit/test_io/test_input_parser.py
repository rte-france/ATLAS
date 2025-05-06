from unittest import mock

import polars as pl
import pytest

import atlas.config as cfg
from atlas import InputLoader


# Fixtures for mocks
@pytest.fixture
def mock_logger():
    with mock.patch.object(cfg, "logger") as logger_mock:
        yield logger_mock


@pytest.fixture
def mock_model_mapping_name():
    with mock.patch.object(cfg, "MODEL_MAPPING_NAME", {"wind": "some_class"}):
        yield


@pytest.fixture
def fake_csv(tmp_path):
    file = tmp_path / "test.csv"
    file.write_text("col1;col2\nval1;val2")
    return file


@pytest.fixture
def fake_parquet(tmp_path):
    file = tmp_path / "test.parquet"
    df = pl.DataFrame({"col1": ["val1"], "col2": ["val2"]})
    df.write_parquet(file)
    return file


# Tests for read_data_file
def test_read_data_file_csv(fake_csv):
    df = InputLoader.read_data_file(fake_csv, separator=";")
    assert isinstance(df, pl.DataFrame)
    assert df.shape == (1, 2)


def test_read_data_file_parquet(fake_parquet):
    df = InputLoader.read_data_file(fake_parquet)
    assert isinstance(df, pl.DataFrame)
    assert df.shape == (1, 2)


# Tests for load_metadata
def test_load_metadata_exists(tmp_path):
    metadata_dir = tmp_path / "scenario_matrix/wind/instance/attribute"
    metadata_dir.mkdir(parents=True)
    metadata_path = metadata_dir / "metadata.json"
    metadata_path.write_text('{"key": "value"}')

    metadata = InputLoader.load_metadata(tmp_path, "instance", "wind", "attribute", "scenario_matrix")
    assert metadata == {"key": "value"}


def test_load_metadata_not_exists(tmp_path):
    metadata = InputLoader.load_metadata(tmp_path, "instance", "wind", "attribute", "scenario_matrix")
    assert metadata == {}


# Tests for _load_timeseries
def test__load_timeseries_success(tmp_path, mock_logger):
    timeseries_dir = tmp_path / "timeseries/wind/instance"
    timeseries_dir.mkdir(parents=True)
    file_path = timeseries_dir / "attribute.parquet"
    df = pl.DataFrame({"timestamp": [1], "value": [100]})
    df.write_parquet(file_path)

    with mock.patch("atlas.math.timeseries.Timeseries.from_file") as timeseries_mock:
        InputLoader._load_timeseries(
            base_path=tmp_path,
            object_type="wind",
            name="instance",
            attribute_name="attribute",
        )
        timeseries_mock.assert_called_once()


def test__load_timeseries_no_timeseries_dir(tmp_path):
    with pytest.raises(NotADirectoryError):
        InputLoader._load_timeseries(
            base_path=tmp_path,
            object_type="wind",
            name="instance",
            attribute_name="attribute",
        )


def test__load_timeseries_no_file(tmp_path):
    (tmp_path / "timeseries/wind/instance").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        InputLoader._load_timeseries(
            base_path=tmp_path,
            object_type="wind",
            name="instance",
            attribute_name="attribute",
        )


def test__load_matrix_no_dir(tmp_path):
    with pytest.raises(NotADirectoryError):
        InputLoader._load_matrix(
            base_path=tmp_path,
            name="instance",
            object_type="wind",
            attribute_name="attribute",
            matrix_type="forecasting_matrix",
        )


def test__load_matrix_no_file(tmp_path):
    (tmp_path / "forecasting_matrix/wind/instance/attribute").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        InputLoader._load_matrix(
            base_path=tmp_path,
            name="instance",
            object_type="wind",
            attribute_name="attribute",
            matrix_type="forecasting_matrix",
        )
