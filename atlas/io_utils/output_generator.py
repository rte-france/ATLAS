"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements Output Generator Loader
"""

from pathlib import Path

import atlas.config as cfg
from atlas.custom_errors import (
    DataValidationError,
    DirectoryStructureError,
    FileParsingError,
    InputLoaderError,
    ObjectInstantiationError,
)
from atlas.io_utils.models import InputLoaderConfig
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.scenario_matrix import ScenarioMatrix
from atlas.math.matrix import Matrix
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
    def deserialize_directory(
        cls,
        dataset: dict[str, list[type[BusinessModel]]],
        directory_path: Path,
        separator: str = ";",
        timeseries_file_extension: str = ".parquet",
        matrix_file_extension: str = ".parquet"
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

        :raises DataValidationError: If data validation fails
        """
        try:
            cfg.logger.info(f"Exporting Atlas output to directory: {directory_path}")

            config = InputLoaderConfig(
                directory_path=directory_path,
                separator=separator,
                timeseries_file_extension=timeseries_file_extension,
                matrix_file_extension=matrix_file_extension
            )

            objects_dir = config.directory_path / "objects"
            timeseries_dir = config.directory_path / "timeseries"
            scenario_matrix_dir = config.directory_path / "scenario_matrix"
            forecasting_matrix_dir = config.directory_path / "forecasting_matrix"

            for object_key, object_values in dataset.items():
                file_name = object_key + ".csv"
                file_path = objects_dir / file_name
                rows = []

                # Generate first row
                columns_name = object_values[0].model_dump().keys()
                columns_name.remove("name")
                columns_name.sort()
                rows.append("name")

                for key in columns_name:
                    rows[0] += config.separator + key

                # Compute other rows
                idx_next_row = 0
                for value in object_values:
                    if isinstance(value, BusinessModel):
                        continue

                    dump_value = value.model_dump()
                    rows.append(dump_value["name"])
                    idx_next_row += 1

                    for field_name in columns_name:
                        rows[idx_next_row] += config.separator
                        if dump_value[field_name] is None:
                            continue
                        elif isinstance(dump_value[field_name], Timeseries):
                            dump_value[field_name].to_file(
                                timeseries_dir / object_key / dump_value["name"] + config.timeseries_file_extension,
                                config.timeseries_file_extension,
                                config.separator)
                            rows[idx_next_row] += "timeseries"
                        elif isinstance(dump_value[field_name], ForecastingMatrix):
                            dump_value[field_name].to_file(
                                forecasting_matrix_dir / object_key / dump_value["name"] + config.matrix_file_extension,
                                config.matrix_file_extension,
                                config.separator)
                            rows[idx_next_row] += "forecasting_matrix"
                        elif isinstance(dump_value[field_name], ScenarioMatrix):
                            dump_value[field_name].to_file(
                                scenario_matrix_dir / object_key / dump_value["name"] + config.matrix_file_extension,
                                config.matrix_file_extension,
                                config.separator)
                            rows[idx_next_row] += "scenario_matrix"
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