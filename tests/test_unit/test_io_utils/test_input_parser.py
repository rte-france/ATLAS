from datetime import datetime
from unittest.mock import MagicMock, patch

import pendulum
import polars as pl
import pytest
from pydantic import BaseModel, ConfigDict
from pydantic_extra_types.pendulum_dt import DateTime

import atlas.config as cfg
from atlas.io_utils.input_loader import load_from_directory
from atlas.io_utils.models import InputLoaderConfig
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.scenario_matrix import LazyScenarioMatrix, ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.business_model import BusinessModel
from atlas.models.equipment.equipment import Equipment


@pytest.fixture
def mock_model_mapping():
    class DummyModel(BaseModel):
        model_config = ConfigDict(arbitrary_types_allowed=True)

        name: str | None = None
        energy: Timeseries | None = None
        scenario: ScenarioMatrix | None = None
        forecast: ForecastingMatrix | None = None
        start_date: DateTime | None = None

    return {
        "hydro": DummyModel,
        "thermal": DummyModel,
        "solar": DummyModel,
        "equipment": DummyModel,
    }


@pytest.fixture
def mock_model_order():
    return ["hydro", "thermal", "solar"]


class DummyReferenced(BusinessModel):
    name: str


class DummyEquipment(Equipment):
    name: str
    type: str = "dummy"

    def __eq__(self, other):
        return isinstance(other, DummyEquipment) and self.name == other.name


class DummyReferencing(BusinessModel):
    name: str
    ref: DummyReferenced | None = None
    equipment: DummyEquipment | None = None
    refs: list[DummyReferenced] | None = None
    list_field: list[str] | None = None
    start_date: DateTime | None = None


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


@patch.dict(cfg.__dict__, {"MODEL_MAPPING_NAME": {"hydro": MagicMock()}})
@patch("atlas.io_utils.input_loader.load_from_directory._load_timeseries", return_value=Timeseries())
@patch("atlas.io_utils.input_loader.load_from_directory._load_matrix")
def test_from_directory_success(mock_matrix, mock_ts, temp_input_dir, mock_model_mapping):
    mock_matrix.side_effect = [ScenarioMatrix(), ForecastingMatrix()]

    with patch.dict(
        cfg.__dict__,
        {"MODEL_MAPPING_NAME": mock_model_mapping, "MODEL_ORDER_INSTANTIATION": ["hydro"]},
    ):
        result = load_from_directory(temp_input_dir)
        assert "hydro" in result
        assert isinstance(result["hydro"][0], mock_model_mapping["hydro"])
        assert result["hydro"][0].energy == Timeseries()
        assert result["hydro"][0].scenario == ScenarioMatrix()
        assert result["hydro"][0].forecast == ForecastingMatrix()
        # Test that date was properly parsed
        assert result["hydro"][0].start_date.to_datetime_string() == "2023-01-01 00:00:00"


def test_instantiate_model_object_with_equipment_reference(monkeypatch):
    # Patch MODEL_MAPPING_NAME and EQUIPMENT_MODELS temporarily
    monkeypatch.setitem(cfg.MODEL_MAPPING_NAME, "my_object", DummyReferencing)
    monkeypatch.setitem(cfg.MODEL_MAPPING_NAME, "equipment", DummyEquipment)
    monkeypatch.setitem(cfg.INVERSE_MODEL_MAPPING_NAME, DummyEquipment, "equipment")
    monkeypatch.setattr(cfg, "EQUIPMENT_MODELS", ["equipment"])

    # Simulate already-instantiated equipment
    equipment1 = DummyEquipment(name="eq1")
    objects_instantiated = {
        "equipment": [equipment1],
    }

    # Object to instantiate, referencing the equipment
    object_dict = {"name": "obj1", "equipment": "eq1"}

    # Build indices like the actual method does
    object_indices = load_from_directory._build_object_indices(objects_instantiated)

    result = load_from_directory._build_single_business_model(
        object_dict.copy(), "my_object", objects_instantiated, object_indices
    )

    assert isinstance(result, DummyReferencing)
    assert result.name == "obj1"
    assert result.equipment == equipment1


def test_instantiate_model_object_with_cross_reference(monkeypatch):
    # Simulate mapping configuration
    monkeypatch.setitem(cfg.MODEL_MAPPING_NAME, "dummy_referencing", DummyReferencing)
    monkeypatch.setitem(cfg.MODEL_MAPPING_NAME, "ref", DummyReferenced)
    monkeypatch.setattr(cfg, "EQUIPMENT_MODELS", [])
    monkeypatch.setitem(cfg.INVERSE_MODEL_MAPPING_NAME, DummyReferenced, "ref")

    # Already instantiated object
    referenced_obj = DummyReferenced(name="ref1")
    referenced_obj_2 = DummyReferenced(name="ref2")
    objects_instantiated = {
        "ref": [referenced_obj, referenced_obj_2],
    }

    # Object to instantiate, referencing the above
    object_dict = {
        "name": "obj1",
        "ref": "ref1",
        "refs": ["ref1", "ref2"],
        "list_field": ["a", "b"],
    }

    # Build indices like the actual method does
    object_indices = load_from_directory._build_object_indices(objects_instantiated)

    result = load_from_directory._build_single_business_model(
        object_dict.copy(), "dummy_referencing", objects_instantiated, object_indices
    )

    assert isinstance(result, DummyReferencing)
    assert result.name == "obj1"
    assert result.ref == referenced_obj
    assert result.refs == [referenced_obj, referenced_obj_2]
    assert result.list_field == ["a", "b"]


