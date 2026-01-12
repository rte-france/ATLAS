"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements Output Generator Loader
"""

from pathlib import Path
from typing import Literal, cast

from pydantic_extra_types.pendulum_dt import Duration

import atlas.config as cfg
from atlas.custom_errors import InputLoaderError
from atlas.io_utils.models import OutputGeneratorConfig
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.scenario_matrix import ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.business_model import BusinessModel


class OutputGenerator:
    """
    A class to handle output deserialization to Atlas-formatted data directories.

    Provides utilities to write BusinessModel objects to a directory structure, including
    timeseries, forecasting matrices, and scenario matrices.
    Does not support lazy loading modes.

    The output directory will follow a specific structure:

        <root_output_directory>/
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
    - Each timeseries or matrix will match the expected file extension (default: `.parquet`).
    - Attribute names in the objects CSV will be either the value itself of the attribute, or the type if a math objects (e.g timeseries,
      forecasting_matrix, scenario_matrix)

    """

    @classmethod
    def to_directory(
        cls,
        dataset: dict[str, list[type[BusinessModel]]],
        directory_path: Path,
        separator: str = ";",
        timeseries_file_extension: Literal["csv", "parquet", "pickle"] = "parquet",
        matrix_file_extension: Literal["csv", "parquet", "pickle"] = "parquet"
    ) -> None:
        """
        Deserialize data set of BusinessModel objects to a directory.

        This method generates data files (CSV, Parquet) in a structured directory and
        constructs intermediate mathematical objects.

        :param dataset: The set of data to deserialize.
        :type dataset: dict[str, list[type[BusinessModel]]]
        :param directory_path: The root path to the directory containing input data.
        :type directory_path: str or pathlib.Path
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

            objects_dir = config.directory_path / "objects"
            timeseries_dir = config.directory_path / "timeseries"
            scenario_matrix_dir = config.directory_path / "scenario_matrix"
            forecasting_matrix_dir = config.directory_path / "forecasting_matrix"

            if not config.directory_path.is_dir():
                try:
                    config.directory_path.mkdir(parents=True, exist_ok=True)
                except PermissionError:
                    print(f"Permission denied: Unable to create '{config.directory_path}'.")
            if not objects_dir.is_dir():
                try:
                    objects_dir.mkdir()
                except PermissionError:
                    print(f"Permission denied: Unable to create '{objects_dir}'.")
            if not timeseries_dir.is_dir():
                try:
                    timeseries_dir.mkdir()
                except PermissionError:
                    print(f"Permission denied: Unable to create '{timeseries_dir}'.")
            if not scenario_matrix_dir.is_dir():
                try:
                    scenario_matrix_dir.mkdir()
                except PermissionError:
                    print(f"Permission denied: Unable to create '{scenario_matrix_dir}'.")
            if not forecasting_matrix_dir.is_dir():
                try:
                    forecasting_matrix_dir.mkdir()
                except PermissionError:
                    print(f"Permission denied: Unable to create '{forecasting_matrix_dir}'.")

            for object_key, object_values in dataset.items():
                file_name = object_key + ".csv"
                file_path = objects_dir / file_name
                rows = []

                # Generate first row
                columns_name = list(object_values[0].model_dump().keys())
                columns_name.remove("name")
                columns_name.sort()
                rows.append("name")

                for key in columns_name:
                    rows[0] += config.separator + key

                # Compute other rows
                idx_next_row = 0
                for value in object_values:
                    dump_value = value.model_dump()
                    rows.append(dump_value["name"])
                    idx_next_row += 1

                    for field_name in columns_name:
                        rows[idx_next_row] += config.separator
                        if dump_value[field_name] is None:
                            continue
                        elif isinstance(dump_value[field_name], Timeseries):
                            dir_path = timeseries_dir / object_key
                            if not dir_path.is_dir():
                                try:
                                    dir_path.mkdir()
                                except PermissionError:
                                    print(f"Permission denied: Unable to create '{dir_path}'.")
                            cast(Timeseries, dump_value[field_name]).to_file_with_attribute(
                                path=dir_path / (dump_value["name"] + "." + config.timeseries_file_extension),
                                attribute=field_name,
                                file_format=config.timeseries_file_extension,
                                separator=config.separator,
                                concatenate=True,
                            )
                            rows[idx_next_row] += "timeseries"
                        elif isinstance(dump_value[field_name], ForecastingMatrix):
                            dir_path = forecasting_matrix_dir / object_key
                            if not dir_path.is_dir():
                                try:
                                    dir_path.mkdir()
                                except PermissionError:
                                    print(f"Permission denied: Unable to create '{dir_path}'.")
                            cast(ForecastingMatrix, dump_value[field_name]).to_file_with_attribute(
                                path=dir_path / (dump_value["name"] + "." + config.matrix_file_extension),
                                attribute=field_name,
                                file_format=config.matrix_file_extension,
                                separator=config.separator,
                                concatenate=True,
                            )
                            rows[idx_next_row] += "forecasting_matrix"
                        elif isinstance(dump_value[field_name], ScenarioMatrix):
                            dir_path = scenario_matrix_dir / object_key
                            if not dir_path.is_dir():
                                try:
                                    dir_path.mkdir()
                                except PermissionError:
                                    print(f"Permission denied: Unable to create '{dir_path}'.")
                            cast(ScenarioMatrix, dump_value[field_name]).to_file_with_attribute(
                                path=dir_path / (dump_value["name"] + "." + config.matrix_file_extension),
                                attribute=field_name,
                                file_format=config.matrix_file_extension,
                                separator=config.separator,
                                concatenate=True,
                            )
                            rows[idx_next_row] += "scenario_matrix"
                        elif isinstance(dump_value[field_name], bool):
                            rows[idx_next_row] += "1" if dump_value[field_name] else "0"
                        elif isinstance(dump_value[field_name], str):
                            rows[idx_next_row] += dump_value[field_name]
                        elif isinstance(dump_value[field_name], int) or isinstance(dump_value[field_name], float):
                            rows[idx_next_row] += str(dump_value[field_name])
                        elif isinstance(dump_value[field_name], Duration):
                            value = dump_value[field_name].to_iso8601_string()
                            if value == "P":
                                rows[idx_next_row] += "PT0H"
                            else:
                                rows[idx_next_row] += value
                        elif isinstance(dump_value[field_name], dict):
                            rows[idx_next_row] += str(dump_value[field_name]["name"])
                        elif isinstance(dump_value[field_name], list):
                            rows[idx_next_row] += ":".join(map(str, dump_value[field_name]))
                        else:
                            rows[idx_next_row] += str(dump_value[field_name])

                # Write file
                with open(file_path, "w") as file:
                    for r in rows:
                        file.write(r)
                        file.write("\n")

            cfg.logger.success("Atlas data exported successfully.")

        except Exception as e:
            raise InputLoaderError(f"Unexpected error during data export: {str(e)}") from e
