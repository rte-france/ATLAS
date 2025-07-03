"""Tests for AbstractParameters class."""

import json
import tempfile
from pathlib import Path

import pendulum
import pytest
import yaml
from pydantic import ValidationError

from atlas.abstract_class.abstract_parameters import AbstractParameters  # Replace with actual import path


class TestAbstractParameters:
    """Test suite for AbstractParameters class."""

    def test_from_file_yaml_valid(self):
        """Test loading parameters from a valid YAML file."""
        yaml_content = {
            "start_date": "2024-01-01T00:00:00",
            "end_date": "2024-12-31T23:59:59",
            "execution_date": "2024-01-01T10:00:00",
            "export_result": False,
            "export_output_dataset": True,
            "solver_name": "yaml_solver",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_content, f)
            yaml_file_path = f.name

        try:
            params = AbstractParameters.from_file(yaml_file_path)

            assert params.start_date == pendulum.DateTime(2024, 1, 1, 0, 0, 0, tzinfo=pendulum.Timezone("UTC"))
            assert params.end_date == pendulum.DateTime(2024, 12, 31, 23, 59, 59, tzinfo=pendulum.Timezone("UTC"))
            assert params.execution_date == pendulum.DateTime(2024, 1, 1, 10, 0, 0, tzinfo=pendulum.Timezone("UTC"))
            assert params.export_result is False
            assert params.export_output_dataset is True
            assert params.solver_name == "yaml_solver"
        finally:
            Path(yaml_file_path).unlink()

    def test_from_file_json_valid(self):
        """Test loading parameters from a valid JSON file."""
        json_content = {
            "start_date": "2024-01-01T00:00:00",
            "end_date": "2024-12-31T23:59:59",
            "execution_date": "2024-01-01T10:00:00",
            "export_result": True,
            "export_output_dataset": False,
            "solver_name": "xpress",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(json_content, f)
            json_file_path = f.name

        try:
            params = AbstractParameters.from_file(json_file_path)

            assert params.start_date == pendulum.DateTime(2024, 1, 1, 0, 0, 0, tzinfo=pendulum.Timezone("UTC"))
            assert params.end_date == pendulum.DateTime(2024, 12, 31, 23, 59, 59, tzinfo=pendulum.Timezone("UTC"))
            assert params.execution_date == pendulum.DateTime(2024, 1, 1, 10, 0, 0, tzinfo=pendulum.Timezone("UTC"))
            assert params.export_result is True
            assert params.export_output_dataset is False
            assert params.solver_name == "xpress"
        finally:
            Path(json_file_path).unlink()

    def test_from_file_unsupported_extension(self):
        """Test loading parameters from a file with unsupported extension."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("some content")
            txt_file_path = f.name

        try:
            with pytest.raises(ValueError, match="Unsupported file extension: .txt"):
                AbstractParameters.from_file(txt_file_path)
        finally:
            Path(txt_file_path).unlink()

    def test_from_file_with_path_object(self):
        """Test loading parameters using Path object instead of string."""
        yaml_content = {
            "start_date": "2024-01-01T00:00:00",
            "end_date": "2024-12-31T23:59:59",
            "execution_date": "2024-01-01T10:00:00",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_content, f)
            yaml_file_path = Path(f.name)

        try:
            params = AbstractParameters.from_file(yaml_file_path)
            assert params.start_date == pendulum.DateTime(2024, 1, 1, 0, 0, 0, tzinfo=pendulum.Timezone("UTC"))
        finally:
            yaml_file_path.unlink()

    def test_from_file_invalid_yaml_content(self):
        """Test loading parameters from YAML file with invalid content."""
        yaml_content = {
            "start_date": "2024-01-01T00:00:00",
            "end_date": "2023-12-31T23:59:59",  # Invalid: before start_date
            "execution_date": "2024-01-01T10:00:00",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_content, f)
            yaml_file_path = f.name

        try:
            with pytest.raises(
                ValidationError,
                match="Start date '2024-01-01 00:00:00' must be inferior to end date '2023-12-31 23:59:59'",
            ):
                AbstractParameters.from_file(yaml_file_path)
        finally:
            Path(yaml_file_path).unlink()

    def test_from_file_missing_required_fields(self):
        """Test loading parameters from file with missing required fields."""
        yaml_content = {
            "start_date": "2024-01-01T00:00:00",
            # Missing end_date and execution_date
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_content, f)
            yaml_file_path = f.name

        try:
            with pytest.raises(ValidationError):
                AbstractParameters.from_file(yaml_file_path)
        finally:
            Path(yaml_file_path).unlink()

    def test_parse_yaml_static_method(self):
        """Test the static _parse_yaml method."""
        yaml_content = {
            "start_date": "2024-01-01T00:00:00",
            "end_date": "2024-12-31T23:59:59",
            "execution_date": "2024-01-01T10:00:00",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_content, f)
            yaml_file_path = f.name

        try:
            result = AbstractParameters._parse_yaml(yaml_file_path)
            assert result == yaml_content
        finally:
            Path(yaml_file_path).unlink()

    def test_parse_json_static_method(self):
        """Test the static _parse_json method."""
        json_content = {
            "start_date": "2024-01-01T00:00:00",
            "end_date": "2024-12-31T23:59:59",
            "execution_date": "2024-01-01T10:00:00",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(json_content, f)
            json_file_path = f.name

        try:
            result = AbstractParameters._parse_json(json_file_path)
            assert result == json_content
        finally:
            Path(json_file_path).unlink()

    def test_parse_yaml_with_path_object(self):
        """Test _parse_yaml with Path object."""
        yaml_content = {"test": "value"}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_content, f)
            yaml_file_path = Path(f.name)

        try:
            result = AbstractParameters._parse_yaml(yaml_file_path)
            assert result == yaml_content
        finally:
            yaml_file_path.unlink()

    def test_parse_json_with_path_object(self):
        """Test _parse_json with Path object."""
        json_content = {"test": "value"}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(json_content, f)
            json_file_path = Path(f.name)

        try:
            result = AbstractParameters._parse_json(json_file_path)
            assert result == json_content
        finally:
            json_file_path.unlink()

    def test_file_not_found_error(self):
        """Test behavior when file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            AbstractParameters.from_file("nonexistent_file.yaml")

    def test_invalid_yaml_syntax(self):
        """Test behavior with invalid YAML syntax."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [")
            yaml_file_path = f.name

        try:
            with pytest.raises(yaml.YAMLError):
                AbstractParameters.from_file(yaml_file_path)
        finally:
            Path(yaml_file_path).unlink()

    def test_invalid_json_syntax(self):
        """Test behavior with invalid JSON syntax."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"invalid": json content')
            json_file_path = f.name

        try:
            with pytest.raises(json.JSONDecodeError):
                AbstractParameters.from_file(json_file_path)
        finally:
            Path(json_file_path).unlink()
