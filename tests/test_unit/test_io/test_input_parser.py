from unittest.mock import MagicMock, patch

import polars as pl
import pytest

import atlas.config as cfg
from atlas.io.input_loader import InputLoader


@pytest.fixture
def mock_model_mapping():
    class DummyModel:
        def __init__(self, **kwargs):
            self.attrs = kwargs

    return {"hydro": DummyModel}


@pytest.fixture
def temp_input_dir(tmp_path, mock_model_mapping):
    # Setup directory structure
    (tmp_path / "objects").mkdir()
    (tmp_path / "timeseries" / "hydro").mkdir(parents=True)
    (tmp_path / "scenario_matrix" / "hydro").mkdir(parents=True)
    (tmp_path / "forecasting_matrix" / "hydro").mkdir(parents=True)

    # Write sample object definition
    pl.DataFrame(
        [
            {
                "name": "fr_hydro",
                "energy": "timeseries",
                "scenario": "scenario_matrix",
                "forecast": "forecasting_matrix",
            }
        ]
    ).write_csv(tmp_path / "objects" / "hydro.csv", separator=";")

    # Create empty dummy data files
    (tmp_path / "timeseries" / "hydro" / "fr_hydro.parquet").touch()
    (tmp_path / "scenario_matrix" / "hydro" / "fr_hydro.parquet").touch()
    (tmp_path / "forecasting_matrix" / "hydro" / "fr_hydro.parquet").touch()

    return tmp_path


@patch.dict(cfg.__dict__, {"MODEL_MAPPING_NAME": {"hydro": MagicMock()}})
@patch("atlas.io.input_loader.InputLoader._load_timeseries", return_value="TS")
@patch("atlas.io.input_loader.InputLoader._load_matrix", return_value="MATRIX")
def test_from_directory_success(mock_matrix, mock_ts, temp_input_dir, mock_model_mapping):
    with patch.dict(cfg.__dict__, {"MODEL_MAPPING_NAME": mock_model_mapping}):
        result = InputLoader.from_directory(temp_input_dir)
        assert "hydro" in result
        assert isinstance(result["hydro"][0], mock_model_mapping["hydro"])
        assert result["hydro"][0].attrs["energy"] == "TS"
        assert result["hydro"][0].attrs["scenario"] == "MATRIX"


@patch("atlas.io.input_loader.pl.read_csv", side_effect=Exception("bad csv"))
@patch.dict(cfg.__dict__, {"MODEL_MAPPING_NAME": {"hydro": MagicMock()}})
def test_parse_objects_handles_bad_file_gracefully(mock_read_csv, tmp_path):
    (tmp_path / "objects").mkdir()
    (tmp_path / "objects" / "hydro.csv").write_text("bad csv")

    result = InputLoader._parse_objects_from_directory(tmp_path / "objects")
    assert result == {}


def test_read_data_file_csv(tmp_path):
    csv_path = tmp_path / "test.csv"
    pl.DataFrame({"a": [1, 2]}).write_csv(csv_path)
    df = InputLoader._read_data_file(csv_path)
    assert isinstance(df, pl.DataFrame)


def test_read_data_file_invalid(tmp_path):
    fake_path = tmp_path / "invalid.foo"
    fake_path.write_text("whatever")
    with pytest.raises(NotImplementedError):
        InputLoader._read_data_file(fake_path)
