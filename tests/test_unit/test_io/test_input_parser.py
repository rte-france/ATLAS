import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

import atlas.config as cfg
from atlas.io.input_parser import InputLoader


@pytest.fixture
def mock_csv_data():
    return """id,name,value
1,test1,100
2,test2,200
3,test3,300"""


@pytest.fixture
def sample_df():
    return pl.DataFrame({"id": [1, 2, 3], "name": ["test1", "test2", "test3"], "value": [100, 200, 300]})


@pytest.fixture
def temp_csv_file(mock_csv_data):
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(mock_csv_data.encode("utf-8"))
        temp_file = f.name
    yield temp_file
    os.unlink(temp_file)


@pytest.fixture
def temp_parquet_file(sample_df):
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        temp_file = f.name
    sample_df.write_parquet(temp_file)
    yield temp_file
    os.unlink(temp_file)


@pytest.fixture
def temp_directory():
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


class MockModelClass:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def test_from_csv(temp_csv_file, sample_df):
    result = InputLoader._from_csv(temp_csv_file)
    assert result.shape == sample_df.shape
    assert result.columns == sample_df.columns
    assert result["id"].to_list() == sample_df["id"].to_list()


def test_from_parquet(temp_parquet_file, sample_df):
    result = InputLoader._from_parquet(temp_parquet_file)
    assert result.shape == sample_df.shape
    assert result.columns == sample_df.columns
    assert result["id"].to_list() == sample_df["id"].to_list()


def test_from_file_csv(temp_csv_file, sample_df):
    result = InputLoader.from_file(temp_csv_file)
    assert result.shape == sample_df.shape
    assert result.columns == sample_df.columns


def test_from_file_parquet(temp_parquet_file, sample_df):
    result = InputLoader.from_file(temp_parquet_file)
    assert result.shape == sample_df.shape
    assert result.columns == sample_df.columns


def test_from_file_unsupported_extension():
    with pytest.raises(ValueError, match=r"Unsupported file extension: .txt"):
        InputLoader.from_file("test.txt")


def test_from_directory_not_found():
    with pytest.raises(FileNotFoundError):
        InputLoader.from_directory("nonexistent_directory")


def test_from_directory_not_a_directory(temp_csv_file):
    with pytest.raises(NotADirectoryError):
        InputLoader.from_directory(temp_csv_file)


@patch.dict(cfg.MODEL_MAPPING_NAME, {"test_model": MockModelClass})
def test_from_directory(temp_directory, mock_csv_data):
    # Create test CSV file in temp directory
    file_path = Path(temp_directory) / "test_model.csv"
    with open(file_path, "w") as f:
        f.write(mock_csv_data)

    result = InputLoader.from_directory(temp_directory)

    assert "test_model" in result
    assert len(result["test_model"]) == 3
    assert isinstance(result["test_model"][0], MockModelClass)
    assert result["test_model"][0].id == 1
    assert result["test_model"][0].name == "test1"
    assert result["test_model"][0].value == 100


@patch.dict(cfg.MODEL_MAPPING_NAME, {"test_model": MockModelClass})
def test_instantiate_objects_from_file(temp_csv_file):
    result = InputLoader._instantiate_objects_from_file(Path(temp_csv_file), "test_model")

    assert len(result) == 3
    assert isinstance(result[0], MockModelClass)
    assert result[0].id == 1
    assert result[0].name == "test1"
    assert result[0].value == 100


def test_parse_business_objects(temp_directory, mock_csv_data):
    # Create test CSV files in temp directory
    for name in ["users", "products"]:
        file_path = Path(temp_directory) / f"{name}.csv"
        with open(file_path, "w") as f:
            f.write(mock_csv_data)

    result = InputLoader.parse_business_objects(temp_directory)

    assert "users" in result
    assert "products" in result
    assert len(result) == 2
    assert result["users"].shape == (3, 3)
    assert result["products"].shape == (3, 3)


def test_parse_business_objects_directory_not_found():
    with pytest.raises(FileNotFoundError):
        InputLoader.parse_business_objects("nonexistent_directory")


@patch("atlas.math.timeseries.Timeseries")
def test_load_timeseries_from_file(mock_timeseries, temp_csv_file, sample_df):
    mock_instance = MagicMock()
    mock_timeseries.return_value = mock_instance

    result = InputLoader.load_timeseries_from_file(temp_csv_file)

    mock_timeseries.assert_called_once()
    assert result == mock_instance


@patch("atlas.math.scenario_matrix..ScenarioMatrix")
def test_load_scenario_matrix_from_file(mock_scenario_matrix, temp_directory):
    # Setup
    instance_name = "wind_turbine1"
    instance_dir = Path(temp_directory) / instance_name
    instance_dir.mkdir()

    # Create parquet files
    for scenario in ["scenario1", "scenario2"]:
        with open(instance_dir / f"{scenario}.parquet", "wb") as f:
            pass  # Just create empty files for the test

    # Mock the timeseries loading
    mock_ts1 = MagicMock()
    mock_ts2 = MagicMock()

    with patch.object(InputLoader, "load_timeseries_from_file") as mock_load:
        mock_load.side_effect = [mock_ts1, mock_ts2]

        mock_instance = MagicMock()
        mock_scenario_matrix.return_value = mock_instance

        result = InputLoader.load_scenario_matrix_from_file(temp_directory, instance_name)

        # Assertions
        assert mock_load.call_count == 2
        mock_scenario_matrix.assert_called_once()
        assert result == mock_instance


def test_load_scenario_matrix_not_found():
    with pytest.raises(FileNotFoundError):
        InputLoader.load_scenario_matrix_from_file("base_dir", "nonexistent_instance")


@patch("atlas.math.forecasting_matrix.ForecastingMatrix")
def test_load_forecasting_matrix(mock_forecasting_matrix, temp_directory):
    # Setup
    instance_name = "wind_turbine1"
    instance_dir = Path(temp_directory) / instance_name
    instance_dir.mkdir()

    # Create parquet files
    for forecast in ["forecast1", "forecast2"]:
        with open(instance_dir / f"{forecast}.parquet", "wb") as f:
            pass  # Just create empty files for the test

    # Mock the timeseries loading
    mock_ts1 = MagicMock()
    mock_ts2 = MagicMock()

    with patch.object(InputLoader, "load_timeseries_from_file") as mock_load:
        mock_load.side_effect = [mock_ts1, mock_ts2]

        mock_instance = MagicMock()
        mock_forecasting_matrix.return_value = mock_instance

        result = InputLoader.load_forecasting_matrix(temp_directory, instance_name)

        # Assertions
        assert mock_load.call_count == 2
        mock_forecasting_matrix.assert_called_once()
        assert result == mock_instance


def test_load_forecasting_matrix_not_found():
    with pytest.raises(FileNotFoundError):
        InputLoader.load_forecasting_matrix("base_dir", "nonexistent_instance")


def test_load_metadata_exists(temp_directory):
    # Create metadata file
    metadata = {"version": "1.0", "description": "Test metadata"}
    metadata_path = Path(temp_directory) / "metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f)

    result = InputLoader.load_metadata(temp_directory)

    assert result == metadata


def test_load_metadata_not_exists(temp_directory):
    result = InputLoader.load_metadata(temp_directory)
    assert result == {}
