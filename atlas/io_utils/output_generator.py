"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements Output Generator Loader
"""

from pathlib import Path
from typing import Literal

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
        dataset: dict[str, list[BusinessModel]],
        directory_path: Path,
        separator: str = ";",
        timeseries_file_extension: Literal["csv", "parquet", "pickle"] = "parquet",
        matrix_file_extension: Literal["csv", "parquet", "pickle"] = "parquet",
    ) -> None:
        """
        Deserialize data set of BusinessModel objects to a directory.

        This method generates data files (CSV, Parquet) in a structured directory and
        constructs intermediate mathematical objects.

        :param dataset: The set of data to deserialize.
        :type dataset: dict[str, list[BusinessModel]]
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

            config.directory_path.mkdir(parents=True, exist_ok=True)
            objects_dir.mkdir(exist_ok=True)
            timeseries_dir.mkdir(exist_ok=True)
            scenario_matrix_dir.mkdir(exist_ok=True)
            forecasting_matrix_dir.mkdir(exist_ok=True)

            for object_type, objects_list in dataset.items():
                file_name = object_type + ".csv"
                file_path = objects_dir / file_name

                if not objects_list:
                    continue

                first_dump = objects_list[0].model_dump(mode="json")
                columns_name = [col for col in sorted(first_dump.keys()) if col != "name"]

                csv_rows = []
                header_row = ["name"] + columns_name
                csv_rows.append(config.separator.join(header_row))

                for business_object in objects_list:
                    for field_name, field_value in business_object:
                        if field_name == "name":
                            continue

                        if isinstance(field_value, Timeseries):
                            dir_path = timeseries_dir / object_type
                            dir_path.mkdir(exist_ok=True)
                            field_value.to_file_with_attribute(
                                path=dir_path / (business_object.name + "." + config.timeseries_file_extension),
                                attribute=field_name,
                                file_format=config.timeseries_file_extension,
                                separator=config.separator,
                                concatenate=True,
                            )

                        elif isinstance(field_value, ForecastingMatrix):
                            dir_path = forecasting_matrix_dir / object_type
                            dir_path.mkdir(exist_ok=True)
                            field_value.to_file_with_attribute(
                                path=dir_path / (business_object.name + "." + config.matrix_file_extension),
                                attribute=field_name,
                                file_format=config.matrix_file_extension,
                                separator=config.separator,
                                concatenate=True,
                            )

                        elif isinstance(field_value, ScenarioMatrix):
                            dir_path = scenario_matrix_dir / object_type
                            dir_path.mkdir(exist_ok=True)
                            field_value.to_file_with_attribute(
                                path=dir_path / (business_object.name + "." + config.matrix_file_extension),
                                attribute=field_name,
                                file_format=config.matrix_file_extension,
                                separator=config.separator,
                                concatenate=True,
                            )

                    dump_value = business_object.model_dump(mode="json")
                    row_values = [str(dump_value["name"])] + [
                        "" if dump_value[col] is None else str(dump_value[col]) for col in columns_name
                    ]
                    csv_rows.append(config.separator.join(row_values))

                with open(file_path, "w") as file:
                    file.write("\n".join(csv_rows) + "\n")
                cfg.logger.info(
                    f"Exported {len(objects_list)} objects of type {cfg.MODEL_MAPPING_NAME[object_type].__name__}"
                )

            cfg.logger.success("Atlas data exported successfully.")

        except Exception as e:
            raise InputLoaderError(f"Unexpected error during data export: {str(e)}") from e
