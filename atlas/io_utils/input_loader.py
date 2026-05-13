"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Functional module for loading ATLAS datasets from directories.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Literal, cast, get_args, get_origin

import atlas.config as cfg
from atlas.custom_errors import (
    DataValidationError,
    DirectoryStructureError,
    FileParsingError,
    InputLoaderError,
    ObjectInstantiationError,
)
from atlas.enums import BusinessModelName
from atlas.io_utils.models import InputLoaderConfig
from atlas.io_utils.utils import read_data_file
from atlas.math.abstract_scenario_matrix import AbstractScenarioMatrix
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_matrix import LazyScenarioMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.matrix import ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.objects.business_model import BusinessModel
from atlas.type import get_type_attribute


def load_from_directory(
    directory_path: Path,
    separator: str = ";",
    timeseries_file_extension: Literal["csv", "parquet", "pickle"] = "parquet",
    matrix_file_extension: Literal["csv", "parquet", "pickle"] = "parquet",
    lazy: bool = False,
    timezone: str = "UTC",
    date_format_forecasting_matrix: str = "YYYY-MM-DD HH:mm:ss",
    date_format_input_files: str = "YYYY-MM-DD HH:mm:ss",
) -> dict[str, list[BusinessModel]]:
    """
    Load input data from a directory and return instantiated BusinessModel objects.

    :param directory_path: The root path to the directory containing input data.
    :type directory_path: pathlib.Path
    :param separator: The separator used in CSV files (default: ";").
    :type separator: str
    :param timeseries_file_extension: File extension for timeseries files (default: "parquet").
    :type timeseries_file_extension: Literal["csv", "parquet", "pickle"]
    :param matrix_file_extension: File extension for matrix files (default: "parquet").
    :type matrix_file_extension: Literal["csv", "parquet", "pickle"]
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

    """
    try:
        cfg.logger.info(f"Loading Atlas input from directory: {directory_path}")

        config = InputLoaderConfig(
            directory_path=directory_path,
            separator=separator,
            timeseries_file_extension=timeseries_file_extension,
            matrix_file_extension=matrix_file_extension,
            lazy=lazy,
            timezone=timezone,
            date_format_forecasting_matrix=date_format_forecasting_matrix,
            date_format_input_files=date_format_input_files,
        )

        objects_dir = config.directory_path / "objects"
        objects = _parse_objects_files(objects_dir, separator=config.separator)

        if not objects:
            raise DataValidationError(
                f"No valid object files found in {objects_dir}. "
                f"Expected files named after object types with supported extensions."
            )

        objects_instantiated_with_math_objects = {}
        objects_instantiated: dict[str, list[BusinessModel]] = {}

        objects_type_sorted = sorted(objects, key=lambda x: cfg.MODEL_ORDER_INSTANTIATION.index(x))

        for object_type in objects_type_sorted:
            try:
                objects_instantiated_with_math_objects[object_type] = _build_math_objects(
                    objects[object_type],
                    object_type,
                    config,
                )

                objects_instantiated[object_type] = _build_business_models(
                    objects_instantiated_with_math_objects[object_type],
                    object_type,
                    objects_instantiated,
                )

                cfg.logger.debug(
                    f"Instantiated {len(objects_instantiated[object_type])} "
                    f"objects of type {cfg.MODEL_MAPPING_NAME[object_type].__name__}"
                )

            except Exception as e:
                raise ObjectInstantiationError(
                    f"Failed to instantiate objects of type '{object_type}': {str(e)}"
                ) from e

        cfg.logger.info("Atlas data loaded successfully.")
        return objects_instantiated

    except (DirectoryStructureError, FileParsingError, ObjectInstantiationError, DataValidationError):
        raise
    except Exception as e:
        raise InputLoaderError(f"Unexpected error during data loading: {str(e)}") from e


def _parse_objects_files(objects_path: Path, separator: str = ";") -> dict[BusinessModelName, list[dict[str, str]]]:
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

        key = BusinessModelName(file_path.stem)

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
                    raise DataValidationError(f"Object at line {i + 2} in {file_path} is missing a 'name' attribute")

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
            f"Some files could not be parsed but others were successful. Failed files: {list(parsing_errors.keys())}"
        )

    return result


