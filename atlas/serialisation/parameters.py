import json
from pathlib import Path

import yaml
from pydantic import BaseModel


class Parameters(BaseModel):
    """A class to represent parameters."""


class ParametersParser:
    """A class to parse parameters from a file."""

    @classmethod
    def from_file(cls, file_path: str | Path) -> Parameters:
        """Load parameters from a file."""
        file_extension = Path(file_path).suffix

        if file_extension in (".yaml", ".yml"):
            parameters = cls._parse_yaml(file_path)
        elif file_extension == ".json":
            parameters = cls._parse_json(file_path)

        return Parameters(**parameters)

    @staticmethod
    def _parse_yaml(file_path: str | Path) -> dict:
        """Parse a YAML file and return the parameters."""
        with open(file_path) as file:
            return yaml.safe_load(file)

    @staticmethod
    def _parse_json(file_path: str | Path) -> dict:
        """Parse a JSON file and return the parameters."""
        with open(file_path) as file:
            return json.load(file)
