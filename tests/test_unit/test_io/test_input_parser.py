from unittest.mock import MagicMock, Mock, patch

import pendulum
import polars as pl
import pytest

import atlas.config as cfg
from atlas.io.input_loader import InputLoader
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.scenario_matrix import LazyScenarioMatrix, ScenarioMatrix
from atlas.math.timeseries import Timeseries


@pytest.fixture
def mock_model_mapping():
    class DummyModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            for k, v in kwargs.items():
                setattr(self, k, v)

    return {
        "hydro": DummyModel,
        "thermal": DummyModel,
        "solar": DummyModel,
        "equipment": DummyModel,
    }


@pytest.fixture
def mock_model_order():
    return ["hydro", "thermal", "solar"]


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
                "start_date": "01/01/2023 00:00:00",
            }
        ]
    ).write_csv(tmp_path / "objects" / "hydro.csv", separator=";")

    # Create empty dummy data files
    (tmp_path / "timeseries" / "hydro" / "fr_hydro.parquet").touch()
    (tmp_path / "scenario_matrix" / "hydro" / "fr_hydro.parquet").touch()
    (tmp_path / "forecasting_matrix" / "hydro" / "fr_hydro.parquet").touch()

    return tmp_path


@pytest.fixture
def complex_input_dir(tmp_path, mock_model_mapping):
    # Setup directory structure
    (tmp_path / "objects").mkdir()
    # Create directories for all object types
    for obj_type in ["hydro", "thermal", "solar"]:
        (tmp_path / "timeseries" / obj_type).mkdir(parents=True, exist_ok=True)
        (tmp_path / "scenario_matrix" / obj_type).mkdir(parents=True, exist_ok=True)
        (tmp_path / "forecasting_matrix" / obj_type).mkdir(parents=True, exist_ok=True)

    # Write hydro object definition with reference to equipment
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

    # Write thermal object definition with reference to hydro
    pl.DataFrame(
        [
            {
                "name": "fr_thermal",
                "energy": "timeseries",
                "hydro": "fr_hydro",
            }
        ]
    ).write_csv(tmp_path / "objects" / "thermal.csv", separator=";")

    # Create dummy data files
    for obj_type in ["hydro", "thermal"]:
        prefix = ""
        name = f"{prefix}{obj_type}" if obj_type != "equipment" else "pump1"
        (tmp_path / "timeseries" / obj_type / f"{name}.parquet").touch()
        (tmp_path / "scenario_matrix" / obj_type / f"{name}.parquet").touch()
        (tmp_path / "forecasting_matrix" / obj_type / f"{name}.parquet").touch()

    return tmp_path


