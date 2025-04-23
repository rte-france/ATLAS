# test_parameters_parser.py

import json

import pytest
import yaml

from atlas.io.parameters import Parameters, ParametersParser


@pytest.fixture
def sample_data():
    return {
        "param1": "value1",
        "param2": 42,
        "param3": [1, 2, 3],
    }


def test_parse_yaml(tmp_path, sample_data):
    yaml_path = tmp_path / "params.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(sample_data, f)

    params = ParametersParser.from_file(yaml_path)
    assert isinstance(params, Parameters)
    assert params.param1 == "value1"
    assert params.param2 == 42
    assert params.param3 == [1, 2, 3]


def test_parse_json(tmp_path, sample_data):
    json_path = tmp_path / "params.json"
    with open(json_path, "w") as f:
        json.dump(sample_data, f)

    params = ParametersParser.from_file(json_path)
    assert isinstance(params, Parameters)
    assert params.param1 == "value1"
    assert params.param2 == 42
    assert params.param3 == [1, 2, 3]


def test_unsupported_extension(tmp_path):
    txt_path = tmp_path / "params.txt"
    txt_path.write_text("invalid: true")

    with pytest.raises(ValueError, match="Unsupported file extension"):
        ParametersParser.from_file(txt_path)
