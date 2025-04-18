"""Copyright (c) 2016-2022, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements Input Parser
"""

import json
from pathlib import Path
from typing import Any

import polars as pl

import atlas.config as cfg
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.scenario_matrix import ScenarioMatrix
from atlas.math.timeseries import Timeseries


class InputParser:
    """A class to handle input parsing from Atlas format."""

    @classmethod
    def from_directory(cls, directory_path: str | Path) -> None:
        """Parse input from a directory."""
        if not Path(directory_path).exists():
            raise FileNotFoundError(
                f"Directory does not exist: {directory_path}",
            )
        if not Path(directory_path).is_dir():
            raise NotADirectoryError(
                f"Path is not a directory: {directory_path}",
            )

        objects_by_type: dict[str, list[Any]] = {}

        for file_path in directory_path.iterdir():
            if file_path.is_file() and file_path.suffix == ".csv":
                model_key = file_path.stem
                if model_key in cfg.MODEL_MAPPING_NAME:
                    objects = cls._instantiate_objects_from_file(file_path, model_key)
                    objects_by_type[model_key] = objects

        return objects_by_type

    @classmethod
    def from_file(cls, file_path: str | Path) -> pl.DataFrame:
        """Load parameters from a YAML or JSON file.

        :param file_path: Path to the parameters file.
        :type file_path: str or Path
        :return: A Parameters object containing the parsed and validated parameters.
        :rtype: Parameters
        :raises ValueError: If the file extension is not supported.
        """
        file_extension = Path(file_path).suffix

        if file_extension == ".csv":
            return cls._from_csv(file_path)
        if file_extension == ".parquet":
            return cls._from_parquet(file_path)
        raise ValueError(f"Unsupported file extension: {file_extension}")

    @staticmethod
    def _from_csv(file_path: str | Path) -> pl.DataFrame:
        """Parse input from a CSV file.

        :param file_path: The path to the CSV file.
        :type file_path: str or pathlib.Path
        :return: A DataFrame containing the parsed CSV data.
        :rtype: pl.DataFrame
        """
        return pl.read_csv(file_path)

    @classmethod
    def _instantiate_objects_from_file(cls, file_path: Path, model_key: str) -> list[Any]:
        """Instantiate objects from a single file using the model class associated with the key.

        :param file_path: Path to the CSV file.
        :param model_key: Key corresponding to the model class in CSV_MODEL_MAPPING.
        :return: List of instantiated objects.
        """
        model_cls = cfg.MODEL_MAPPING_NAME[model_key]
        df = cls._from_csv(file_path)
        return [model_cls(**row) for row in df.to_dicts()]

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
    def load_timeseries_profile(cls, timeseries_dir: str | Path, filename: str) -> pl.DataFrame:
        """Load a timeseries profile from the timeseries/ folder.

        :param timeseries_dir: Path to the timeseries folder.
        :type timeseries_dir: str or Path
        :param filename: Name of the timeseries file.
        :type filename: str
        :return: A DataFrame containing the timeseries.
        :rtype: pl.DataFrame
        """
        path = Path(timeseries_dir) / filename
        return Timeseries(cls.from_file(path))

    @classmethod
    def load_scenario_matrix(
        cls,
        base_dir: str | Path,
        instance_name: str,
    ) -> dict[str, pl.DataFrame]:
        """Load scenario matrix time series for a specific instance.

        :param base_dir: Path to the scenario_matrix/ folder.
        :type base_dir: str or Path
        :param instance_name: Name of the instance (e.g., wind_turbine1_normandie).
        :type instance_name: str
        :return: A dictionary mapping scenario names to their timeseries DataFrames.
        :rtype: dict[str, pl.DataFrame]
        :raises FileNotFoundError: If the instance subfolder does not exist.
        """
        instance_path = Path(base_dir) / instance_name
        if not instance_path.exists():
            raise FileNotFoundError(f"Scenario matrix path does not exist: {instance_path}")
        return ScenarioMatrix(
            instance_name,
            {
                f.stem: cls.from_file(f)
                for f in instance_path.glob("*.parquet")
                if f.name != "metadata.json"
            },
        )

    @classmethod
    def load_forecasting_matrix(
        cls,
        base_dir: str | Path,
        instance_name: str,
    ) -> dict[str, pl.DataFrame]:
        """Load forecasting matrix time series for a specific instance.

        :param base_dir: Path to the forecasting_matrix/ folder.
        :type base_dir: str or Path
        :param instance_name: Name of the instance (e.g., wind_turbine1_normandie).
        :type instance_name: str
        :return: A dictionary mapping forecast timestamps to their timeseries DataFrames.
        :rtype: dict[str, pl.DataFrame]
        :raises FileNotFoundError: If the instance subfolder does not exist.
        """
        instance_path = Path(base_dir) / instance_name
        if not instance_path.exists():
            raise FileNotFoundError(f"Forecasting matrix path does not exist: {instance_path}")
        return ForecastingMatrix(
            {
                f.stem: cls.from_file(f)
                for f in instance_path.glob("*.parquet")
                if f.name != "metadata.json"
            }
        )

    @staticmethod
    def load_metadata(folder_path: str | Path) -> dict:
        """Load metadata.json file if it exists in the given folder."""
        metadata_path = Path(folder_path) / "metadata.json"
        if not metadata_path.exists():
            return {}
        with open(metadata_path) as f:
            return json.load(f)
