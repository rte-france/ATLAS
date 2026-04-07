import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from atlas.io_utils.parameters import DateParameters, Parameters


def test_from_yaml_file():
    """Test loading parameters from a YAML file"""
    yaml_content = {
        "export_result": True,
        "export_output_dataset": False,
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as temp_file:
        yaml.dump(yaml_content, temp_file)
        temp_file_path = temp_file.name

    try:
        params = Parameters.from_file(temp_file_path)
        # Parameters.from_file successfully loads and parses the YAML file
        assert params is not None
    finally:
        Path(temp_file_path).unlink()


def test_from_json_file():
    """Test loading parameters from a JSON file"""
    json_content = {
        "solver_name": "XPRESS",
        "export_lp": True,
        "use_presolve": True,
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as temp_file:
        json.dump(json_content, temp_file)
        temp_file_path = temp_file.name

    try:
        params = Parameters.from_file(temp_file_path)
        # Parameters.from_file successfully loads and parses the JSON file
        assert params is not None
    finally:
        Path(temp_file_path).unlink()


def test_from_yml_file():
    """Test loading parameters from a .yml file (alternative YAML extension)"""
    yaml_content = {
        "start_date": "2024-01-01T00:00:00",
        "end_date": "2024-12-31T23:59:59",
        "execution_date": "2024-06-01T12:00:00",
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as temp_file:
        yaml.dump(yaml_content, temp_file)
        temp_file_path = temp_file.name

    try:
        params = Parameters.from_file(temp_file_path)
        # Parameters.from_file successfully loads and parses the .yml file
        assert params is not None
    finally:
        Path(temp_file_path).unlink()


def test_unsupported_file_extension():
    """Test that unsupported file extensions raise ValueError"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as temp_file:
        temp_file.write("some content")
        temp_file_path = temp_file.name

    try:
        with pytest.raises(ValueError, match="Unsupported file extension"):
            Parameters.from_file(temp_file_path)
    finally:
        Path(temp_file_path).unlink()


def test_equal_start_end_dates():
    """Test that equal start and end dates are valid"""
    same_date = datetime(2024, 6, 1)
    params = DateParameters(
        start_date=same_date,
        end_date=same_date,
        execution_date=same_date,
    )
    assert params.start_date == params.end_date


def test_date_validation_boundary():
    """Test date validation at boundary conditions"""
    # Test with dates one second apart
    start = datetime(2024, 6, 1, 12, 0, 0)
    end = datetime(2024, 6, 1, 12, 0, 1)

    params = DateParameters(
        start_date=start,
        end_date=end,
        execution_date=start,
    )
    assert params.start_date < params.end_date


def test_pathlib_path_support():
    """Test that from_file method works with pathlib.Path objects"""
    yaml_content = {
        "start_date": "2024-01-01T00:00:00",
        "end_date": "2024-12-31T23:59:59",
        "execution_date": "2024-06-01T12:00:00",
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as temp_file:
        yaml.dump(yaml_content, temp_file)
        temp_file_path = Path(temp_file.name)

    try:
        params = Parameters.from_file(temp_file_path)
        # Parameters.from_file successfully accepts pathlib.Path objects
        assert params is not None
    finally:
        temp_file_path.unlink()


def test_valid_dates():
    params = DateParameters(
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        execution_date=datetime(2024, 6, 1),
    )
    assert params.start_date < params.end_date


def test_invalid_end_before_start():
    try:
        DateParameters(
            start_date=datetime(2024, 12, 31), end_date=datetime(2024, 1, 1), execution_date=datetime(2024, 12, 31)
        )
    except ValueError as e:
        assert "Start date" in str(e)


def test_invalid_timestep_raises():
    with pytest.raises(ValidationError):
        DateParameters(timestep="")