class TestInputLoader:
    @patch.dict(cfg.__dict__, {"MODEL_MAPPING_NAME": {"hydro": MagicMock()}})
    @patch("atlas.io.input_loader.InputLoader._load_timeseries", return_value="TS")
    @patch("atlas.io.input_loader.InputLoader._load_matrix", return_value="MATRIX")
    def test_from_directory_success(self, mock_matrix, mock_ts, temp_input_dir, mock_model_mapping):
        with patch.dict(
            cfg.__dict__,
            {"MODEL_MAPPING_NAME": mock_model_mapping, "MODEL_ORDER_INSTANTIATION": ["hydro"]},
        ):
            result = InputLoader.from_directory(temp_input_dir)
            assert "hydro" in result
            assert isinstance(result["hydro"][0], mock_model_mapping["hydro"])
            assert result["hydro"][0].energy == "TS"
            assert result["hydro"][0].scenario == "MATRIX"
            assert result["hydro"][0].forecast == "MATRIX"
            # Test that date was properly parsed
            assert result["hydro"][0].start_date == "2023-01-01 00:00:00"

    @patch.dict(
        cfg.__dict__,
        {
            "MODEL_MAPPING_NAME": {
                "hydro": MagicMock(),
                "thermal": MagicMock(),
                "solar": MagicMock(),
            }
        },
    )
    @patch("atlas.io.input_loader.InputLoader._load_timeseries", return_value="TS")
    @patch("atlas.io.input_loader.InputLoader._load_matrix", return_value="MATRIX")
    def test_from_directory_with_references(
        self,
        mock_matrix,
        mock_ts,
        complex_input_dir,
        mock_model_mapping,
        mock_model_order,
    ):
        with patch.dict(
            cfg.__dict__,
            {
                "MODEL_MAPPING_NAME": mock_model_mapping,
                "MODEL_ORDER_INSTANTIATION": mock_model_order,
            },
        ):
            result = InputLoader.from_directory(complex_input_dir)

            # Check that all objects were instantiated
            assert "hydro" in result
            assert "thermal" in result

            # Check references were resolved correctly

            assert result["thermal"][0].hydro == result["hydro"][0]

    def test_from_directory_nonexistent_dir(self):
        with pytest.raises(FileNotFoundError, match="Directory does not exist"):
            InputLoader.from_directory("/path/does/not/exist")

    def test_from_directory_not_a_dir(self, tmp_path):
        file_path = tmp_path / "not_a_dir"
        file_path.touch()
        with pytest.raises(NotADirectoryError, match="Path is not a directory"):
            InputLoader.from_directory(file_path)

    def test_from_directory_no_objects_dir(self, tmp_path):
        with pytest.raises(NotADirectoryError, match="Directory does not contain 'objects' subdirectory"):
            InputLoader.from_directory(tmp_path)

    @patch("atlas.io.input_loader.pl.read_csv", side_effect=Exception("bad csv"))
    @patch.dict(cfg.__dict__, {"MODEL_MAPPING_NAME": {"hydro": MagicMock()}})
    def test_parse_objects_handles_bad_file_gracefully(self, mock_read_csv, tmp_path):
        (tmp_path / "objects").mkdir()
        (tmp_path / "objects" / "hydro.csv").write_text("bad csv")

        result = InputLoader._parse_objects_from_directory(tmp_path / "objects")
        assert result == {}

    def test_read_data_file_csv(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        pl.DataFrame({"a": [1, 2]}).write_csv(csv_path)
        df = InputLoader._read_data_file(csv_path)
        assert isinstance(df, pl.DataFrame)
        assert df.shape == (2, 1)

    def test_read_data_file_parquet(self, tmp_path):
        parquet_path = tmp_path / "test.parquet"
        pl.DataFrame({"a": [1, 2]}).write_parquet(parquet_path)
        df = InputLoader._read_data_file(parquet_path)
        assert isinstance(df, pl.DataFrame)
        assert df.shape == (2, 1)

    def test_read_data_file_json(self, tmp_path):
        json_path = tmp_path / "test.json"
        pl.DataFrame({"a": [1, 2]}).write_json(json_path)
        df = InputLoader._read_data_file(json_path)
        assert isinstance(df, pl.DataFrame)
        assert df.shape == (2, 1)

    def test_read_data_file_invalid(self, tmp_path):
        fake_path = tmp_path / "invalid.foo"
        fake_path.write_text("whatever")
        with pytest.raises(NotImplementedError, match="File extension has to be csv, parquet or json"):
            InputLoader._read_data_file(fake_path)

    @patch("atlas.io.input_loader.Timeseries.from_file")
    def test_load_timeseries_eager(self, mock_from_file, tmp_path):
        # Setup
        base_path = tmp_path
        (tmp_path / "timeseries" / "hydro").mkdir(parents=True)
        (tmp_path / "timeseries" / "hydro" / "fr_hydro.parquet").touch()

        mock_from_file.return_value = Mock(spec=Timeseries)

        # Test
        result = InputLoader._load_timeseries(
            base_path=base_path,
            object_type="hydro",
            name="fr_hydro",
            attribute_name="energy",
            lazy=False,
        )

        # Assert
        mock_from_file.assert_called_once()
        assert isinstance(result, Mock)
        assert mock_from_file.call_args[1]["filters"] == ("attribute", "energy")

    @patch("atlas.io.input_loader.LazyTimeseries.from_file")
    def test_load_timeseries_lazy(self, mock_from_file, tmp_path):
        # Setup
        base_path = tmp_path
        (tmp_path / "timeseries" / "hydro").mkdir(parents=True)
        (tmp_path / "timeseries" / "hydro" / "fr_hydro.parquet").touch()

        mock_from_file.return_value = Mock(spec=LazyTimeseries)

        # Test
        result = InputLoader._load_timeseries(
            base_path=base_path,
            object_type="hydro",
            name="fr_hydro",
            attribute_name="energy",
            lazy=True,
        )

        # Assert
        mock_from_file.assert_called_once()
        assert isinstance(result, Mock)
        assert mock_from_file.call_args[1]["filters"] == ("attribute", "energy")

    def test_load_timeseries_no_directory(self, tmp_path):
        with pytest.raises(NotADirectoryError, match="Directory does not contain 'timeseries' subdirectory"):
            InputLoader._load_timeseries(
                base_path=tmp_path, object_type="hydro", name="fr_hydro", attribute_name="energy"
            )

    def test_load_timeseries_file_not_found(self, tmp_path):
        (tmp_path / "timeseries" / "hydro").mkdir(parents=True)
        with pytest.raises(FileNotFoundError, match="Path does not exist"):
            InputLoader._load_timeseries(
                base_path=tmp_path, object_type="hydro", name="fr_hydro", attribute_name="energy"
            )

    @patch("atlas.io.input_loader.ScenarioMatrix.from_file")
    def test_load_scenario_matrix_eager(self, mock_from_file, tmp_path):
        # Setup
        base_path = tmp_path
        (tmp_path / "scenario_matrix" / "hydro").mkdir(parents=True)
        (tmp_path / "scenario_matrix" / "hydro" / "fr_hydro.parquet").touch()

        mock_from_file.return_value = Mock(spec=ScenarioMatrix)

        # Test
        result = InputLoader._load_matrix(
            base_path=base_path,
            name="fr_hydro",
            object_type="hydro",
            attribute_name="scenario",
            matrix_type="scenario_matrix",
            lazy=False,
        )

        # Assert
        mock_from_file.assert_called_once()
        assert isinstance(result, Mock)
        assert mock_from_file.call_args[1]["filters"] == ("attribute", "scenario")

    @patch("atlas.io.input_loader.LazyScenarioMatrix.from_file")
    def test_load_scenario_matrix_lazy(self, mock_from_file, tmp_path):
        # Setup
        base_path = tmp_path
        (tmp_path / "scenario_matrix" / "hydro").mkdir(parents=True)
        (tmp_path / "scenario_matrix" / "hydro" / "fr_hydro.parquet").touch()

        mock_from_file.return_value = Mock(spec=LazyScenarioMatrix)

        # Test
        result = InputLoader._load_matrix(
            base_path=base_path,
            name="fr_hydro",
            object_type="hydro",
            attribute_name="scenario",
            matrix_type="scenario_matrix",
            lazy=True,
        )

        # Assert
        mock_from_file.assert_called_once()
        assert isinstance(result, Mock)
        assert mock_from_file.call_args[1]["filters"] == ("attribute", "scenario")

    @patch("atlas.io.input_loader.ForecastingMatrix.from_file")
    def test_load_forecasting_matrix_eager(self, mock_from_file, tmp_path):
        # Setup
        base_path = tmp_path
        (tmp_path / "forecasting_matrix" / "hydro").mkdir(parents=True)
        (tmp_path / "forecasting_matrix" / "hydro" / "fr_hydro.parquet").touch()

        mock_from_file.return_value = Mock(spec=ForecastingMatrix)

        # Test
        result = InputLoader._load_matrix(
            base_path=base_path,
            name="fr_hydro",
            object_type="hydro",
            attribute_name="forecast",
            matrix_type="forecasting_matrix",
            lazy=False,
            date_format_forecasting="DD_MM_YYYY HH:mm:ss",
        )

        # Assert
        mock_from_file.assert_called_once()
        assert isinstance(result, Mock)
        assert mock_from_file.call_args[1]["filters"] == ("attribute", "forecast")
        assert mock_from_file.call_args[1]["date_format"] == "DD_MM_YYYY HH:mm:ss"

    @patch("atlas.io.input_loader.LazyForecastingMatrix.from_file")
    def test_load_forecasting_matrix_lazy(self, mock_from_file, tmp_path):
        # Setup
        base_path = tmp_path
        (tmp_path / "forecasting_matrix" / "hydro").mkdir(parents=True)
        (tmp_path / "forecasting_matrix" / "hydro" / "fr_hydro.parquet").touch()

        mock_from_file.return_value = Mock(spec=LazyForecastingMatrix)

        # Test
        result = InputLoader._load_matrix(
            base_path=base_path,
            name="fr_hydro",
            object_type="hydro",
            attribute_name="forecast",
            matrix_type="forecasting_matrix",
            lazy=True,
        )

        # Assert
        mock_from_file.assert_called_once()
        assert isinstance(result, Mock)
        assert mock_from_file.call_args[1]["filters"] == ("attribute", "forecast")

    def test_load_matrix_invalid_type(self, tmp_path):
        (tmp_path / "forecasting_matrix" / "hydro").mkdir(parents=True)
        (tmp_path / "forecasting_matrix" / "hydro" / "fr_hydro.parquet").touch()

        with pytest.raises(ValueError, match="Invalid matrix type, should be scenario_matrix or forecasting_matrix"):
            InputLoader._load_matrix(
                base_path=tmp_path,
                name="fr_hydro",
                object_type="hydro",
                attribute_name="forecast",
                matrix_type="invalid_matrix",
                lazy=False,
            )

    def test_load_matrix_no_directory(self, tmp_path):
        with pytest.raises(NotADirectoryError, match="Directory does not contain 'forecasting_matrix' subdirectory"):
            InputLoader._load_matrix(
                base_path=tmp_path,
                name="fr_hydro",
                object_type="hydro",
                attribute_name="forecast",
                matrix_type="forecasting_matrix",
            )

    def test_load_matrix_file_not_found(self, tmp_path):
        (tmp_path / "forecasting_matrix" / "hydro").mkdir(parents=True)
        with pytest.raises(FileNotFoundError, match="Path does not exist"):
            InputLoader._load_matrix(
                base_path=tmp_path,
                name="fr_hydro",
                object_type="hydro",
                attribute_name="forecast",
                matrix_type="forecasting_matrix",
            )

    @patch("atlas.io.input_loader.pendulum.from_format")
    def test_parse_date_formats(self, mock_from_format, temp_input_dir, mock_model_mapping):
        mock_dt = pendulum.datetime(2023, 1, 1)
        mock_from_format.return_value = mock_dt

        with patch.dict(
            cfg.__dict__,
            {"MODEL_MAPPING_NAME": mock_model_mapping, "MODEL_ORDER_INSTANTIATION": ["hydro"]},
        ):
            with patch("atlas.io.input_loader.InputLoader._load_timeseries", return_value="TS"):
                with patch("atlas.io.input_loader.InputLoader._load_matrix", return_value="MATRIX"):
                    InputLoader._instantiate_math_objects_into_dict(
                        [{"name": "fr_hydro", "start_date": "01/01/2023 00:00:00"}],
                        "hydro",
                        temp_input_dir,
                        date_format_input_files="DD/MM/YYYY HH:mm:ss",
                    )

                    mock_from_format.assert_called_with("01/01/2023 00:00:00", "DD/MM/YYYY HH:mm:ss")

    def test_parse_date_format_exception_handling(self, temp_input_dir, mock_model_mapping):
        with patch.dict(
            cfg.__dict__,
            {"MODEL_MAPPING_NAME": mock_model_mapping, "MODEL_ORDER_INSTANTIATION": ["hydro"]},
        ):
            with patch("atlas.io.input_loader.InputLoader._load_timeseries", return_value="TS"):
                with patch("atlas.io.input_loader.InputLoader._load_matrix", return_value="MATRIX"):
                    with patch(
                        "atlas.io.input_loader.pendulum.from_format",
                        side_effect=Exception("Bad date format"),
                    ):
                        result = InputLoader._instantiate_math_objects_into_dict(
                            [{"name": "fr_hydro", "start_date": "not a date"}],
                            "hydro",
                            temp_input_dir,
                            date_format_input_files="DD/MM/YYYY HH:mm:ss",
                        )

                        # The original value should be kept when parsing fails
                        assert result[0]["start_date"] == "not a date"
