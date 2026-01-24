"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements AtlasDataset
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

import atlas.config as cfg
from atlas.io_utils.input_loader import load_from_directory
from atlas.io_utils.output_writer import save_to_directory
from atlas.models.business_model import BusinessModel
from atlas.models.control_block import ControlBlock
from atlas.models.equipment.hydro import Hydro
from atlas.models.equipment.load import Load
from atlas.models.equipment.other_non_dispatchable import OtherNonDispatchable
from atlas.models.equipment.solar import Solar
from atlas.models.equipment.storage import Storage
from atlas.models.equipment.thermal import Thermal
from atlas.models.equipment.wind import Wind
from atlas.models.market.critical_branch import CriticalBranch
from atlas.models.market.market_area import MarketArea
from atlas.models.market.market_area_ptdf import MarketAreaPtdf
from atlas.models.market.market_border import MarketBorder
from atlas.models.market.node_ptdf import NodePtdf
from atlas.models.market.order import Order
from atlas.models.market.order_coupling import OrderCoupling
from atlas.models.node import Node
from atlas.models.portfolio import Portfolio


class AtlasDataset(BaseModel):
    """
    A Pydantic-based container for ATLAS BusinessModel objects with efficient lookup and I/O operations.

    This class provides:

    - Type-safe attribute access to different BusinessModel types
    - O(1) lookup by name for each object type
    - Serialization/deserialization via from_directory and to_directory
    - Validation of object references
    - Dictionary-style and attribute-style access

    Example:

        >>> dataset = AtlasDataset.from_directory("data/atlas-dataset")
        >>> # Attribute access
        >>> nodes = dataset.node
        >>> # Efficient lookup by name
        >>> thermal_plant = dataset.get("thermal", "my_plant")
        >>> # Export to directory
        >>> dataset.to_directory("output/atlas-dataset")
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    control_block: list[ControlBlock] = Field(default_factory=list)
    critical_branch: list[CriticalBranch] = Field(default_factory=list)
    hydro: list[Hydro] = Field(default_factory=list)
    load: list[Load] = Field(default_factory=list)
    market_area: list[MarketArea] = Field(default_factory=list)
    market_area_ptdf: list[MarketAreaPtdf] = Field(default_factory=list)
    market_border: list[MarketBorder] = Field(default_factory=list)
    node: list[Node] = Field(default_factory=list)
    node_ptdf: list[NodePtdf] = Field(default_factory=list)
    order: list[Order] = Field(default_factory=list)
    order_coupling: list[OrderCoupling] = Field(default_factory=list)
    other_non_dispatchable: list[OtherNonDispatchable] = Field(default_factory=list)
    solar: list[Solar] = Field(default_factory=list)
    portfolio: list[Portfolio] = Field(default_factory=list)
    storage: list[Storage] = Field(default_factory=list)
    thermal: list[Thermal] = Field(default_factory=list)
    wind: list[Wind] = Field(default_factory=list)

    _indices: dict[str, dict[str, BusinessModel]] = {}

    @classmethod
    def from_directory(
        cls,
        directory_path: Path | str,
        separator: str = ";",
        timeseries_file_extension: Literal["csv", "parquet", "pickle"] = "parquet",
        matrix_file_extension: Literal["csv", "parquet", "pickle"] = "parquet",
        lazy: bool = False,
        timezone: str = "UTC",
        date_format_forecasting_matrix: str = "YYYY-MM-DD HH:mm:ss",
        date_format_input_files: str = "YYYY-MM-DD HH:mm:ss",
    ) -> AtlasDataset:
        """
        Load an AtlasDataset from a directory structure.

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

        :return: An AtlasDataset instance containing all loaded BusinessModel objects.
        :rtype: AtlasDataset

        """
        if isinstance(directory_path, str):
            directory_path = Path(directory_path)

        raw_data = load_from_directory(
            directory_path=directory_path,
            separator=separator,
            timeseries_file_extension=timeseries_file_extension,
            matrix_file_extension=matrix_file_extension,
            lazy=lazy,
            timezone=timezone,
            date_format_forecasting_matrix=date_format_forecasting_matrix,
            date_format_input_files=date_format_input_files,
        )

        return cls.from_dict(raw_data)

    @classmethod
    def from_dict(cls, data: dict[str, list[BusinessModel]]) -> AtlasDataset:
        """
        Create an AtlasDataset from a dictionary of BusinessModel objects.

        :param data: Dictionary mapping object type names to lists of BusinessModel objects.
        :type data: dict[str, list[BusinessModel]]
        :return: An AtlasDataset instance
        :rtype: AtlasDataset
        """
        # Initialize with empty lists for all fields, then update with provided data
        kwargs: dict[str, Any] = {key: [] for key in cfg.MODEL_MAPPING_NAME.keys()}
        kwargs.update(data)

        return cls(**kwargs)

    def to_directory(
        self,
        directory_path: Path | str,
        separator: str = ";",
        timeseries_file_extension: Literal["csv", "parquet", "pickle"] = "parquet",
        matrix_file_extension: Literal["csv", "parquet", "pickle"] = "parquet",
    ) -> None:
        """
        Write the AtlasDataset to a directory structure.

        This method generates data files (CSV, Parquet) in a structured directory and
        exports all BusinessModel objects along with their mathematical objects.

        :param directory_path: The root path to the directory to write data.
        :type directory_path: str or pathlib.Path
        :param separator: The separator used in CSV files (default: ";").
        :type separator: str
        :param timeseries_file_extension: File extension for timeseries files (default: "parquet").
        :type timeseries_file_extension: Literal["csv", "parquet", "pickle"]
        :param matrix_file_extension: File extension for matrix files (default: "parquet").
        :type matrix_file_extension: Literal["csv", "parquet", "pickle"]

        """
        if isinstance(directory_path, str):
            directory_path = Path(directory_path)

        dataset_dict = self.to_dict()

        save_to_directory(
            dataset=dataset_dict,
            directory_path=directory_path,
            separator=separator,
            timeseries_file_extension=timeseries_file_extension,
            matrix_file_extension=matrix_file_extension,
        )

    def to_dict(self) -> dict[str, list[BusinessModel]]:
        """
        Convert the AtlasDataset to a dictionary representation.

        :return: Dictionary mapping object type names to lists of BusinessModel objects.
        :rtype: dict[str, list[BusinessModel]]
        """
        result: dict[str, list[BusinessModel]] = {}

        for object_type in cfg.MODEL_MAPPING_NAME.keys():
            objects = getattr(self, object_type, [])
            if objects:  # Only include non-empty lists
                result[object_type] = objects

        return result

    def to_pickle(self, file_path: Path | str) -> None:
        """
        Serialize the AtlasDataset to a pickle file.

        :param file_path: Path to the pickle file to write
        :type file_path: str or pathlib.Path

        Example:
            >>> dataset = AtlasDataset.from_directory("data/atlas-dataset")
            >>> dataset.to_pickle("dataset.pkl")
        """
        if isinstance(file_path, str):
            file_path = Path(file_path)

        with open(file_path, "wb") as f:
            pickle.dump(self, f)

    @classmethod
    def from_pickle(cls, file_path: Path | str) -> AtlasDataset:
        """
        Load an AtlasDataset from a pickle file.

        :param file_path: Path to the pickle file to read
        :type file_path: str or pathlib.Path
        :return: An AtlasDataset instance
        :rtype: AtlasDataset

        Example:
            >>> dataset = AtlasDataset.from_pickle("dataset.pkl")
        """
        if isinstance(file_path, str):
            file_path = Path(file_path)

        with open(file_path, "rb") as f:
            return pickle.load(f)

    @model_validator(mode="after")
    def _build_indices(self) -> AtlasDataset:
        """
        Build lookup indices after model initialization for O(1) name-based lookups.
        Also validates that all object names are unique within their type.
        """
        self._indices = {}

        for object_type in cfg.MODEL_MAPPING_NAME.keys():
            objects = getattr(self, object_type, [])
            if not objects:
                continue

            # Build index and check for duplicate names
            type_index: dict[str, BusinessModel] = {}
            for obj in objects:
                if obj.name in type_index:
                    raise ValueError(
                        f"Duplicate object name '{obj.name}' found in {object_type}. "
                        f"All object names must be unique within their type."
                    )
                type_index[obj.name] = obj

            self._indices[object_type] = type_index

        return self

    def get(self, object_type: str, name: str) -> BusinessModel | None:
        """
        Get a BusinessModel object by type and name with O(1) lookup.

        :param object_type: The type of object (e.g., "hydro", "node")
        :type object_type: str
        :param name: The name of the object to retrieve
        :type name: str
        :return: The BusinessModel object if found, None otherwise
        :rtype: BusinessModel | None
        """
        if object_type not in self._indices:
            return None
        return self._indices[object_type].get(name)

    def iter_by_types(self, *object_types: str):
        """
        Iterator over objects of one or more specific types.

        :param object_types: One or more object type names (e.g., "hydro", "node")
        :type object_types: str
        :yield: BusinessModel objects of the specified types
        :raises ValueError: If any object_type is not valid
        """
        # Validate all object types first
        for object_type in object_types:
            if object_type not in cfg.MODEL_MAPPING_NAME:
                raise ValueError(
                    f"Invalid object type '{object_type}'. Valid types: {list(cfg.MODEL_MAPPING_NAME.keys())}"
                )

        # Yield objects from each type
        for object_type in object_types:
            objects = getattr(self, object_type, [])
            yield from objects

    def __contains__(self, item: str | BusinessModel) -> bool:
        """
        Check if the dataset contains an object with the given name or instance.

        :param item: The object name (str) or BusinessModel instance to search for
        :type item: str | BusinessModel
        :return: True if an object with this name or instance exists in the dataset
        :rtype: bool
        """
        if isinstance(item, str):
            for type_index in self._indices.values():
                if item in type_index:
                    return True
            return False
        elif isinstance(item, BusinessModel):
            for type_index in self._indices.values():
                if item.name in type_index and type_index[item.name] is item:
                    return True
            return False
        else:
            return False

    def __iter__(self):
        """
        Iterate over all objects in the dataset across all types.

        Yields objects in the order defined by MODEL_MAPPING_NAME configuration.

        :yield: All BusinessModel objects in the dataset
        """
        for object_type in cfg.MODEL_MAPPING_NAME.keys():
            objects = getattr(self, object_type, [])
            yield from objects

    def __len__(self) -> int:
        """
        Get the total number of objects across all types.

        :return: Total count of all BusinessModel objects
        :rtype: int
        """
        total = 0
        for object_type in cfg.MODEL_MAPPING_NAME.keys():
            total += len(getattr(self, object_type, []))
        return total

    def __repr__(self) -> str:
        """String representation showing counts of each object type."""
        type_counts = []
        for object_type in cfg.MODEL_MAPPING_NAME.keys():
            objects = getattr(self, object_type, [])
            if objects:
                type_counts.append(f"{object_type}={len(objects)}")

        return f"AtlasDataset({', '.join(type_counts)})"

    def __str__(self) -> str:
        """User-friendly string representation."""
        return self.__repr__()

    def __getstate__(self) -> dict[str, Any]:
        """
        Prepare the object for pickling.

        Returns the model's state, excluding the _indices cache which will be rebuilt on unpickling.

        :return: Dictionary containing the object's state
        :rtype: dict[str, Any]
        """
        # Get the default state from Pydantic
        state = self.__dict__.copy()
        # Remove the _indices cache as it will be rebuilt by _build_indices validator
        state.pop("_indices", None)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        """
        Restore the object from pickled state.

        Reconstructs the object and rebuilds the _indices cache.

        :param state: Dictionary containing the object's pickled state
        :type state: dict[str, Any]
        """
        # Restore the state
        self.__dict__.update(state)
        # Rebuild indices (the validator will be called automatically by Pydantic)
        self._build_indices()