def test_load_matrix(tmp_path):
    # Create required directory structure
    (tmp_path / "objects").mkdir()
    matrix_path = tmp_path / "scenario_matrix" / "hydro"
    matrix_path.mkdir(parents=True)
    pl.DataFrame(
        {
            "date": [datetime(2024, 1, 1, 0, 0, 0)],
            "scenario1": [1.0],
            "scenario2": [3.0],
            "attribute": ["attribute"],
        }
    ).write_parquet(matrix_path / "fr_hydro.parquet")

    config = InputLoaderConfig(directory_path=tmp_path)
    result = load_from_directory._load_matrix(
        object_type="hydro",
        name="fr_hydro",
        attribute_name="attribute",
        matrix_type="scenario_matrix",
        config=config,
    )
    assert isinstance(result, ScenarioMatrix)


def test_load_forecasting_matrix(tmp_path):
    # Create required directory structure
    (tmp_path / "objects").mkdir()
    matrix_path = tmp_path / "forecasting_matrix" / "hydro"
    matrix_path.mkdir(parents=True)
    pl.DataFrame(
        {
            "date": [datetime(2024, 1, 1, 0, 0, 0)],
            "2024-01-01 00:00:00": [1.0],
            "2024-01-01 00:01:00": [3.0],
            "attribute": ["attribute"],
        }
    ).write_parquet(matrix_path / "fr_hydro.parquet")

    config = InputLoaderConfig(directory_path=tmp_path)
    result = load_from_directory._load_matrix(
        object_type="hydro",
        name="fr_hydro",
        attribute_name="attribute",
        matrix_type="forecasting_matrix",
        config=config,
    )
    assert isinstance(result, ForecastingMatrix)


def test_load_lazy_matrix(tmp_path):
    # Create required directory structure
    (tmp_path / "objects").mkdir()
    matrix_path = tmp_path / "scenario_matrix" / "hydro"
    matrix_path.mkdir(parents=True)
    pl.DataFrame(
        {
            "date": [datetime(2024, 1, 1, 0, 0, 0)],
            "scenario1": [1.0],
            "scenario2": [3.0],
            "attribute": ["attribute"],
        }
    ).write_parquet(matrix_path / "fr_hydro.parquet")

    config = InputLoaderConfig(directory_path=tmp_path, lazy=True)
    result = load_from_directory._load_matrix(
        object_type="hydro",
        name="fr_hydro",
        attribute_name="attribute",
        matrix_type="scenario_matrix",
        config=config,
    )
    assert isinstance(result, LazyScenarioMatrix)


def test_load_lazy_forecasting_matrix(tmp_path):
    # Create required directory structure
    (tmp_path / "objects").mkdir()
    matrix_path = tmp_path / "forecasting_matrix" / "hydro"
    matrix_path.mkdir(parents=True)
    pl.DataFrame(
        {
            "date": [datetime(2024, 1, 1, 0, 0, 0)],
            "01_01_2024 00:00:00": [1.0],
            "01_01_2024 00:01:00": [3.0],
            "attribute": ["attribute"],
        }
    ).write_parquet(matrix_path / "fr_hydro.parquet")

    config = InputLoaderConfig(directory_path=tmp_path, lazy=True)
    result = load_from_directory._load_matrix(
        object_type="hydro",
        name="fr_hydro",
        attribute_name="attribute",
        matrix_type="forecasting_matrix",
        config=config,
    )
    assert isinstance(result, LazyForecastingMatrix)


def test_load_timeseries(tmp_path):
    # Create required directory structure
    (tmp_path / "objects").mkdir()
    ts_path = tmp_path / "timeseries" / "hydro"
    ts_path.mkdir(parents=True)
    pl.DataFrame(
        {
            "date": [datetime(2024, 1, 1, 0, 0, 0), datetime(2024, 1, 1, 1, 0, 0)],
            "value": [1.0, 2.0],
            "attribute": ["attribute", "attribute"],
        }
    ).write_parquet(ts_path / "fr_hydro.parquet")

    config = InputLoaderConfig(directory_path=tmp_path)
    result = load_from_directory._load_timeseries(
        object_type="hydro", name="fr_hydro", attribute_name="attribute", config=config
    )
    assert isinstance(result, Timeseries)
    assert result.frequency == pendulum.duration(hours=1)


def test_load_lazy_timeseries(tmp_path):
    # Create required directory structure
    (tmp_path / "objects").mkdir()
    ts_path = tmp_path / "timeseries" / "hydro"
    ts_path.mkdir(parents=True)
    pl.DataFrame({"date": [datetime(2024, 1, 1, 0, 0, 0)], "value": [1.0], "attribute": ["attribute"]}).write_parquet(
        ts_path / "fr_hydro.parquet"
    )

    config = InputLoaderConfig(directory_path=tmp_path, lazy=True)
    result = load_from_directory._load_timeseries(
        object_type="hydro", name="fr_hydro", attribute_name="attribute", config=config
    )
    assert isinstance(result, LazyTimeseries)


def test_parse_objects_multiple_models(tmp_path):
    (tmp_path / "objects").mkdir()
    df1 = pl.DataFrame([{"name": "fr_hydro", "energy": "ts", "scenario": "sc"}])
    df2 = pl.DataFrame([{"name": "de_solar", "energy": "ts2", "scenario": "sc2"}])

    df1.write_csv(tmp_path / "objects" / "hydro.csv", separator=";")
    df2.write_csv(tmp_path / "objects" / "solar.csv", separator=";")

    result = load_from_directory._parse_objects_files(tmp_path / "objects")
    assert "hydro" in result
    assert "solar" in result
