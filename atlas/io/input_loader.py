"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements Input Loader
"""

from datetime import datetime
from pathlib import Path
from types import UnionType
from typing import Any, Literal, get_args, get_origin

import pendulum
import polars as pl
from pydantic_extra_types.pendulum_dt import DateTime

import atlas.config as cfg
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_matrix import LazyMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.matrix import Matrix
from atlas.math.scenario_matrix import LazyScenarioMatrix, ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.business_model import BusinessModel


class InputLoader:
    """
    A class to handle input parsing and object instantiation from Atlas-formatted data directories.

    Provides utilities to load BusinessModel objects from a directory structure, including
    timeseries, forecasting matrices, and scenario matrices. Supports both eager and lazy loading modes.

    The input directory must follow a specific structure for successful parsing:

        <root_input_directory>/
        ├── objects/
        │   ├── hydro.csv
        │   ├── wind.csv
        │   └── ...
        ├── timeseries/
        │   └── hydro/
        │       ├── fr_hydro.parquet
        │       └── ...
        ├── scenario_matrix/
        │   └── hydro/
        │       ├── fr_hydro.parquet
        │       └── ...
        └── forecasting_matrix/
            └── hydro/
                ├── fr_hydro.parquet
                └── ...

    - The `objects/` directory contains CSV files, each named after an object type (e.g., `storage.csv`),
      describing the business objects and their attributes. Each line in the CSV represents an object.
    - The `timeseries/`, `scenario_matrix/`, and `forecasting_matrix/` directories contain subdirectories
      for each object type, with files named after the object (e.g., `fr_storage.parquet`).
    - Each matrix or timeseries file contains a column 'attribute' which is categorical and contains the timeseries or matrix name.
      In a way that if a filter is applied on this column, the dataframe retrieved is the timeseries, or the matrix of the filter applied.
    - Each timeseries or matrix file must match the expected file extension (default: `.parquet`).
    - Attribute names in the objects CSV must be either the value itself of the attribute, or the type if a math objects (e.g timeseries,
      forecasting_matrix, scenario_matrix)

    """

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
    ) -> dict[str, list[type[BusinessModel]]]:
        """
        Load input data from a directory and return instantiated BusinessModel objects.

        This method reads data files (CSV, Parquet) from a structured directory,
        constructs intermediate mathematical objects, and then instantiates the
        corresponding business model classes.

        :param directory_path: The root path to the directory containing input data.
        :type directory_path: str or pathlib.Path
        :param separator: The separator used in CSV files (default: ";").
        :type separator: str
        :param timeseries_file_extension: File extension for timeseries files (default: ".parquet").
        :type timeseries_file_extension: str
        :param matrix_file_extension: File extension for matrix files (default: ".parquet").
        :type matrix_file_extension: str
        :param lazy: Whether to use lazy loading for timeseries and matrices (default: False).
        :type lazy: bool
        :param timezone: Timezone for date parsing and object instantiation (default: "UTC").
        :type timezone: str
        :param date_format_forecasting_matrix: Date format used for forecasting matrix timestamps.
        :type date_format_forecasting_matrix: str
        :param date_format_input_files: Date format used in object CSV data.
        :type date_format_input_files: str
        :return: A dictionary mapping object type names to lists of instantiated BusinessModel objects.
        :rtype: dict[str, list[BusinessModel]]
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
            objects = cls._parse_objects_files(objects_dir, separator=separator)
        else:
            raise NotADirectoryError(
                f"Directory does not contain 'objects' subdirectory: {directory_path}",
            )

        objects_instantiated_with_math_objects = {}
        objects_instantiated: dict[str, list[type[BusinessModel]]] = {}

        invalid_elements = [x for x in objects if x not in cfg.MODEL_MAPPING_NAME]
        if invalid_elements:
            raise ValueError(
                f"Object type '{invalid_elements}' are not recognized. "
                f"Available types are: {list(cfg.MODEL_MAPPING_NAME.keys())}"
            )

        objects_type_sorted = sorted(objects, key=lambda x: cfg.MODEL_ORDER_INSTANTIATION.index(x))

        for object_type in objects_type_sorted:
            objects_instantiated_with_math_objects[object_type] = cls._build_math_objects(
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
            objects_instantiated[object_type] = cls._build_business_models(
                objects_instantiated_with_math_objects[object_type],
                object_type,
                objects_instantiated,
            )
            cfg.logger.success(f"Instantiated objects of type {cfg.MODEL_MAPPING_NAME[object_type].__name__}")
        cfg.logger.success("Atlas data loaded.")
        return objects_instantiated

    @classmethod
    def _build_math_objects(
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
        """
        Instantiate intermediate math objects (timeseries or matrices) from input attributes.
        """
        objects_instantiated = []

        for obj in object_list:
            object_instantiated: dict[str, Any] = {}
            for key, value in obj.items():
                attribute_type = get_type_attribute(object_type, key)
                if value == "timeseries" and attribute_type in (Timeseries, LazyTimeseries):
                    object_instantiated[key] = cls._load_timeseries(
                        base_path=base_path,
                        object_type=object_type,
                        name=obj["name"],
                        attribute_name=key,
                        file_extension=timeseries_file_extension,
                        lazy=lazy,
                        timezone=timezone,
                    )

                elif value in ["forecasting_matrix", "scenario_matrix"] and attribute_type in (
                    ForecastingMatrix,
                    LazyForecastingMatrix,
                    ScenarioMatrix,
                    LazyScenarioMatrix,
                ):
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
                elif attribute_type in (DateTime, datetime) and value is not None:
                    object_instantiated[key] = pendulum.from_format(value, date_format_input_files).to_datetime_string()
                elif get_origin(attribute_type) is list and value is not None:
                    inside_type = get_args(attribute_type)[0]
                    if inside_type in (str, float, int):
                        object_instantiated[key] = list(map(inside_type, value.split(":")))
                    else:
                        object_instantiated[key] = list(map(str, value.split(":")))
                else:  # noqa: PLR2004
                    object_instantiated[key] = value

            objects_instantiated.append(object_instantiated)

        return objects_instantiated

    @classmethod
    def _build_business_models(
        cls,
        object_list: list[dict[str, Any]],
        object_type: str,
        objects_instantiated: dict[str, list[type[BusinessModel]]],
    ) -> list[type[BusinessModel]]:
        """Instantiate final BusinessModel objects from intermediate math object dictionaries."""
        return [cls._build_single_business_model(obj, object_type, objects_instantiated) for obj in object_list]

    @staticmethod
    def _build_single_business_model(
        object_dict: dict[str, Any],
        object_type: str,
        objects_instantiated: dict[str, list[type[BusinessModel]]],
    ) -> type[BusinessModel]:
        """Instantiate a single BusinessModel object from its attributes. The function instantiates the objects nested in the object_dict."""
        cfg.logger.debug(
            f"""Instantiated > business model {object_dict["name"]} - type {cfg.MODEL_MAPPING_NAME[object_type].__name__}"""
        )
        for attribute in object_dict:
            attribute_type = get_type_attribute(object_type, attribute)
            if attribute_type in cfg.INVERSE_MODEL_MAPPING_NAME:
                if attribute == "equipment":
                    for attr in cfg.EQUIPMENT_MODELS:
                        equipment_lookup = {model.name: model for model in objects_instantiated[attr]}
                        name = object_dict["equipment"]
                        if name in equipment_lookup:
                            object_dict["equipment"] = equipment_lookup[name]
                            break
                else:
                    name = object_dict[attribute]
                    objects_lookup = {
                        model.name: model
                        for model in objects_instantiated[cfg.INVERSE_MODEL_MAPPING_NAME[attribute_type]]
                    }
                    object_dict[attribute] = objects_lookup[name]
            elif get_origin(attribute_type) is list:
                if get_args(attribute_type)[0] in cfg.INVERSE_MODEL_MAPPING_NAME:
                    object_list_string = object_dict[attribute]
                    object_list_instantiated = []
                    objects_lookup = {
                        model.name: model
                        for model in objects_instantiated[cfg.INVERSE_MODEL_MAPPING_NAME[get_args(attribute_type)[0]]]
                    }
                    for obj_string in object_list_string:
                        object_list_instantiated.append(objects_lookup[obj_string])
                    object_dict[attribute] = object_list_instantiated
        return cfg.MODEL_MAPPING_NAME[object_type](**object_dict)  # type: ignore[return-value]

    @classmethod
    def _parse_objects_files(cls, objects_path: Path, separator: str = ";") -> dict[str, list[dict[str, str]]]:
        """Parse object definitions from the 'objects' directory."""
        cfg.logger.debug(f"Parsing objects from directory: {objects_path}")
        result = {}
        for file_path in objects_path.iterdir():
            key = file_path.stem
            if key in cfg.MODEL_MAPPING_NAME:
                try:
                    result[key] = cls._read_data_file(file_path, separator=separator).to_dicts()
                except Exception:  # noqa: BLE001
                    cfg.logger.warning(
                        f"Failed to read {file_path}. Object type key {key} won't be taken into account."
                    )
            else:
                cfg.logger.warning(f"File {file_path} is not a recognized objects from Atlas.")
        return result

    @staticmethod
    def _read_data_file(file_path: str | Path, separator: str = ";") -> pl.DataFrame:
        """Read a file (CSV, Parquet, or JSON) and return a Polars DataFrame."""
        file_extension = Path(file_path).suffix

        if file_extension == ".csv":
            return pl.read_csv(file_path, separator=separator)
        if file_extension == ".parquet":
            return pl.read_parquet(file_path)
        if file_extension == ".json":
            return pl.read_json(file_path)

        raise NotImplementedError("File extension has to be csv, parquet or json")

    @staticmethod
    def _load_timeseries(
        base_path: Path,
        object_type: str,
        name: str,
        attribute_name: str,
        file_extension: str = ".parquet",
        lazy: bool = False,
        timezone: str = "UTC",
    ) -> Timeseries | LazyTimeseries:
        """Load a Timeseries or LazyTimeseries from a file."""
        timeseries_path = Path(base_path) / "timeseries" / object_type / (name + file_extension)
        if not (Path(base_path) / "timeseries").exists():
            raise NotADirectoryError(f"Directory does not contain 'timeseries' subdirectory: {base_path}")
        if not timeseries_path.exists():
            raise FileNotFoundError(f"Path does not exist: {timeseries_path}")

        cfg.logger.debug(f"Loading timeseries from file: {timeseries_path} with attribute {attribute_name}")

        if lazy:
            return LazyTimeseries.from_file(
                file_path=timeseries_path,
                timezone=timezone,
                filters=("attribute", attribute_name),
            )
        return Timeseries.from_file(file_path=timeseries_path, timezone=timezone, filters=("attribute", attribute_name))

    @staticmethod
    def _load_matrix(
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
        """Load a ForecastingMatrix or ScenarioMatrix (lazy or not) from a file."""
        if matrix_type not in ("scenario_matrix", "forecasting_matrix"):
            raise ValueError("Invalid matrix type, should be scenario_matrix or forecasting_matrix")

        matrix_file_path = Path(base_path) / matrix_type / object_type / (name + file_extension)
        if not (Path(base_path) / matrix_type).exists():
            raise NotADirectoryError(f"Directory does not contain '{matrix_type}' subdirectory: {base_path}")
        if not matrix_file_path.exists():
            raise FileNotFoundError(f"Path does not exist: {matrix_file_path}")

        cfg.logger.debug(f"Loading {matrix_type} from file: {matrix_file_path}")

        if not lazy:
            if matrix_type == "scenario_matrix":
                return ScenarioMatrix.from_file(
                    file_path=matrix_file_path,
                    timezone=timezone,
                    filters=("attribute", attribute_name),
                )
            if matrix_type == "forecasting_matrix":
                return ForecastingMatrix.from_file(
                    file_path=matrix_file_path,
                    timezone=timezone,
                    filters=("attribute", attribute_name),
                    date_format=date_format_forecasting,
                )
            raise ValueError(f"Invalid matrix_type: {matrix_type}. Must be 'scenario' or 'forecasting'.")
        if matrix_type == "scenario_matrix":
            return LazyScenarioMatrix.from_file(
                file_path=matrix_file_path,
                timezone=timezone,
                filters=("attribute", attribute_name),
            )
        if matrix_type == "forecasting_matrix":
            return LazyForecastingMatrix.from_file(
                file_path=matrix_file_path,
                timezone=timezone,
                filters=("attribute", attribute_name),
            )
        raise ValueError(f"Invalid matrix_type: {matrix_type}. Must be 'scenario' or 'forecasting'.")


def get_type_attribute(object_type: str, attribute: str) -> type[BusinessModel]:
    """Get type of attribute for a given object type."""
    if object_type not in cfg.MODEL_MAPPING_NAME:
        raise ValueError(f"Object type {object_type} is not valid.")

    if attribute not in cfg.MODEL_MAPPING_NAME[object_type].model_fields:
        raise KeyError(f"The attribute {attribute} is not present in Atlas model object : {object_type}")
    attribute_type = cfg.MODEL_MAPPING_NAME[object_type].model_fields[attribute].annotation

    if get_origin(attribute_type) is UnionType:
        model = get_args(attribute_type)[0]
        if model is None:
            model = get_args(attribute_type)[1]

    return model
