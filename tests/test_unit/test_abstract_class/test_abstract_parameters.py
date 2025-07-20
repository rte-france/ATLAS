"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from atlas.abstract_class.abstract_parameters import AbstractParameters
from atlas.enum import SolverEnum


def test_valid_dates():
    params = AbstractParameters(
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        execution_date=datetime(2024, 6, 1),
    )
    assert params.start_date < params.end_date


def test_invalid_end_before_start():
    try:
        AbstractParameters(
            start_date=datetime(2024, 12, 31), end_date=datetime(2024, 1, 1), execution_date=datetime(2024, 12, 31)
        )
        assert False, "Expected ValueError for end_date before start_date"
    except ValueError as e:
        assert "Start date" in str(e)


def test_from_yaml_file():
    """Test loading parameters from a YAML file"""
    yaml_content = {
        "start_date": "2024-01-01T00:00:00",
        "end_date": "2024-12-31T23:59:59",
        "execution_date": "2024-06-01T12:00:00",
        "export_result": True,
        "export_output_dataset": False,
        "solver_name": "XPRESS",
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as temp_file:
        yaml.dump(yaml_content, temp_file)
        temp_file_path = temp_file.name

    try:
        params = AbstractParameters.from_file(temp_file_path)
        assert params.export_result is True
        assert params.export_output_dataset is False
        assert params.solver_name == SolverEnum.XPRESS
    finally:
        Path(temp_file_path).unlink()


def test_from_json_file():
    """Test loading parameters from a JSON file"""
    json_content = {
        "start_date": "2024-01-01T00:00:00",
        "end_date": "2024-12-31T23:59:59",
        "execution_date": "2024-06-01T12:00:00",
        "export_result": False,
        "export_output_dataset": True,
        "solver_name": "XPRESS",
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as temp_file:
        json.dump(json_content, temp_file)
        temp_file_path = temp_file.name

    try:
        params = AbstractParameters.from_file(temp_file_path)
        assert params.export_result is False
        assert params.export_output_dataset is True
        assert params.solver_name == SolverEnum.XPRESS
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
        params = AbstractParameters.from_file(temp_file_path)
        assert params.start_date is not None
        assert params.end_date is not None
        assert params.execution_date is not None
    finally:
        Path(temp_file_path).unlink()


def test_unsupported_file_extension():
    """Test that unsupported file extensions raise ValueError"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as temp_file:
        temp_file.write("some content")
        temp_file_path = temp_file.name

    try:
        with pytest.raises(ValueError, match="Unsupported file extension"):
            AbstractParameters.from_file(temp_file_path)
    finally:
        Path(temp_file_path).unlink()


def test_equal_start_end_dates():
    """Test that equal start and end dates are valid"""
    same_date = datetime(2024, 6, 1)
    params = AbstractParameters(
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

    params = AbstractParameters(
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
        params = AbstractParameters.from_file(temp_file_path)
        assert params.start_date is not None
        assert params.end_date is not None
        assert params.execution_date is not None
    finally:
        temp_file_path.unlink()
