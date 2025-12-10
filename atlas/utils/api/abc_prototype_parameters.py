import json
from abc import ABC
from pathlib import Path

import yaml
from pydantic import BaseModel


class ABCPrototypeParameters(ABC, BaseModel):
    @classmethod
    def from_file(cls, file_path: str | Path) -> "Self":
        """
        Load parameters from a YAML or JSON file.
        :param file_path: Path to the parameters file.
        :type file_path: str or pathlib.Path
        :return: A Parameters object containing the parsed and validated parameters.
        :rtype: Parameters
        :raises ValueError: If the file extension is not supported.
        """
        file_extension = Path(file_path).suffix

        if file_extension in (".yaml", ".yml"):
            parameters = cls._parse_yaml(file_path)
        elif file_extension == ".json":
            parameters = cls._parse_json(file_path)
        else:
            raise ValueError(f"Unsupported file extension: {file_extension}")

        return cls.model_validate(parameters)

    @staticmethod
    def _parse_yaml(file_path: str | Path) -> dict:
        """Parse a YAML file and return its contents as a dictionary.
        :param file_path: Path to the YAML file.
        :type file_path: str or pathlib.Path
        :return: Parsed parameters.
        :rtype: dict
        """
        with open(Path(file_path)) as file:
            return yaml.safe_load(file)

    @staticmethod
    def _parse_json(file_path: str | Path) -> dict:
        """Parse a JSON file and return its contents as a dictionary.
        :param file_path: Path to the JSON file.
        :type file_path: str or pathlib.Path
        :return: Parsed parameters.
        :rtype: dict
        """
        with open(Path(file_path)) as file:
            return json.load(file)
