"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements Input Loader
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast, get_args, get_origin

import pendulum
from pydantic_extra_types.pendulum_dt import DateTime

import atlas.config as cfg
from atlas.io_utils.utils import read_data_file
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_matrix import LazyMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.matrix import Matrix
from atlas.math.scenario_matrix import LazyScenarioMatrix, ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.business_model import BusinessModel
from atlas.typing import get_type_attribute


class InputLoaderError(Exception):
    """Base exception for InputLoader errors."""

    pass


class DirectoryStructureError(InputLoaderError):
    """Raised when the input directory structure is invalid."""

    pass


class FileParsingError(InputLoaderError):
    """Raised when a file cannot be parsed correctly."""

    pass


class ObjectInstantiationError(InputLoaderError):
    """Raised when an object cannot be instantiated."""

    pass


class DataValidationError(InputLoaderError):
    """Raised when data validation fails."""

    pass


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
        date_format_forecasting_matrix: str = "YYYY-MM-DD HH:mm:ss",
        date_format_input_files: str = "YYYY-MM-DD HH:mm:ss",
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
        :rtype: dict[str, list[type[BusinessModel]]]

        :raises DirectoryStructureError: If the directory structure is invalid
        :raises FileParsingError: If files cannot be parsed
        :raises ObjectInstantiationError: If objects cannot be instantiated
        :raises DataValidationError: If data validation fails
        """
        try:
            cfg.logger.debug(f"Loading input from directory: {directory_path}")
            cfg.logger.debug(f"Parameters -> directory_path: {directory_path}, lazy mode: {lazy}")

            cls._validate_input_parameters(
                directory_path,
                separator,
                timeseries_file_extension,
                matrix_file_extension,
                timezone,
                date_format_forecasting_matrix,
                date_format_input_files,
            )

            # Validate and parse directory structure
            directory_path = Path(directory_path)
            cls._validate_directory_structure(directory_path)

            objects_dir = directory_path / "objects"
            objects = cls._parse_objects_files(objects_dir, separator=separator)

            if not objects:
                raise DataValidationError(
                    f"No valid object files found in {objects_dir}. "
                    f"Expected files named after object types with supported extensions."
                )

            objects_instantiated_with_math_objects = {}
            objects_instantiated: dict[str, list[type[BusinessModel]]] = {}

            cls._validate_object_types(objects)

            # Sort objects by instantiation order
            objects_type_sorted = sorted(objects, key=lambda x: cfg.MODEL_ORDER_INSTANTIATION.index(x))

            # Process each object type
            for object_type in objects_type_sorted:
                try:
                    objects_instantiated_with_math_objects[object_type] = cls._build_math_objects(
                        objects[object_type],
                        object_type,
                        base_path=directory_path,
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

                    cfg.logger.success(
                        f"Successfully instantiated {len(objects_instantiated[object_type])} "
                        f"objects of type {cfg.MODEL_MAPPING_NAME[object_type].__name__}"
                    )

                except Exception as e:
                    raise ObjectInstantiationError(
                        f"Failed to instantiate objects of type '{object_type}': {str(e)}"
                    ) from e

            cfg.logger.success("Atlas data loaded successfully.")
            return objects_instantiated

        except (DirectoryStructureError, FileParsingError, ObjectInstantiationError, DataValidationError):
            raise
        except Exception as e:
            raise InputLoaderError(f"Unexpected error during data loading: {str(e)}") from e

    @classmethod
    def _validate_input_parameters(
        cls,
        directory_path: str | Path,
        separator: str,
        timeseries_file_extension: str,
        matrix_file_extension: str,
        timezone: str,
        date_format_forecasting_matrix: str,
        date_format_input_files: str,
    ) -> None:
        """Validate input parameters."""
        if not directory_path:
            raise ValueError("directory_path cannot be empty")

        if not separator:
            raise ValueError("separator cannot be empty")

        for ext_name, ext_value in [
            ("timeseries_file_extension", timeseries_file_extension),
            ("matrix_file_extension", matrix_file_extension),
        ]:
            if not ext_value or not ext_value.startswith("."):
                raise ValueError(f"{ext_name} must start with '.' (e.g., '.parquet')")

        # Validate timezone
        try:
            pendulum.timezone(timezone)
        except Exception as e:
            raise ValueError(f"Invalid timezone '{timezone}': {str(e)}") from e

        # Validate date formats
        for format_name, format_value in [
            ("date_format_forecasting_matrix", date_format_forecasting_matrix),
            ("date_format_input_files", date_format_input_files),
        ]:
            try:
                # Test the format with a sample date
                pendulum.now().format(format_value)
            except Exception as e:
                raise ValueError(f"Invalid {format_name} '{format_value}': {str(e)}") from e

    @classmethod
    def _validate_directory_structure(cls, directory_path: Path) -> None:
        """Validate the directory structure."""
        if not directory_path.exists():
            raise DirectoryStructureError(f"Directory does not exist: {directory_path}")

        if not directory_path.is_dir():
            raise DirectoryStructureError(f"Path is not a directory: {directory_path}")

        objects_dir = directory_path / "objects"
        if not objects_dir.exists():
            raise DirectoryStructureError(
                f"Required 'objects' subdirectory not found in: {directory_path}. "
                f"Expected structure: {directory_path}/objects/"
            )

        if not objects_dir.is_dir():
            raise DirectoryStructureError(f"'objects' path is not a directory: {objects_dir}")

    @classmethod
    def _validate_object_types(cls, objects: dict[str, list[dict[str, Any]]]) -> None:
        """Validate that all object types are recognized."""
        invalid_elements = [x for x in objects if x not in cfg.MODEL_MAPPING_NAME]
        if invalid_elements:
            available_types = list(cfg.MODEL_MAPPING_NAME.keys())
            raise DataValidationError(
                f"Object type(s) {invalid_elements} are not recognized. "
                f"Available types are: {available_types}. "
                f"Please ensure your CSV files in the 'objects' directory are named correctly."
            )

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
        date_format_forecasting_matrix: str = "YYYY-MM-DD HH:mm:ss",
        date_format_input_files: str = "YYYY-MM-DD HH:mm:ss",
    ) -> list[dict[str, Any]]:
        """
        Instantiate intermediate math objects (timeseries or matrices) from input attributes.
        """
        objects_instantiated = []

        for i, obj in enumerate(object_list):
            try:
                object_name = cast(str, obj["name"])
                cfg.logger.debug(f"Processing math objects for '{object_name}' (type: {object_type})")

                object_instantiated: dict[str, Any] = {}

                for key, value in obj.items():
                    try:
                        attribute_type = get_type_attribute(object_type, key)

                        if value == "timeseries" and attribute_type in (Timeseries, LazyTimeseries):
                            object_instantiated[key] = cls._load_timeseries(
                                base_path=base_path,
                                object_type=object_type,
                                name=object_name,
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
                                name=object_name,
                                attribute_name=key,
                                object_type=object_type,
                                matrix_type=value,
                                file_extension=matrix_file_extension,
                                lazy=lazy,
                                timezone=timezone,
                                date_format_forecasting=date_format_forecasting_matrix,
                            )
                        elif attribute_type in (DateTime, datetime) and value is not None:
                            object_instantiated[key] = cls._parse_datetime(value, date_format_input_files)
                        elif get_origin(attribute_type) is list and value is not None:
                            object_instantiated[key] = cls._parse_list_attribute(
                                value, attribute_type, object_name, key
                            )
                        else:
                            object_instantiated[key] = value

                    except Exception as e:
                        raise FileParsingError(
                            f"Error processing attribute '{key}' for object '{object_name}' "
                            f"of type '{object_type}': {str(e)}"
                        ) from e

                objects_instantiated.append(object_instantiated)

            except Exception as e:
                if isinstance(e, FileParsingError):
                    raise
                raise FileParsingError(f"Error processing object {i} of type '{object_type}': {str(e)}") from e

        return objects_instantiated

    @classmethod
    def _parse_datetime(cls, value: Any, date_format: str) -> str:
        """Parse datetime values with proper error handling."""
        try:
            if isinstance(value, (datetime | DateTime)):
                return pendulum.instance(value).to_datetime_string()
            else:
                return pendulum.from_format(value, date_format).to_datetime_string()
        except Exception as e:
            raise DataValidationError(f"Invalid datetime value '{value}' with format '{date_format}': {str(e)}") from e

    @classmethod
    def _parse_list_attribute(
        cls, value: str, attribute_type: type[BusinessModel] | float | str | int | None, object_name: str, key: str
    ) -> list:
        """Parse list attributes with proper error handling."""
        try:
            inside_type = get_args(attribute_type)[0]
            if inside_type in (float, int):
                return list(map(inside_type, value.split(":")))
            else:
                return list(map(str, value.split(":")))
        except Exception as e:
            raise DataValidationError(
                f"Error parsing list attribute '{key}' for object '{object_name}': "
                f"Expected format 'item1:item2:item3', got '{value}'. Error: {str(e)}"
            ) from e

    @classmethod
    def _build_business_models(
        cls,
        object_list: list[dict[str, Any]],
        object_type: str,
        objects_instantiated: dict[str, list[type[BusinessModel]]],
    ) -> list[type[BusinessModel]]:
        """Instantiate final BusinessModel objects from intermediate math object dictionaries."""
        business_models = []

        for _, obj in enumerate(object_list):
            try:
                business_model = cls._build_single_business_model(obj, object_type, objects_instantiated)
                business_models.append(business_model)
            except Exception as e:
                object_name: str = obj["name"]
                raise ObjectInstantiationError(
                    f"Failed to instantiate business model '{object_name}' of type '{object_type}': {str(e)}"
                ) from e

        return business_models

    @staticmethod
    def _build_single_business_model(
        object_dict: dict[str, Any],
        object_type: str,
        objects_instantiated: dict[str, list[type[BusinessModel]]],
    ) -> type[BusinessModel]:
        """Instantiate a single BusinessModel object from its attributes."""
        object_name = object_dict.get("name", "unnamed_object")

        try:
            cfg.logger.debug(
                f"Instantiating business model '{object_name}' - type {cfg.MODEL_MAPPING_NAME[object_type].__name__}"
            )

            for attribute in object_dict:
                try:
                    attribute_type = get_type_attribute(object_type, attribute)

                    if attribute_type in cfg.INVERSE_MODEL_MAPPING_NAME:
                        if attribute_type is cfg.MODEL_MAPPING_NAME["equipment"]:
                            InputLoader._resolve_equipment_reference(object_dict, objects_instantiated)
                        else:
                            InputLoader._resolve_single_object_reference(
                                object_dict,
                                attribute,
                                attribute_type,  # type: ignore[arg-type]
                                objects_instantiated,
                            )
                    elif get_origin(attribute_type) is list:
                        if get_args(attribute_type)[0] in cfg.INVERSE_MODEL_MAPPING_NAME:
                            InputLoader._resolve_list_object_reference(
                                object_dict, attribute, attribute_type, objects_instantiated
                            )

                except Exception as e:
                    raise ObjectInstantiationError(
                        f"Error resolving attribute '{attribute}' for object '{object_name}': {str(e)}"
                    ) from e

            return cast(type[BusinessModel], cfg.MODEL_MAPPING_NAME[object_type](**object_dict))

        except Exception as e:
            if isinstance(e, ObjectInstantiationError):
                raise
            raise ObjectInstantiationError(
                f"Failed to create {cfg.MODEL_MAPPING_NAME[object_type].__name__} "
                f"instance for '{object_name}': {str(e)}"
            ) from e

    @staticmethod
    def _resolve_equipment_reference(
        object_dict: dict[str, Any], objects_instantiated: dict[str, list[type[BusinessModel]]]
    ) -> None:
        """Resolve equipment references with error handling."""
        equipment_name = object_dict.get("equipment")
        if not equipment_name:
            return

        equipment_found = False
        for attr in cfg.EQUIPMENT_MODELS:
            if attr in objects_instantiated:
                equipment_lookup = {model.name: model for model in objects_instantiated[attr]}
                if equipment_name in equipment_lookup:
                    object_dict["equipment"] = equipment_lookup[equipment_name]
                    equipment_found = True
                    break

        if not equipment_found:
            available_equipment = []
            for attr in cfg.EQUIPMENT_MODELS:
                if attr in objects_instantiated:
                    available_equipment.extend([model.name for model in objects_instantiated[attr]])

            raise DataValidationError(
                f"Equipment '{equipment_name}' not found. Available equipment: {available_equipment}"
            )

    @staticmethod
    def _resolve_single_object_reference(
        object_dict: dict[str, Any],
        attribute: str,
        attribute_type: type[BusinessModel],
        objects_instantiated: dict[str, list[type[BusinessModel]]],
    ) -> None:
        """Resolve single object references with error handling."""
        object_name: str = object_dict[attribute]
        object_type_key: str = cfg.INVERSE_MODEL_MAPPING_NAME[attribute_type]

        if object_type_key not in objects_instantiated:
            raise DataValidationError(
                f"No objects of type '{object_type_key}' have been instantiated yet. You may have missing data in your dataset."
            )

        objects_lookup = {model.name: model for model in objects_instantiated[object_type_key]}

        if object_name not in objects_lookup:
            available_objects = list(objects_lookup.keys())
            raise DataValidationError(
                f"Object '{object_name}' of type '{object_type_key}' not found. Available objects: {available_objects}"
            )

        object_dict[attribute] = objects_lookup[object_name]

    @staticmethod
    def _resolve_list_object_reference(
        object_dict: dict[str, Any],
        attribute: str,
        attribute_type: type[BusinessModel] | float | str | int | None,
        objects_instantiated: dict[str, list[type[BusinessModel]]],
    ) -> None:
        """Resolve list object references with error handling."""
        object_list_string = object_dict[attribute]
        if not object_list_string:
            return

        object_type_key = cfg.INVERSE_MODEL_MAPPING_NAME[get_args(attribute_type)[0]]

        if object_type_key not in objects_instantiated:
            raise DataValidationError(
                f"No objects of type '{object_type_key}' have been instantiated yet. Check the instantiation order."
            )

        objects_lookup = {model.name: model for model in objects_instantiated[object_type_key]}
        object_list_instantiated = []
        missing_objects = []

        for obj_string in object_list_string:
            if obj_string in objects_lookup:
                object_list_instantiated.append(objects_lookup[obj_string])
            else:
                missing_objects.append(obj_string)

        if missing_objects:
            available_objects = list(objects_lookup.keys())
            raise DataValidationError(
                f"Objects {missing_objects} of type '{object_type_key}' not found. "
                f"Available objects: {available_objects}"
            )

        object_dict[attribute] = object_list_instantiated

    @classmethod
    def _parse_objects_files(cls, objects_path: Path, separator: str = ";") -> dict[str, list[dict[str, str]]]:
        """Parse object definitions from the 'objects' directory with enhanced error handling."""
        cfg.logger.debug(f"Parsing objects from directory: {objects_path}")
        result = {}
        parsing_errors = {}

        if not list(objects_path.iterdir()):
            raise DirectoryStructureError(f"Objects directory is empty: {objects_path}")

        for file_path in objects_path.iterdir():
            if file_path.is_dir():
                cfg.logger.debug(f"Skipping subdirectory: {file_path}")
                continue

            key = file_path.stem

            if key not in cfg.MODEL_MAPPING_NAME:
                cfg.logger.warning(
                    f"File '{file_path.name}' does not correspond to a recognized Atlas object type. "
                    f"Available types: {list(cfg.MODEL_MAPPING_NAME.keys())}"
                )
                continue

            try:
                cfg.logger.debug(f"Parsing file: {file_path}")
                data = read_data_file(file_path, separator=separator).to_dicts()

                if not data:
                    cfg.logger.warning(f"File {file_path} is empty or contains no valid data")
                    continue

                # Validate that all objects have a 'name' attribute
                for i, obj in enumerate(data):
                    if "name" not in obj or not obj["name"]:
                        raise DataValidationError(
                            f"Object at line {i + 2} in {file_path} is missing a 'name' attribute"
                        )

                result[key] = data
                cfg.logger.debug(f"Successfully parsed {len(data)} objects from {file_path}")

            except Exception as e:
                parsing_errors[key] = str(e)
                cfg.logger.error(f"Failed to parse {file_path}: {str(e)}")

        if parsing_errors and not result:
            error_details = "\n".join([f"  - {key}: {error}" for key, error in parsing_errors.items()])
            raise FileParsingError(f"Failed to parse any object files. Errors encountered:\n{error_details}")
        elif parsing_errors:
            cfg.logger.warning(
                f"Some files could not be parsed but others were successful. "
                f"Failed files: {list(parsing_errors.keys())}"
            )

        return result

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
        """Load a Timeseries or LazyTimeseries from a file with enhanced error handling."""
        timeseries_dir = base_path / "timeseries"
        object_type_dir = timeseries_dir / object_type
        timeseries_path = object_type_dir / (name + file_extension)

        # Validate directory structure
        if not timeseries_dir.exists():
            raise DirectoryStructureError(
                f"Directory does not contain 'timeseries' subdirectory: {base_path}. Expected: {timeseries_dir}"
            )

        if not object_type_dir.exists():
            raise DirectoryStructureError(
                f"Timeseries directory does not contain subdirectory for object type '{object_type}': {timeseries_dir}. "
                f"Expected: {object_type_dir}"
            )

        if not timeseries_path.exists():
            # List available files for better error message
            available_files = [f.name for f in object_type_dir.iterdir() if f.is_file()]
            raise FileNotFoundError(
                f"Timeseries file not found: {timeseries_path}. Available files in {object_type_dir}: {available_files}"
            )

        cfg.logger.debug(f"Loading timeseries from file: {timeseries_path} with attribute {attribute_name}")

        try:
            if lazy:
                return LazyTimeseries.from_file(
                    file_path=timeseries_path,
                    timezone=timezone,
                    filters=("attribute", attribute_name),
                )
            return Timeseries.from_file(
                file_path=timeseries_path, timezone=timezone, filters=("attribute", attribute_name)
            )
        except Exception as e:
            raise FileParsingError(
                f"Failed to load timeseries from {timeseries_path} for attribute '{attribute_name}': {str(e)}"
            ) from e

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
        date_format_forecasting: str = "YYYY-MM-DD HH:mm:ss",
    ) -> Matrix | LazyMatrix:
        """Load a ForecastingMatrix or ScenarioMatrix (lazy or not) from a file with enhanced error handling."""
        if matrix_type not in ("scenario_matrix", "forecasting_matrix"):
            raise ValueError(f"Invalid matrix type '{matrix_type}'. Must be 'scenario_matrix' or 'forecasting_matrix'")

        base_path = Path(base_path)
        matrix_dir = base_path / matrix_type
        object_type_dir = matrix_dir / object_type
        matrix_file_path = object_type_dir / (name + file_extension)

        # Validate directory structure
        if not matrix_dir.exists():
            raise DirectoryStructureError(
                f"Directory does not contain '{matrix_type}' subdirectory: {base_path}. Expected: {matrix_dir}"
            )

        if not object_type_dir.exists():
            raise DirectoryStructureError(
                f"Matrix directory does not contain subdirectory for object type '{object_type}': {matrix_dir}. "
                f"Expected: {object_type_dir}"
            )

        if not matrix_file_path.exists():
            # List available files for better error message
            available_files = [f.name for f in object_type_dir.iterdir() if f.is_file()]
            raise FileNotFoundError(
                f"Matrix file not found: {matrix_file_path}. Available files in {object_type_dir}: {available_files}"
            )

        cfg.logger.debug(f"Loading {matrix_type} from file: {matrix_file_path}")

        try:
            if not lazy:
                if matrix_type == "scenario_matrix":
                    return ScenarioMatrix.from_file(
                        file_path=matrix_file_path,
                        timezone=timezone,
                        filters=("attribute", attribute_name),
                    )
                elif matrix_type == "forecasting_matrix":
                    return ForecastingMatrix.from_file(
                        file_path=matrix_file_path,
                        timezone=timezone,
                        filters=("attribute", attribute_name),
                        date_format=date_format_forecasting,
                    )
            else:
                if matrix_type == "scenario_matrix":
                    return LazyScenarioMatrix.from_file(
                        file_path=matrix_file_path,
                        timezone=timezone,
                        filters=("attribute", attribute_name),
                    )
                elif matrix_type == "forecasting_matrix":
                    return LazyForecastingMatrix.from_file(
                        file_path=matrix_file_path,
                        timezone=timezone,
                        filters=("attribute", attribute_name),
                    )

            # This should never be reached due to the validation above
            raise ValueError(f"Invalid matrix_type: {matrix_type}")

        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise FileParsingError(
                f"Failed to load {matrix_type} from {matrix_file_path} for attribute '{attribute_name}': {str(e)}"
            ) from e
