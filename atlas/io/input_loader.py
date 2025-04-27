"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements Input Parser
"""

import json
from pathlib import Path
from typing import Any, Literal

import polars as pl

import atlas.config as cfg
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.scenario_matrix import ScenarioMatrix
from atlas.math.timeseries import Timeseries


class InputLoader:
    """A class to handle input parsing from Atlas format."""

    @classmethod
    def from_directory(
        cls,
        directory_path: str | Path,
        separator: str = ";",
        timeseries_file_extension: str = ".parquet",
    ) -> dict[str, Any]:
        """Load input from a directory.
        :param directory_path: The path to the directory.
        :type directory_path: str or pathlib.Path
        :param separator: The separator used in the CSV files.
        :type separator: str
        :param timeseries_file_extension: The file extension for the timeseries files.
        :type timeseries_file_extension: str
        :return: A dictionary mapping object names to lists of instantiated objects.
        :rtype: dict[str, list[BusinessModel]]
        """
        cfg.logger.debug(f"Loading input from directory: {directory_path}")

        if not Path(directory_path).exists():
            raise FileNotFoundError(
                f"Directory does not exist: {directory_path}",
            )
        if not Path(directory_path).is_dir():
            raise NotADirectoryError(
                f"Path is not a directory: {directory_path}",
            )
        objects_dir = Path(directory_path) / "objects"
        if objects_dir.is_dir():
            objects = cls._parse_objects_from_directory(objects_dir, separator=separator)
        else:
            raise NotADirectoryError(
                f"Directory does not contain 'objects' subdirectory: {directory_path}",
            )

        objects_instantiated_with_math_objects = {}
        objects_instantiated = {}

        for object_type in objects:
            if object_type not in cfg.MODEL_MAPPING_NAME:
                raise ValueError(
                    f"Object type '{object_type}' is not recognized. "
                    f"Available types are: {list(cfg.MODEL_MAPPING_NAME.keys())}"
                )
            objects_instantiated_with_math_objects[object_type] = cls._instantiate_math_objects_into_dict(
                objects[object_type],
                object_type,
                base_path=Path(directory_path),
                timeseries_file_extension=timeseries_file_extension,
            )
            objects_instantiated[object_type] = cls._instantiate_model_objects_into_dict(
                objects_instantiated_with_math_objects[object_type],
                object_type,
            )
        cfg.logger.debug(f"Instantiated objects of type {object_type}")

        return objects_instantiated

    @classmethod
    def from_file(cls, file_path: str | Path, object_type: str) -> dict[str, Any]:
        """Load input from a object file.
        :param file_path: The path to the file.
        :type file_path: str or pathlib.Path
        :param object_type: The type of the object to instantiate.
        :type object_type: str
        :return: A dictionary mapping object names to lists of instantiated objects.
        :rtype: dict[str, Any]]
        """
        if not Path(file_path).exists():
            raise FileNotFoundError(
                f"File does not exist: {file_path}",
            )
        if not Path(file_path).is_file():
            raise NotADirectoryError(
                f"Path is not a file: {file_path}",
            )

        objects = cls.read_data_file(file_path)
        objects_instantiated_with_math_objects = cls._instantiate_math_objects_into_dict(
            objects,
            object_type,
            base_path=Path(file_path).parent,
        )

        return cls._instantiate_model_objects_into_dict(
            objects_instantiated_with_math_objects,
            object_type,
        )

    @classmethod
    def _instantiate_math_objects_into_dict(
        cls,
        object_list: list[dict[str, Any]],
        object_type: str,
        base_path: Path,
        timeseries_file_extension: str = ".parquet",
    ) -> dict[str, Any]:
        """Instantiate objects from a dictionary of attributes.

        :param object_dict: A dictionary containing the attributes of the object.
        :type object_dict: dict
        :param object_type: The type of the object to instantiate.
        :type object_type: str
        :param base_path: The base path to the directory containing the timeseries and matrix files.
        :type base_path: str or pathlib.Path
        :param timeseries_file_extension: The file extension for the timeseries files.
        :type timeseries_file_extension: str
        :return: An instance of the specified object type.
        :rtype: BusinessModel
        """
        object_instantiated: dict[str, Any] = {}
        for obj in object_list:
            for key, value in obj.items():
                if value == "timeseries":
                    object_instantiated[key] = cls._load_timeseries(
                        base_path=base_path,
                        object_type=object_type,
                        instance_name=obj["instance_name"],
                        attribute_name=key,
                        file_extension=timeseries_file_extension,
                    )
                elif value in ["forecasting_matrix", "scenario_matrix"]:
                    object_instantiated[key] = cls._load_matrix(
                        base_path=base_path,
                        instance_name=obj["instance_name"],
                        attribute_name=key,
                        object_type=object_type,
                        matrix_type=value,
                    )

        return obj

    @classmethod
    def _instantiate_model_objects_into_dict(
        cls,
        object_list: list[dict[str, Any]],
        object_type: str,
    ) -> dict[str, Any]:
        """Instantiate objects from a dictionary of attributes.

        :param object_dict: A dictionary containing the attributes of the object.
        :type object_dict: dict
        :param object_type: The type of the object to instantiate.
        :type object_type: str
        :return: An instance of the specified object type.
        :rtype: dict[str, BusinessModel]
        """
        object_instantiated: dict[str, Any] = {}
        for obj in object_list:
            instance_name = obj["instance_name"]
            if instance_name in object_instantiated:
                raise ValueError(f"Duplicate instance name '{instance_name}' found in {object_type} objects.")
            object_instantiated[instance_name] = cls._instantiate_model_object(
                obj,
                object_type,
            )
        return object_instantiated

    @staticmethod
    def _instantiate_model_object(
        object_dict: dict[str, Any],
        object_type: str,
    ) -> dict[str, Any]:
        """Instantiate a business model from a dictionary of attributes.

        :param object_dict: A dictionary containing the attributes of the object.
        :type object_dict: dict
        :param object_type: The type of the object to instantiate.
        :type object_type: str
        :return: An instance of the specified object type.
        :rtype: BusinessModel
        """
        return cfg.MODEL_MAPPING_NAME[object_type](**object_dict)

    @classmethod
    def _parse_objects_from_directory(cls, objects_path: Path, separator: str = ";") -> dict[str, list[dict[str, str]]]:
        """Parse objects from a directory.

        :param directory_path: The path to the directory.
        :type directory_path: str or pathlib.Path
        :return: A dictionary mapping object names to lists of instantiated objects.
        :rtype: dict[str, list[BusinessModel]]
        """
        cfg.logger.debug(f"Parsing objects from directory: {objects_path}")
        return {
            file_path.stem: cls.read_data_file(file_path, separator=separator).to_dicts()
            for file_path in objects_path.iterdir()
        }

    @staticmethod
    def read_data_file(file_path: str | Path, separator: str = ";") -> pl.DataFrame:
        """Parse input from a CSV file or a parquet file.

        :param file_path: The path to the file.
        :type file_path: str or pathlib.Path
        :param separator: The separator used in the CSV file.
        :type separator: str
        :return: A DataFrame containing the parsed CSV data.
        :rtype: pl.DataFrame
        """
        file_extension = Path(file_path).suffix

        if file_extension == ".csv":
            return pl.read_csv(file_path, separator=separator)
        if file_extension == ".parquet":
            return pl.read_parquet(file_path)
        if file_extension == ".json":
            return pl.read_json(file_path)

        raise ValueError(f"Unsupported file extension: {file_extension}")

    @staticmethod
    def _load_timeseries(
        base_path: Path,
        object_type: str,
        instance_name: str,
        attribute_name: str,
        file_extension: str = ".parquet",
    ) -> Timeseries:
        """Load a timeseries profile from the timeseries/ folder.
        :param base_path: Path to the timeseries/ folder.
        :type base_path: str or Path
        :param instance_name: Name of the instance (e.g., wind_turbine1_normandie).
        :type instance_name: str
        :param attribute_name: Name of the attribute (e.g., wind_speed).
        :type attribute_name: str
        :param file_extension: File extension of the timeseries file (default: ".parquet").
        :type file_extension: str
        :return: A Timeseries object instantiated from the file.
        :rtype: Timeseries
        """
        timeseries_path = (
            Path(base_path) / "timeseries" / object_type / instance_name / (attribute_name + file_extension)
        )
        if not (Path(base_path) / "timeseries").exists():
            raise NotADirectoryError(f"Directory does not contain 'timeseries' subdirectory: {base_path}")
        if not timeseries_path.exists():
            raise FileNotFoundError(f"Path does not exist: {timeseries_path}")

        cfg.logger.debug(f"Loading timeseries from file: {timeseries_path}")

        return Timeseries.from_file(file_path=timeseries_path)

    @staticmethod
    def _load_matrix(  # noqa: PLR0913
        base_path: str | Path,
        instance_name: str,
        object_type: str,
        attribute_name: str,
        matrix_type: Literal["scenario_matrix", "forecasting_matrix"],
        file_extension: str = ".parquet",
    ) -> ScenarioMatrix | ForecastingMatrix:
        """Generic loader for scenario or forecasting matrix time series for a specific instance.

        :param base_dir: Path to the scenario_matrix/ or forecasting_matrix/ folder.
        :type base_dir: str or Path
        :param instance_name: Name of the instance (e.g., wind_turbine1_normandie).
        :type instance_name: str
        :param matrix_type: Type of matrix to load ("scenario" or "forecasting").
        :type matrix_type: str
        :param object_type: Type of object (e.g., "wind_turbine").
        :type object_type: str
        :param attribute_name: Name of the attribute (e.g., "wind_speed").
        :type attribute_name: str
        :param file_extension: File extension of the matrix file (default: ".parquet").
        :type file_extension: str
        :return: An instance of the corresponding matrix class with loaded data.
        :rtype: ScenarioMatrix or ForecastingMatrix
        """
        matrix_file_path = (
            Path(base_path)
            / matrix_type
            / object_type
            / instance_name
            / attribute_name
            / (attribute_name + file_extension)
        )
        if not (Path(base_path) / matrix_type).exists():
            raise NotADirectoryError(f"Directory does not contain '{matrix_type}' subdirectory: {base_path}")
        if not matrix_file_path.exists():
            raise FileNotFoundError(f"Path does not exist: {matrix_file_path}")

        cfg.logger.debug(f"Loading {matrix_type} from file: {matrix_file_path}")

        # if matrix_type == "scenario":
        #     return ScenarioMatrix(
        #         instance_name, list(matrix_dict.keys()), list(matrix_dict.values())
        #     )
        # if matrix_type == "forecasting":
        #     return ForecastingMatrix(
        #         instance_name, list(matrix_dict.keys()), list(matrix_dict.values())
        #     )
        # raise ValueError(
        #     f"Invalid matrix_type: {matrix_type}. Must be 'scenario' or 'forecasting'."
        # )

    @staticmethod
    def load_metadata(
        base_path: str | Path,
        instance_name: str,
        object_type: str,
        attribute_name: str,
        matrix_type: Literal["scenario_matrix", "forecasting_matrix"],
    ) -> dict:
        """Load metadata.json file if it exists in the given folder."""
        metadata_path = Path(base_path) / matrix_type / object_type / instance_name / attribute_name / "metadata.json"

        cfg.logger.debug(f"Loading metadata from file: {metadata_path}")

        if not metadata_path.exists():
            return {}
        with open(metadata_path) as f:
            return json.load(f)