def _build_math_objects(
    object_list: list[dict[str, Any]],
    object_type: BusinessModelName,
    config: InputLoaderConfig,
) -> list[dict[str, Any]]:
    """Parallel version of _build_math_objects for better performance with I/O operations."""
    results: list[dict[str, Any]] = [{}] * len(object_list)
    max_workers = min(4, len(object_list))  # Limit concurrent workers

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = {}
        for i, obj in enumerate(object_list):
            future = executor.submit(
                _process_single_object_math,
                obj,
                object_type,
                config,
                i,  # Pass index for error reporting
            )
            futures[future] = i

        # Collect results maintaining order
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                # Re-raise with context about which object failed
                obj_name = object_list[idx].get("name", f"object_{idx}")
                raise FileParsingError(f"Error processing object '{obj_name}' of type '{object_type}': {str(e)}") from e

    return results


def _process_single_object_math(
    obj: dict[str, Any],
    object_type: BusinessModelName,
    config: InputLoaderConfig,
    obj_index: int,
) -> dict[str, Any]:
    """Process a single object's math attributes. Used by parallel processing."""
    try:
        object_name = cast(str, obj["name"])
        cfg.logger.debug(f"Processing math objects for '{object_name}' (type: {object_type})")

        object_instantiated: dict[str, Any] = {}

        for key, value in obj.items():
            try:
                attribute_type = get_type_attribute(object_type, key)

                if value == "timeseries" and attribute_type is AbstractTimeseries:
                    object_instantiated[key] = _load_timeseries(
                        object_type=object_type,
                        name=object_name,
                        attribute_name=key,
                        config=config,
                    )

                elif value in ["forecasting_matrix", "scenario_matrix"] and attribute_type in (
                    ForecastingMatrix,
                    LazyForecastingMatrix,
                    AbstractScenarioMatrix,
                ):
                    object_instantiated[key] = _load_matrix(
                        name=object_name,
                        attribute_name=key,
                        object_type=object_type,
                        matrix_type=value,
                        config=config,
                    )
                else:
                    object_instantiated[key] = value

            except Exception as e:
                raise FileParsingError(
                    f"Error processing attribute '{key}' for object '{object_name}' of type '{object_type}': {str(e)}"
                ) from e

        return object_instantiated

    except Exception as e:
        if isinstance(e, FileParsingError):
            raise
        raise FileParsingError(f"Error processing object {obj_index} of type '{object_type}': {str(e)}") from e


