"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements AtlasDataset
"""

from __future__ import annotations

import copy
import pickle
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal, cast, get_origin

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

import atlas.config as cfg
from atlas.enums import BusinessModelName
from atlas.io_utils.container import Container
from atlas.io_utils.input_loader import load_from_directory
from atlas.io_utils.output_writer import save_to_directory
from atlas.models.business_model import BusinessModel
from atlas.models.control_block import ControlBlock
from atlas.models.equipment.equipment import Equipment
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
    - Serialization/deserialization via from_directory / to_directory, from_dict / to_dict methods, and pickle support

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

    control_block: Container[ControlBlock] = Field(default_factory=lambda: Container())
    critical_branch: Container[CriticalBranch] = Field(default_factory=lambda: Container())
    hydro: Container[Hydro] = Field(default_factory=lambda: Container())
    load: Container[Load] = Field(default_factory=lambda: Container())
    market_area: Container[MarketArea] = Field(default_factory=lambda: Container())
    market_area_ptdf: Container[MarketAreaPtdf] = Field(default_factory=lambda: Container())
    market_border: Container[MarketBorder] = Field(default_factory=lambda: Container())
    node: Container[Node] = Field(default_factory=lambda: Container())
    node_ptdf: Container[NodePtdf] = Field(default_factory=lambda: Container())
    order: Container[Order] = Field(default_factory=lambda: Container())
    order_coupling: Container[OrderCoupling] = Field(default_factory=lambda: Container())
    other_non_dispatchable: Container[OtherNonDispatchable] = Field(default_factory=lambda: Container())
    solar: Container[Solar] = Field(default_factory=lambda: Container())
    portfolio: Container[Portfolio] = Field(default_factory=lambda: Container())
    storage: Container[Storage] = Field(default_factory=lambda: Container())
    thermal: Container[Thermal] = Field(default_factory=lambda: Container())
    wind: Container[Wind] = Field(default_factory=lambda: Container())

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
        return cls(**data)  # type: ignore[arg-type]

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
                result[object_type] = list(objects)

        return result

    def to_pickle(self, file_path: Path | str) -> None:
        """
        Serialize the AtlasDataset to a pickle file.

        :param file_path: Path to the pickle file to write
        :type file_path: str or pathlib.Path
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

    def get_items_by_type(self, object_type: str | type[BusinessModel] | BusinessModelName) -> list[BusinessModel]:
        """
        Get a Container object by type with O(1) lookup.

        :param object_type: The type of object (e.g., "hydro", "node")
        :type object_type: str | type[BusinessModel] | BusinessModelName
        :return: The Container object if found, raise an error otherwise
        :rtype: Container
        """
        container = self.get_container_by_type(object_type)
        return container.all()

    def get_container_by_type(self, object_type: BusinessModelName | str | type[BusinessModel]) -> Container:
        """
        Get a Container object by type with O(1) lookup.

        :param object_type: The type of object (e.g., "hydro", "node")
        :type object_type: str | type[BusinessModel] | BusinessModelName
        :return: The Container object if found, raise an error otherwise
        :rtype: Container
        """
        if isinstance(object_type, type) and issubclass(object_type, BusinessModel):
            object_type_str = cfg.INVERSE_MODEL_MAPPING_NAME[object_type]
        elif isinstance(object_type, str):
            object_type_str = BusinessModelName(object_type)
        elif isinstance(object_type, BusinessModelName):
            object_type_str = object_type
        else:
            raise TypeError(f"Invalid type for object_type: {object_type!r}")
        container = getattr(self, object_type_str, None)
        if container is None:
            raise ValueError(f"No container found for type {object_type_str}")
        return container

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

    @field_validator(
        "control_block",
        "critical_branch",
        "hydro",
        "load",
        "market_area",
        "market_area_ptdf",
        "market_border",
        "node",
        "node_ptdf",
        "order",
        "order_coupling",
        "other_non_dispatchable",
        "solar",
        "portfolio",
        "storage",
        "thermal",
        "wind",
        mode="before",
    )
    @classmethod
    def _container_validator(cls, v: Any, info):
        """
        Ensure that container fields are either already a Container or a list of BusinessModel objects.
        """
        container_type = cls.model_fields[info.field_name].annotation
        origin_type = get_origin(container_type) or container_type  # unwrap Container[Node] -> Container

        if not isinstance(origin_type, type):
            raise TypeError(f"Cannot determine container type for field {info.field_name}")

        if isinstance(v, origin_type):
            return v

        if isinstance(v, list):
            return origin_type(v)  # wrap list in Container

        raise TypeError(f"{info.field_name} must be a {origin_type.__name__} or a list")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AtlasDataset):
            return NotImplemented
        DATASET_MODEL_NAMES = [k for k, v in cfg.MODEL_MAPPING_NAME.items() if k != BusinessModelName.EQUIPMENT]
        try:
            for object_type in DATASET_MODEL_NAMES:
                container_self = getattr(self, object_type)
                container_other = getattr(other, object_type)
                if container_self != container_other:
                    return False
        except Exception:
            return False
        return True

    def diff(self, other: AtlasDataset) -> dict[str, dict[str, Any]]:
        """
        Compare two AtlasDataset and return their differences, including nested fields.
        """
        result: dict[str, dict[str, Any]] = {}

        for object_type in cfg.MODEL_ORDER_INSTANTIATION:
            container: Container = getattr(self, object_type)
            other_container: Container = getattr(other, object_type)

            names = set(container._items.keys())
            other_names = set(other_container._items.keys())

            only_in_self = names - other_names
            only_in_other = other_names - names
            in_both = names & other_names

            modified: dict[str, dict[str, Any]] = {}
            for name in in_both:
                obj = container.get(name)
                other_obj = other_container.get(name)
                diff = AtlasDataset.diff_business_model(obj, other_obj)
                if diff:
                    modified[name] = diff

            if only_in_self or only_in_other or modified:
                result[object_type] = {
                    "only_in_self": sorted(only_in_self),
                    "only_in_other": sorted(only_in_other),
                    "modified": modified,
                }

        return result

    @staticmethod
    def diff_business_model(
        obj: BusinessModel,
        other_obj: BusinessModel,
        _visited: set[tuple[int, int]] | None = None,
    ) -> dict[str, Any]:
        """
        Recursively compare two BusinessModel instances field by field.
        Returns a dict of fields that differ, with (value_self, value_other) as value.
        _visited guards against circular references.
        """
        if _visited is None:
            _visited = set()

        # Guard against circular references
        pair = (id(obj), id(other_obj))
        if pair in _visited:
            return {}
        _visited.add(pair)

        field_diffs: dict[str, Any] = {}

        for field_name in obj.model_fields:
            val = getattr(obj, field_name, None)
            other_val = getattr(other_obj, field_name, None)

            # Nested BusinessModel → recurse
            if isinstance(val, BusinessModel) and isinstance(other_val, BusinessModel):
                nested_diffs = AtlasDataset.diff_business_model(val, other_val, _visited)
                if nested_diffs:
                    field_diffs[field_name] = {
                        "type": "nested",
                        "object_name": val.name,
                        "diffs": nested_diffs,
                    }
            elif isinstance(val, list) and isinstance(other_val, list):
                diff = AtlasDataset.diff_lists(val, other_val, _visited)
                if diff:
                    field_diffs[field_name] = diff
            else:
                diff = AtlasDataset.diff_on_other_than_business_model(val, other_val, _visited)
                if diff:
                    field_diffs[field_name] = diff

        return field_diffs

    @staticmethod
    def diff_on_other_than_business_model(
        val: Any, other_val: Any, _visited: set[tuple[int, int]] | None = None
    ) -> dict[str, Any] | None:
        if isinstance(val, list) and isinstance(other_val, list):
            return AtlasDataset.diff_lists(val, other_val, _visited)

        elif isinstance(val, str | int | float | bool):
            try:
                if val != other_val:
                    return {"self": val, "other": other_val}
            except Exception:
                return {"self": str(val), "other": str(other_val)}
        elif hasattr(val, "equals") and hasattr(other_val, "equals"):
            try:
                if not val.equals(other_val):
                    return {"changed": "not-serializable yet"}
            except Exception:
                return {"error": "Couldn't check diff"}
        else:
            try:
                if val != other_val:
                    return {"changed": "not-serializable yet"}
            except Exception:
                return {"error": "Couldn't check diff"}
        return None

    @staticmethod
    def diff_lists(
        _list: list,
        other_list: list,
        _visited: set[tuple[int, int]] | None = None,
    ) -> dict[str, Any] | None:
        if len(_list) != len(other_list):
            return {
                "type": "list_length",
                "self": len(_list),
                "other": len(other_list),
            }

        diffs = {}
        for i, (a, b) in enumerate(zip(_list, other_list, strict=True)):
            if isinstance(a, BusinessModel) and isinstance(b, BusinessModel):
                nested_diffs = AtlasDataset.diff_business_model(a, b, _visited)
                if nested_diffs:
                    diffs[str(i)] = {
                        "type": "nested",
                        "object_name": a.name,
                        "diffs": nested_diffs,
                    }
            else:
                try:
                    diff = AtlasDataset.diff_on_other_than_business_model(a, b, _visited)
                    if diff:
                        diffs[str(i)] = diff
                except Exception:
                    diffs[str(i)] = {"error": "Couldn't check diff"}
        return diffs if diffs else None

    def filter_dataset(
        self,
        included_types: Iterable[str | BusinessModelName] = (),
        filters: dict[str | BusinessModelName, Any] | None = None,
    ) -> AtlasDataset:
        filtered_data: dict[str, list[BusinessModel]] = {}
        for object_type in included_types:
            object_type_str = object_type.value if isinstance(object_type, BusinessModelName) else object_type
            if not filters or object_type_str not in filters:
                try:
                    container: Container[BusinessModel] = self.get_container_by_type(object_type_str)
                    filtered_data[object_type_str] = list([copy.deepcopy(obj) for obj in container])
                except ValueError:
                    continue

        if filters:
            for object_type, filter_fn in filters.items():
                object_type_str = object_type.value if isinstance(object_type, BusinessModelName) else object_type
                try:
                    filtered_container: Container[BusinessModel] = self.get_container_by_type(object_type_str)
                    filtered_data[object_type_str] = [copy.deepcopy(obj) for obj in filtered_container if filter_fn(obj)]
                except ValueError:
                    continue

        return AtlasDataset.from_dict(filtered_data)

    def filter_equipments(self, equipment_names: list[str] | None) -> AtlasDataset:
        copy_dataset = copy.deepcopy(self)
        if not equipment_names:
            return copy_dataset
        for equipment_type in cfg.EQUIPMENT_MODELS:
            equipments = copy_dataset.get_container_by_type(equipment_type)
            for equipment in copy_dataset.get_items_by_type(equipment_type):
                if equipment.name not in equipment_names:
                    equipments.remove(equipment.name)
        return copy_dataset

    def filter_zones(self, control_block_names: list[str], equipment_names: list[str] | None = None) -> AtlasDataset:
        dataset = AtlasDataset()
        for cb in self.control_block:
            if cb.name in control_block_names:
                dataset.control_block.add(cb)
        for ma in self.market_area:
            if ma.control_block is not None and ma.control_block.name in control_block_names:
                dataset.market_area.add(ma)
        for node in self.node:
            if node.control_block is not None and node.control_block.name in control_block_names:
                dataset.node.add(node)
        for border in self.market_border:
            if (
                border.downhill_control_block is not None
                and border.downhill_control_block.name in control_block_names
                and border.uphill_control_block is not None
                and border.uphill_control_block.name in control_block_names
            ):
                dataset.market_border.add(border)
        for ma_ptdf in self.market_area_ptdf:
            if (
                ma_ptdf.market_area is not None
                and ma_ptdf.market_area.control_block is not None
                and ma_ptdf.market_area.control_block.name in control_block_names
            ):
                dataset.market_area_ptdf.add(ma_ptdf)
        for node_ptdf in self.node_ptdf:
            if (
                node_ptdf.node is not None
                and node_ptdf.node.control_block is not None
                and node_ptdf.node.control_block.name in control_block_names
            ):
                dataset.node_ptdf.add(node_ptdf)
        for critical_branch in self.critical_branch:
            if (
                critical_branch.uphill_node is not None
                and critical_branch.uphill_node.control_block is not None
                and critical_branch.uphill_node.control_block.name in control_block_names
                and critical_branch.downhill_node is not None
                and critical_branch.downhill_node.control_block is not None
                and critical_branch.downhill_node.control_block.name in control_block_names
            ):
                dataset.critical_branch.add(critical_branch)
        for order in self.order:
            if (
                order.market_area is not None
                and order.market_area.control_block is not None
                and order.market_area.control_block.name in control_block_names
            ):
                dataset.order.add(order)
        # Hypothesis that every Order in OrderCoupling has the same MarketArea
        for order_coupling in self.order_coupling:
            keep_coupling = False
            if order_coupling.orders is None:
                continue
            for coupled_order in order_coupling.orders:
                if (
                    coupled_order.market_area is not None
                    and coupled_order.market_area.control_block is not None
                    and coupled_order.market_area.control_block.name in control_block_names
                ):
                    keep_coupling = True
                    break
            if keep_coupling:
                dataset.order_coupling.add(order_coupling)
        for portfolio in self.portfolio:
            if portfolio.control_block is not None and portfolio.control_block.name in control_block_names:
                dataset.portfolio.add(portfolio)

        for equipment_type in cfg.EQUIPMENT_MODELS:
            equipments = dataset.get_container_by_type(equipment_type)
            for equipment in self.get_items_by_type(equipment_type):
                equipment_node: Node | None = cast(Equipment, equipment).node
                if (
                    equipment_node is not None
                    and equipment_node.control_block is not None
                    and equipment_node.control_block.name in control_block_names
                ):
                    if equipment_names is None or equipment.name in equipments:
                        equipments.add(equipment)
        return copy.deepcopy(dataset)
