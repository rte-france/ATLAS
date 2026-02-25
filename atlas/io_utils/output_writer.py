"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Functional module for saving ATLAS datasets to directories.
"""

import shutil
from pathlib import Path
from typing import Literal

import atlas.config as cfg
from atlas.custom_errors import InputLoaderError
from atlas.io_utils.models import OutputGeneratorConfig
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_matrix import LazyScenarioMatrix
from atlas.math.matrix import ScenarioMatrix
from atlas.models.business_model import BusinessModel


def save_to_directory(
    dataset: dict[str, list[BusinessModel]],
    directory_path: Path,
    separator: str = ";",
    timeseries_file_extension: Literal["csv", "parquet", "pickle"] = "parquet",
    matrix_file_extension: Literal["csv", "parquet", "pickle"] = "parquet",
) -> None:
    """
    Serialize a dataset of BusinessModel objects to a directory.

    This function generates data files (CSV, Parquet) in a structured directory and
    exports all BusinessModel objects along with their mathematical objects.

    :param dataset: The set of data to serialize.
    :type dataset: dict[str, list[BusinessModel]]
    :param directory_path: The root path to the directory to write data.
    :type directory_path: pathlib.Path
    :param separator: The separator used in CSV files (default: ";").
    :type separator: str
    :param timeseries_file_extension: File extension for timeseries files (default: "parquet").
    :type timeseries_file_extension: Literal["csv", "parquet", "pickle"]
    :param matrix_file_extension: File extension for matrix files (default: "parquet").
    :type matrix_file_extension: Literal["csv", "parquet", "pickle"]

    :raises DataValidationError: If data validation fails
    """
    try:
        cfg.logger.info(f"Exporting Atlas output to directory: {directory_path}")

        config = OutputGeneratorConfig(
            directory_path=directory_path,
            separator=separator,
            timeseries_file_extension=timeseries_file_extension,
            matrix_file_extension=matrix_file_extension,
        )

        if config.directory_path.exists():
            shutil.rmtree(config.directory_path)

        _create_directory_structure(config)

        # Export each object type
        for object_type, objects_list in dataset.items():
            if not objects_list:
                continue

            _export_object_type(
                object_type=object_type,
                objects_list=objects_list,
                config=config,
            )

        cfg.logger.info("Atlas data exported successfully.")

    except Exception as e:
        raise InputLoaderError(f"Unexpected error during data export: {str(e)}") from e


def _create_directory_structure(config: OutputGeneratorConfig) -> None:
    """Create the directory structure for output."""
    directories = [
        config.directory_path,
        config.directory_path / "objects",
        config.directory_path / "timeseries",
        config.directory_path / "scenario_matrix",
        config.directory_path / "forecasting_matrix",
    ]

    for directory in directories:
        if not directory.is_dir():
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                cfg.logger.error(f"Permission denied: Unable to create '{directory}'.")
                raise


def _export_object_type(
    object_type: str,
    objects_list: list[BusinessModel],
    config: OutputGeneratorConfig,
) -> None:
    """Export a single object type to CSV and associated math files."""
    objects_dir = config.directory_path / "objects"
    timeseries_dir = config.directory_path / "timeseries"
    scenario_matrix_dir = config.directory_path / "scenario_matrix"
    forecasting_matrix_dir = config.directory_path / "forecasting_matrix"

    file_name = object_type + ".csv"
    file_path = objects_dir / file_name

    # Get column names from first object
    first_dump = objects_list[0].model_dump(mode="json")
    columns_name = [col for col in sorted(first_dump.keys()) if col != "name"]

    # Build CSV rows
    csv_rows = []
    header_row = ["name"] + columns_name
    csv_rows.append(config.separator.join(header_row))

    # Process each business object
    for business_object in objects_list:
        for field_name, field_value in business_object:
            if field_name == "name":
                continue

            # Export math objects to files
            if isinstance(field_value, AbstractTimeseries):
                _export_timeseries(
                    business_object=business_object,
                    field_name=field_name,
                    field_value=field_value,
                    object_type=object_type,
                    timeseries_dir=timeseries_dir,
                    config=config,
                )

            elif isinstance(field_value, ForecastingMatrix | LazyForecastingMatrix):
                _export_forecasting_matrix(
                    business_object=business_object,
                    field_name=field_name,
                    field_value=field_value,
                    object_type=object_type,
                    forecasting_matrix_dir=forecasting_matrix_dir,
                    config=config,
                )

            elif isinstance(field_value, ScenarioMatrix | LazyScenarioMatrix) and not isinstance(
                field_value, ForecastingMatrix | LazyForecastingMatrix
            ):
                _export_scenario_matrix(
                    business_object=business_object,
                    field_name=field_name,
                    field_value=field_value,
                    object_type=object_type,
                    scenario_matrix_dir=scenario_matrix_dir,
                    config=config,
                )

        # Add row to CSV
        dump_value = business_object.model_dump(mode="json")
        row_values = [str(dump_value["name"])] + [
            "" if dump_value[col] is None else str(dump_value[col]) for col in columns_name
        ]
        csv_rows.append(config.separator.join(row_values))

    # Write CSV file
    with open(file_path, "w") as file:
        file.write("\n".join(csv_rows) + "\n")


def _export_timeseries(
    business_object: BusinessModel,
    field_name: str,
    field_value: AbstractTimeseries,
    object_type: str,
    timeseries_dir: Path,
    config: OutputGeneratorConfig,
) -> None:
    """Export a timeseries to file."""
    dir_path = timeseries_dir / object_type
    dir_path.mkdir(exist_ok=True)

    field_value.to_file_with_attribute(
        path=dir_path / (business_object.name + "." + config.timeseries_file_extension),
        attribute=field_name,
        file_format=config.timeseries_file_extension,
        separator=config.separator,
        concatenate=True,
    )


def _export_forecasting_matrix(
    business_object: BusinessModel,
    field_name: str,
    field_value: ForecastingMatrix | LazyForecastingMatrix,
    object_type: str,
    forecasting_matrix_dir: Path,
    config: OutputGeneratorConfig,
) -> None:
    """Export a forecasting matrix to file."""
    dir_path = forecasting_matrix_dir / object_type
    dir_path.mkdir(exist_ok=True)

    field_value.to_file_with_attribute(
        path=dir_path / (business_object.name + "." + config.matrix_file_extension),
        attribute=field_name,
        file_format=config.matrix_file_extension,
        separator=config.separator,
        concatenate=True,
    )


def _export_scenario_matrix(
    business_object: BusinessModel,
    field_name: str,
    field_value: ScenarioMatrix | LazyScenarioMatrix,
    object_type: str,
    scenario_matrix_dir: Path,
    config: OutputGeneratorConfig,
) -> None:
    """Export a scenario matrix to file."""
    dir_path = scenario_matrix_dir / object_type
    dir_path.mkdir(exist_ok=True)

    field_value.to_file_with_attribute(
        path=dir_path / (business_object.name + "." + config.matrix_file_extension),
        attribute=field_name,
        file_format=config.matrix_file_extension,
        separator=config.separator,
        concatenate=True,
    )