def _load_timeseries(
    object_type: str,
    name: str,
    attribute_name: str,
    config: InputLoaderConfig,
) -> AbstractTimeseries:
    """Load a Timeseries or LazyTimeseries from a file with enhanced error handling."""
    timeseries_dir = config.directory_path / "timeseries"
    object_type_dir = timeseries_dir / object_type
    timeseries_path = object_type_dir / (name + "." + config.timeseries_file_extension)

    # Validate directory structure
    if not timeseries_dir.exists():
        raise DirectoryStructureError(
            f"Directory does not contain 'timeseries' subdirectory: {config.directory_path}. Expected: {timeseries_dir}"
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
        if config.lazy:
            return LazyTimeseries.from_file(
                file_path=timeseries_path,
                timezone=config.timezone,
                filters=("attribute", attribute_name),
            )
        return Timeseries.from_file(
            file_path=timeseries_path, timezone=config.timezone, filters=("attribute", attribute_name)
        )
    except Exception as e:
        raise FileParsingError(
            f"Failed to load timeseries from {timeseries_path} for attribute '{attribute_name}': {str(e)}"
        ) from e


def _load_matrix(
    name: str,
    object_type: str,
    attribute_name: str,
    matrix_type: Literal["scenario_matrix", "forecasting_matrix"],
    config: InputLoaderConfig,
) -> AbstractScenarioMatrix:
    """Load a ForecastingMatrix or ScenarioMatrix (lazy or not) from a file with enhanced error handling."""
    if matrix_type not in ("scenario_matrix", "forecasting_matrix"):
        raise ValueError(f"Invalid matrix type '{matrix_type}'. Must be 'scenario_matrix' or 'forecasting_matrix'")

    matrix_dir = config.directory_path / matrix_type
    object_type_dir = matrix_dir / object_type
    matrix_file_path = object_type_dir / (name + "." + config.matrix_file_extension)

    # Validate directory structure
    if not matrix_dir.exists():
        raise DirectoryStructureError(
            f"Directory does not contain '{matrix_type}' subdirectory: {config.directory_path}. Expected: {matrix_dir}"
        )

    if not object_type_dir.exists():
        raise DirectoryStructureError(
            f"ScenarioMatrix directory does not contain subdirectory for object type '{object_type}': {matrix_dir}. "
            f"Expected: {object_type_dir}"
        )

    if not matrix_file_path.exists():
        # List available files for better error message
        available_files = [f.name for f in object_type_dir.iterdir() if f.is_file()]
        raise FileNotFoundError(
            f"ScenarioMatrix file not found: {matrix_file_path}. Available files in {object_type_dir}: {available_files}"
        )

    cfg.logger.debug(f"Loading {matrix_type} from file: {matrix_file_path}")

    try:
        if not config.lazy:
            if matrix_type == "scenario_matrix":
                return ScenarioMatrix.from_file(
                    file_path=matrix_file_path,
                    timezone=config.timezone,
                    filters=("attribute", attribute_name),
                )
            elif matrix_type == "forecasting_matrix":
                return ForecastingMatrix.from_file(
                    file_path=matrix_file_path,
                    timezone=config.timezone,
                    filters=("attribute", attribute_name),
                    date_format=config.date_format_forecasting_matrix,
                )
        else:
            if matrix_type == "scenario_matrix":
                return LazyScenarioMatrix.from_file(
                    file_path=matrix_file_path,
                    timezone=config.timezone,
                    filters=("attribute", attribute_name),
                )
            elif matrix_type == "forecasting_matrix":
                return LazyForecastingMatrix.from_file(
                    file_path=matrix_file_path,
                    timezone=config.timezone,
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


def _build_business_models(
    object_list: list[dict[str, Any]],
    object_type: BusinessModelName,
    objects_instantiated: dict[str, list[BusinessModel]],
) -> list[BusinessModel]:
    """Instantiate final BusinessModel objects from intermediate math object dictionaries."""
    # Pre-build lookup indices once for performance
    object_indices = _build_object_indices(objects_instantiated)

    business_models = []

    for _, obj in enumerate(object_list):
        try:
            business_model = _build_single_business_model(obj, object_type, object_indices)
            business_models.append(business_model)
        except Exception as e:
            object_name: str = obj["name"]
            raise ObjectInstantiationError(
                f"Failed to instantiate business model '{object_name}' of type '{object_type}': {str(e)}"
            ) from e

    return business_models


def _build_object_indices(
    objects_instantiated: dict[str, list[BusinessModel]],
) -> dict[str, dict[str, BusinessModel]]:
    """
    Pre-build lookup indices for all object types for O(1) lookups.
    This dramatically improves performance by avoiding repeated dict comprehensions.
    """
    object_indices = {}

    # Build index for each object type
    for object_type, objects in objects_instantiated.items():
        object_indices[object_type] = {obj.name: obj for obj in objects}

    # Build combined equipment index for faster equipment lookups
    equipment_index = {}
    for equipment_type in cfg.EQUIPMENT_MODELS:
        if equipment_type in objects_instantiated:
            for obj in objects_instantiated[equipment_type]:
                equipment_index[obj.name] = obj

    object_indices["_equipment_combined"] = equipment_index

    return object_indices


def _build_single_business_model(
    object_dict: dict[str, Any],
    object_type: BusinessModelName,
    object_indices: dict[str, dict[str, BusinessModel]],
) -> BusinessModel:
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
                    if attribute_type is cfg.MODEL_MAPPING_NAME[BusinessModelName.EQUIPMENT]:
                        _resolve_equipment_reference(object_dict, object_indices)
                    else:
                        _resolve_single_object_reference(
                            object_dict,
                            attribute,
                            attribute_type,  # type: ignore[arg-type]
                            object_indices,
                        )
                elif get_origin(attribute_type) is list:
                    if get_args(attribute_type)[0] in cfg.INVERSE_MODEL_MAPPING_NAME:
                        _resolve_list_object_reference(object_dict, attribute, attribute_type, object_indices)

            except Exception as e:
                raise ObjectInstantiationError(
                    f"Error resolving attribute '{attribute}' for object '{object_name}': {str(e)}"
                ) from e

        return cast(BusinessModel, cfg.MODEL_MAPPING_NAME[object_type].model_validate(object_dict))

    except Exception as e:
        if isinstance(e, ObjectInstantiationError):
            raise
        raise ObjectInstantiationError(
            f"Failed to create {cfg.MODEL_MAPPING_NAME[object_type].__name__} instance for '{object_name}': {str(e)}"
        ) from e


def _resolve_equipment_reference(
    object_dict: dict[str, Any],
    object_indices: dict[str, dict[str, BusinessModel]],
) -> None:
    """Equipment reference resolution using pre-built indices."""
    equipment_name = object_dict.get("equipment")
    if not equipment_name:
        return

    equipment_index = object_indices.get("_equipment_combined", {})

    if equipment_name in equipment_index:
        object_dict["equipment"] = equipment_index[equipment_name]
    else:
        available_equipment = list(equipment_index.keys())
        raise DataValidationError(f"Equipment '{equipment_name}' not found. Available equipment: {available_equipment}")


def _resolve_single_object_reference(
    object_dict: dict[str, Any],
    attribute: str,
    attribute_type: type[BusinessModel],
    object_indices: dict[str, dict[str, BusinessModel]],
) -> None:
    """Single object reference resolution using pre-built indices."""
    object_name: str = object_dict[attribute]
    # Do not search for reference when attribute is None
    if not object_name:
        return None
    object_type_key: str = cfg.INVERSE_MODEL_MAPPING_NAME[attribute_type]

    type_index = object_indices.get(object_type_key)
    if not type_index:
        raise DataValidationError(
            f"No objects of type '{object_type_key}' have been instantiated yet. You may have missing data in your dataset."
        )

    if object_name in type_index:
        object_dict[attribute] = type_index[object_name]
    else:
        available_objects = list(type_index.keys())
        raise DataValidationError(
            f"Object '{object_name}' of type '{object_type_key}' not found. Available objects: {available_objects}"
        )


def _resolve_list_object_reference(
    object_dict: dict[str, Any],
    attribute: str,
    attribute_type: type[BusinessModel] | float | str | int | None,
    object_indices: dict[str, dict[str, BusinessModel]],
) -> None:
    """List object reference resolution using pre-built indices."""
    object_list_string = object_dict[attribute]
    if not object_list_string:
        object_dict[attribute] = []
        return

    object_type_key = cfg.INVERSE_MODEL_MAPPING_NAME[get_args(attribute_type)[0]]

    type_index = object_indices.get(object_type_key)
    if not type_index:
        raise DataValidationError(
            f"No objects of type '{object_type_key}' have been instantiated yet. Check the instantiation order."
        )

    # Parse the list from CSV format (colon-separated string)
    if isinstance(object_list_string, str):
        object_names = object_list_string.split("|")
    elif isinstance(object_list_string, list):
        object_names = object_list_string
    else:
        raise DataValidationError(
            f"Invalid list format for attribute '{attribute}': expected string or list, got {type(object_list_string)}"
        )

    object_list_instantiated = []
    missing_objects = []

    for obj_string in object_names:
        if obj_string in type_index:
            object_list_instantiated.append(type_index[obj_string])
        else:
            missing_objects.append(obj_string)

    if missing_objects:
        available_objects = list(type_index.keys())
        raise DataValidationError(
            f"Objects {missing_objects} of type '{object_type_key}' not found. Available objects: {available_objects}"
        )

    object_dict[attribute] = object_list_instantiated
