"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements Input Loader
"""

import json
from pathlib import Path
from typing import Any, Literal

import pendulum
import polars as pl

import atlas.config as cfg
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_matrix import LazyMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.matrix import Matrix
from atlas.math.scenario_matrix import LazyScenarioMatrix, ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.business_model import BusinessModel


class InputLoader:
    """A class to handle input parsing from Atlas format."""

    @classmethod
    def from_directory(
        cls,
        directory_path: str | Path,
        separator: str = ";",
        timeseries_file_extension: str = ".parquet",
        matrix_file_extension: str = ".parquet",
        lazy: bool = False,
        timezone: str = "UTC",
        date_format_forecasting_matrix: str = "DD_MM_YYYY HH:mm:ss",
        date_format_input_files: str = "DD/MM/YYYY HH:mm:ss",
    ) -> dict[str, list[Any]]:
        """Load input from a directory.
        :param directory_path: The path to the directory.
        :type directory_path: str or pathlib.Path
        :param separator: The separator used in the CSV files.
        :type separator: str
        :param timeseries_file_extension: The file extension for the timeseries files.
        :type timeseries_file_extension: str
        :return: A dictionary mapping object names to lists of instantiated objects.
        :rtype: dict[str, dict[str, list[BusinessModel]]]
        """
        cfg.logger.debug(f"Loading input from directory: {directory_path}")
        cfg.logger.debug(f"""Parameters -> directory_path: {directory_path}, lazy mode: {lazy}""")

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
                matrix_file_extension=matrix_file_extension,
                lazy=lazy,
                timezone=timezone,
                date_format_forecasting_matrix=date_format_forecasting_matrix,
                date_format_input_files=date_format_input_files,
            )
            objects_instantiated[object_type] = cls._instantiate_model_objects_into_dict(
                objects_instantiated_with_math_objects[object_type],
                object_type,
            )
        cfg.logger.debug(f"Instantiated objects of type {object_type}")

        return objects_instantiated

    @classmethod
    def _instantiate_math_objects_into_dict(  # noqa: PLR0913
        cls,
        object_list: list[dict[str, Any]],
        object_type: str,
        base_path: Path,
        timeseries_file_extension: str = ".parquet",
        matrix_file_extension: str = ".parquet",
        lazy: bool = False,
        timezone: str = "UTC",
        date_format_forecasting_matrix: str = "DD_MM_YYYY HH:mm:ss",
        date_format_input_files: str = "DD/MM/YYYY HH:mm:ss",
    ) -> list[dict[str, Any]]:
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
        :rtype: list[dict[str, BusinessModel]]
        """
        objects_instantiated = []

        for obj in object_list:
            object_instantiated: dict[str, Any] = {}
            for key, value in obj.items():
                if value == "timeseries":
                    object_instantiated[key] = cls._load_timeseries(
                        base_path=base_path,
                        object_type=object_type,
                        name=obj["name"],
                        attribute_name=key,
                        file_extension=timeseries_file_extension,
                        lazy=lazy,
                        timezone=timezone,
                    )
                elif value in ["forecasting_matrix", "scenario_matrix"]:
                    object_instantiated[key] = cls._load_matrix(
                        base_path=base_path,
                        name=obj["name"],
                        attribute_name=key,
                        object_type=object_type,
                        matrix_type=value,
                        file_extension=matrix_file_extension,
                        lazy=lazy,
                        timezone=timezone,
                        date_format_forecasting=date_format_forecasting_matrix,
                    )
                else:
                    try:
                        object_instantiated[key] = pendulum.from_format(
                            value, date_format_input_files
                        ).to_datetime_string()
                    except Exception:  # noqa: BLE001
                        object_instantiated[key] = value
            objects_instantiated.append(object_instantiated)

        return objects_instantiated

    @classmethod
    def _instantiate_model_objects_into_dict(
        cls,
        object_list: list[dict[str, Any]],
        object_type: str,
    ) -> list[Any]:
        """Instantiate objects from a dictionary of attributes.

        :param object_dict: A dictionary containing the attributes of the object.
        :type object_dict: dict
        :param object_type: The type of the object to instantiate.
        :type object_type: str
        :return: An instance of the specified object type.
        :rtype: list[BusinessModel]
        """
        objects_instantiated: dict[str, Any] = []
        for obj in object_list:
            objects_instantiated.append(
                cls._instantiate_model_object(
                    obj,
                    object_type,
                )
            )

        return objects_instantiated

    @staticmethod
    def _instantiate_model_object(
        object_dict: dict[str, Any],
        object_type: str,
    ) -> BusinessModel:
        """Instantiate a business model from a dictionary of attributes.

        :param object_dict: A dictionary containing the attributes of the object.
        :type object_dict: dict
        :param object_type: The type of the object to instantiate.
        :type object_type: str
        :return: An instance of the specified object type.
        :rtype: BusinessModel
        """
        cfg.logger.debug(f"Instantiated -- business model <{object_dict['name']}> -- type <{object_type}>")
        return cfg.MODEL_MAPPING_NAME[object_type](**object_dict)

    @classmethod
    def _parse_objects_from_directory(cls, objects_path: Path, separator: str = ";") -> dict[str, list[dict[str, str]]]:
        """Parse objects from a directory.

        :param objects_path: The path to the directory.
        :type objects_path: str or pathlib.Path
        :return: A dictionary mapping object names to lists of instantiated objects.
        :rtype: dict[str, list[dict[str, str]]]
        """
        cfg.logger.debug(f"Parsing objects from directory: {objects_path}")
        result = {}
        for file_path in objects_path.iterdir():
            key = file_path.stem
            if key in cfg.MODEL_MAPPING_NAME:
                try:
                    result[key] = cls.read_data_file(file_path, separator=separator).to_dicts()
                except Exception:  # noqa: BLE001
                    cfg.logger.warning(
                        f"Failed to read {file_path}. Object type key {key} won't be taken into account."
                    )
            else:
                cfg.logger.warning(f"File {file_path} is not a recognized objects from Atlas.")
        return result

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

        raise NotImplementedError("File extension has to be csv, parquetFs or json")

    @staticmethod
    def _load_timeseries(  # noqa: PLR0913
        base_path: Path,
        object_type: str,
        name: str,
        attribute_name: str,
        file_extension: str = ".parquet",
        lazy: bool = False,
    ) -> Timeseries | LazyTimeseries:
        """Load a timeseries profile from the timeseries/ folder.
        :param base_path: Path to the timeseries/ folder.
        :type base_path: str or Path
        :param name: Name of the instance (e.g., wind_turbine1_normandie).
        :type name: str
        :param attribute_name: Name of the attribute (e.g., wind_speed).
        :type attribute_name: str
        :param file_extension: File extension of the timeseries file (default: ".parquet").
        :type file_extension: str
        :return: A Timeseries object instantiated from the file.
        :rtype: Timeseries
        """
        timeseries_path = Path(base_path) / "timeseries" / object_type / name / (attribute_name + file_extension)
        if not (Path(base_path) / "timeseries").exists():
            raise NotADirectoryError(f"Directory does not contain 'timeseries' subdirectory: {base_path}")
        if not timeseries_path.exists():
            raise FileNotFoundError(f"Path does not exist: {timeseries_path}")

        cfg.logger.debug(f"Loading timeseries from file: {timeseries_path}")

        if lazy:
            return LazyTimeseries.from_file(file_path=timeseries_path)
        return Timeseries.from_file(file_path=timeseries_path)

    @staticmethod
    def _load_matrix(  # noqa: PLR0913
        base_path: str | Path,
        name: str,
        object_type: str,
        attribute_name: str,
        matrix_type: Literal["scenario_matrix", "forecasting_matrix"],
        file_extension: str = ".parquet",
        lazy: bool = False,
        timezone: str = "UTC",
        date_format_forecasting: str = "DD_MM_YYYY HH:mm:ss",
    ) -> Matrix | LazyMatrix:
        """Generic loader for scenario or forecasting matrix time series for a specific instance.

        :param base_dir: Path to the scenario_matrix/ or forecasting_matrix/ folder.
        :type base_dir: str or Path
        :param name: Name of the instance (e.g., wind_turbine1_normandie).
        :type name: str
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
            Path(base_path) / matrix_type / object_type / name / attribute_name / (attribute_name + file_extension)
        )
        if not (Path(base_path) / matrix_type).exists():
            raise NotADirectoryError(f"Directory does not contain '{matrix_type}' subdirectory: {base_path}")
        if not matrix_file_path.exists():
            raise FileNotFoundError(f"Path does not exist: {matrix_file_path}")

        cfg.logger.debug(f"Loading {matrix_type} from file: {matrix_file_path}")

        if not lazy:
            if matrix_type == "scenario_matrix":
                return ScenarioMatrix.from_file(matrix_file_path, timezone)
            if matrix_type == "forecasting_matrix":
                return ForecastingMatrix.from_file(matrix_file_path, timezone, date_format_forecasting)
            raise ValueError(f"Invalid matrix_type: {matrix_type}. Must be 'scenario' or 'forecasting'.")
        if matrix_type == "scenario_matrix":
            return LazyScenarioMatrix.from_file(matrix_file_path)
        if matrix_type == "forecasting_matrix":
            return LazyForecastingMatrix.from_file(matrix_file_path)
        raise ValueError(f"Invalid matrix_type: {matrix_type}. Must be 'scenario' or 'forecasting'.")

    @staticmethod
    def load_metadata(
        base_path: str | Path,
        name: str,
        object_type: str,
        attribute_name: str,
        matrix_type: Literal["scenario_matrix", "forecasting_matrix"],
    ) -> dict:
        """Load metadata.json file if it exists in the given folder."""
        metadata_path = Path(base_path) / matrix_type / object_type / name / attribute_name / "metadata.json"

        cfg.logger.debug(f"Loading metadata from file: {metadata_path}")

        if not metadata_path.exists():
            return {}
        with open(metadata_path) as f:
            return json.load(f)
