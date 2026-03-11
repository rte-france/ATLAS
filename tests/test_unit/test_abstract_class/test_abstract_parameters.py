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
from atlas.enums import SolverEnum
from atlas.io_utils.section_parameters import DateParameters


def test_from_yaml_file():
    """Test loading parameters from a YAML file"""
    yaml_content = {
        "relative_src": "path_for_relative_path",
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as temp_file:
        yaml.dump(yaml_content, temp_file)
        temp_file_path = temp_file.name

    try:
        params = AbstractParameters.from_file(temp_file_path)
        assert params.relative_src == "path_for_relative_path"
    finally:
        Path(temp_file_path).unlink()


def test_from_json_file():
    """Test loading parameters from a JSON file"""
    json_content = {
        "relative_src": "path_for_relative_path",
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as temp_file:
        json.dump(json_content, temp_file)
        temp_file_path = temp_file.name

    try:
        params = AbstractParameters.from_file(temp_file_path)
        assert params.relative_src == "path_for_relative_path"
    finally:
        Path(temp_file_path).unlink()


def test_from_yml_file():
    """Test loading parameters from a .yml file (alternative YAML extension)"""
    yaml_content = {
        "relative_src": "path_for_relative_path",
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as temp_file:
        yaml.dump(yaml_content, temp_file)
        temp_file_path = temp_file.name

    try:
        params = AbstractParameters.from_file(temp_file_path)
        assert params.relative_src == "path_for_relative_path"
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


def test_pathlib_path_support():
    """Test that from_file method works with pathlib.Path objects"""
    yaml_content = {
        "relative_src": "path_for_relative_path",
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as temp_file:
        yaml.dump(yaml_content, temp_file)
        temp_file_path = Path(temp_file.name)

    try:
        params = AbstractParameters.from_file(temp_file_path)
        assert params.relative_src == "path_for_relative_path"
    finally:
        temp_file_path.unlink()
