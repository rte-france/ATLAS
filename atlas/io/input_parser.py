"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements Input Parser
"""

import json
from pathlib import Path
from typing import Literal

import polars as pl

import atlas.config as cfg
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.scenario_matrix import ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.business_model import BusinessModel


class InputParser:
    """A class to handle input parsing from Atlas format."""

    @classmethod
    def from_directory(cls, directory_path: str | Path, separator: str = ";") -> dict[str, list[BusinessModel]]:
        """Parse input from a directory.
        :param directory_path: The path to the directory.
        :type directory_path: str or pathlib.Path
        :param separator: The separator used in the CSV files.
        :type separator: str
        :return: A dictionary mapping object names to lists of instantiated objects.
        :rtype: dict[str, list[BusinessModel]]
        """
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
        objects_by_type: dict[str, list[BusinessModel]] = {}

        for object_type in objects:
            if object_type not in cfg.MODEL_MAPPING_NAME:
                raise ValueError(
                    f"Object type '{object_type}' is not recognized. "
                    f"Available types are: {list(cfg.MODEL_MAPPING_NAME.keys())}"
                )
            cls._instantiate_object_from_dict(
                objects[object_type],
                object_type,
            )

        return objects_by_type

    @classmethod
    def _instantiate_object_from_dict(
        cls, object_list: list[dict[str, str]], object_type: str, base_path: Path
    ) -> BusinessModel:
        """Instantiate objects from a dictionary of attributes.

        :param object_dict: A dictionary containing the attributes of the object.
        :type object_dict: dict
        :param object_type: The type of the object to instantiate.
        :type object_type: str
        :return: An instance of the specified object type.
        :rtype: BusinessModel
        """
        for obj in object_list:
            for key, value in obj.items():
                if key not in cfg.MODEL_MAPPING_NAME[object_type].__annotations__ and key != "instance_name":
                    raise ValueError(f"Key '{key}' is not a valid attribute for object type '{object_type}'.")
                if value == "timeseries":
                    obj[key] = cls.load_timeseries(
                        base_path=base_path,
                        object_type=object_type,
                        instance_name=obj["instance_name"],
                        attribute_name=key,
                    )
                elif value in ["forecasting_matrix", "scenario_matrix"]:
                    obj[key] = cls.load_matrix_from_file(
                        base_dir=base_path, instance_name=obj["instance_name"], matrix_type=value
                    )

        return obj

    @classmethod
    def _parse_objects_from_directory(cls, objects_path: Path, separator: str = ";") -> dict[str, list[dict[str, str]]]:
        """Parse objects from a directory.

        :param directory_path: The path to the directory.
        :type directory_path: str or pathlib.Path
        :return: A dictionary mapping object names to lists of instantiated objects.
        :rtype: dict[str, list[BusinessModel]]
        """
        objects: dict[str, dict[str, str]] = {}
        for file_path in objects_path.iterdir():
            df_objects = cls.from_file(file_path, separator=separator)
            objects[file_path.stem] = df_objects.to_dicts()
        return objects

    @classmethod
    def from_file(cls, file_path: str | Path, separator: str = ";") -> pl.DataFrame:
        """Parse input from a CSV file or a parquet file.

        :param file_path: The path to the file.
        :type file_path: str or pathlib.Path
        :return: A DataFrame containing the parsed CSV data.
        :rtype: pl.DataFrame
        """
        file_extension = Path(file_path).suffix

        if file_extension == ".csv":
            return cls._from_csv(file_path, separator=separator)
        if file_extension == ".parquet":
            return cls._from_parquet(file_path)
        raise ValueError(f"Unsupported file extension: {file_extension}")

    @staticmethod
    def _from_csv(file_path: str | Path, separator: str = ";") -> pl.DataFrame:
        """Parse input from a CSV file.

        :param file_path: The path to the CSV file.
        :type file_path: str or pathlib.Path
        :return: A DataFrame containing the parsed CSV data.
        :rtype: pl.DataFrame
        """
        return pl.read_csv(file_path, separator=separator)

    @staticmethod
    def _from_parquet(file_path: str | Path) -> pl.DataFrame:
        """Parse input from a Parquet file.

        :param file_path: The path to the Parquet file.
        :type file_path: str or pathlib.Path
        :return: A DataFrame containing the parsed Parquet data.
        :rtype: pl.DataFrame
        """
        return pl.read_parquet(file_path)

    @classmethod
    def parse_business_objects(cls, data_dir: str | Path) -> dict[str, pl.DataFrame]:
        """Parse business objects defined in the data/ folder.

        :param data_dir: Path to the folder containing business object CSVs.
        :type data_dir: str or Path
        :return: A dictionary mapping object names to parsed DataFrames.
        :rtype: dict[str, pl.DataFrame]
        :raises FileNotFoundError: If the directory does not exist.
        """
        data_dir = Path(data_dir)
        if not data_dir.exists():
            raise FileNotFoundError(f"Data directory not found: {data_dir}")
        return {file.stem: cls._from_csv(file) for file in data_dir.glob("*.csv")}

    @classmethod
    def load_timeseries(cls, base_path: Path, object_type: str, instance_name: str, attribute_name: str) -> Timeseries:
        """Load a timeseries profile from the timeseries/ folder.

        :param timeseries_dir: Path to the timeseries file.
        :type timeseries_dir: str or Path
        :return: A Timeseries object instantiated from the file.
        :rtype: Timeseries
        """
        timeseries_path = base_path / "timeseries" / object_type / instance_name / attribute_name
        return Timeseries(cls.from_file(timeseries_path))

    @classmethod
    def load_matrix_from_file(
        cls,
        base_path: str | Path,
        instance_name: str,
        object_type: str,
        attribute_name: str,
        matrix_type: Literal["scenario", "forecasting"],
    ) -> ScenarioMatrix | ForecastingMatrix:
        """Generic loader for scenario or forecasting matrix time series for a specific instance.

        :param base_dir: Path to the scenario_matrix/ or forecasting_matrix/ folder.
        :type base_dir: str or Path
        :param instance_name: Name of the instance (e.g., wind_turbine1_normandie).
        :type instance_name: str
        :param matrix_type: Type of matrix to load ("scenario" or "forecasting").
        :type matrix_type: str
        :return: An instance of the corresponding matrix class with loaded data.
        :rtype: ScenarioMatrix or ForecastingMatrix
        :raises FileNotFoundError: If the instance subfolder does not exist.
        :raises ValueError: If the matrix_type is invalid.
        """
        matrix_dir = matrix_type + "_matrix"
        instance_path = Path(base_path) / matrix_dir / object_type / instance_name / attribute_name
        if not instance_path.exists():
            raise FileNotFoundError(f"Path does not exist: {instance_path}")

        matrix_dict = {
            f.stem: cls.load_timeseries_from_file(f)
            for f in instance_path.glob("*.parquet")
            if f.name != "metadata.json"
        }

        if matrix_type == "scenario":
            return ScenarioMatrix(instance_name, list(matrix_dict.keys()), list(matrix_dict.values()))
        if matrix_type == "forecasting":
            return ForecastingMatrix(instance_name, list(matrix_dict.keys()), list(matrix_dict.values()))
        raise ValueError(f"Invalid matrix_type: {matrix_type}. Must be 'scenario' or 'forecasting'.")

    @staticmethod
    def load_metadata(folder_path: str | Path) -> dict:
        """Load metadata.json file if it exists in the given folder."""
        metadata_path = Path(folder_path) / "metadata.json"
        if not metadata_path.exists():
            return {}
        with open(metadata_path) as f:
            return json.load(f)
