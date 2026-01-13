"""Prometheus HDF5 data transformer for Atlas datasets.

This module handles the conversion of Prometheus HDF5 data files into Atlas-compatible
datasets, including objects, timeseries, scenario matrices, and forecasting matrices.
"""

import os
import shutil
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, get_args

import h5py  # type: ignore[import-untyped]
import numpy as np
import numpy.typing as npt
import pendulum
import polars as pl
from pydantic_extra_types.pendulum_dt import DateTime, Duration

import atlas.config as cfg
from atlas.config import DEFAULT_VALUE_IO, logger
from atlas.io_utils.utils import to_snake_case
from atlas.timing import get_most_frequent_timestep, infer_frequency, pendulum_to_datetime
from atlas.typing import get_class_inheritance_chain, get_type_attribute

# Constants
MAPPING_OBJECTS_TO_ATLAS = {"hydraulic": "hydro", "thermic": "thermal", "photovoltaic": "solar"}

NAME_MAPPING = {
    "Baseload": "BaseLoad",
    "is_v2_g": "is_v2g",
    "idpo_for_orders": "id_po_for_orders",
    "co2_emission": "co2_emissions",
    "daptdf": "da_ptdf",
}

MATRIX_TYPES = ["timeseries", "scenario_matrix", "forecasting_matrix"]

DEFAULT_DATE_FORMAT_FORECASTING = "DD/MM/YYYY HH:mm:ss"
DEFAULT_DATE_FORMAT_INPUT = "DD/MM/YYYY HH:mm:ss"
DEFAULT_DATE_FORMAT_TIMESTEP = "DD_MM_YYYY_HH_mm_ss"
ATLAS_DATE_FORMAT = "YYYY-MM-DD HH:mm:ss"

CSV_SEPARATOR = ";"


class PrometheusToAtlasDataParser:
    """Parser for converting Prometheus HDF5 data to Atlas dataset format.

    This class handles the conversion of Prometheus data stored in HDF5 format
    along with CSV timeseries into the Atlas dataset structure with proper
    directory organization and data formatting.

    Args:
        timeseries_path: Path to directory containing CSV timeseries files
        hdf5_path: Path to the HDF5 file containing object metadata
        output_dir: Root directory for the output Atlas dataset
        date_format_forecasting: Date format for forecasting matrix columns
        date_format_input_files: Date format for input file timestamps
        date_format_timestep: Date format for timestep column in CSV files
    """

    def __init__(
        self,
        timeseries_path: str | Path,
        hdf5_path: str | Path,
        output_dir: str | Path,
        date_format_forecasting: str = DEFAULT_DATE_FORMAT_FORECASTING,
        date_format_input_files: str = DEFAULT_DATE_FORMAT_INPUT,
        date_format_timestep: str = DEFAULT_DATE_FORMAT_TIMESTEP,
    ) -> None:
        self.hdf5_path = Path(hdf5_path)
        self.output_dir = Path(output_dir)
        self.timeseries_path = Path(timeseries_path)
        self.date_format_forecasting = date_format_forecasting
        self.date_format_input_files = date_format_input_files
        self.date_format_timestep = date_format_timestep

        logger.info(f"Initialized parser with HDF5 path: {self.hdf5_path} and output root: {self.output_dir}")

        if self.output_dir.exists():
            self._remove_root_directory()

    def _remove_root_directory(self) -> None:
        """Remove the existing root directory and all its contents."""
        logger.info(f"Removing existing directory: {self.output_dir}")
        shutil.rmtree(self.output_dir)

    def process(self, use_multiprocessing: bool = True, n_workers: int | None = None) -> None:
        """Main processing method to convert Prometheus HDF5 data to Atlas format.

        This method orchestrates the entire conversion process:
        1. Reads HDF5 file structure
        2. Creates output directory structure
        3. Processes each object type and instance (in parallel if enabled)
        4. Converts timeseries/matrices to parquet format
        5. Exports object attributes to CSV

        Args:
            use_multiprocessing: Whether to use multiprocessing for parallel execution
            n_workers: Number of worker processes. If None, uses os.cpu_count()
        """
        logger.info("Starting the parsing process.")

        with h5py.File(self.hdf5_path, "r") as hdf5_file:
            object_types = list(hdf5_file.keys())
            logger.info(f"Found object types: {object_types}")

            objects_dir = self.output_dir / "objects"
            _ensure_directory(objects_dir)

            for object_type in object_types:
                self._process_object_type(hdf5_file, object_type, objects_dir, use_multiprocessing, n_workers)

        logger.success(f"Export done to Atlas dataset - {self.output_dir}!")

    def _process_object_type(
        self,
        hdf5_file: h5py.File,
        object_type: str,
        objects_dir: Path,
        use_multiprocessing: bool = False,
        n_workers: int | None = None,
    ) -> None:
        """Process a single object type from the HDF5 file.

        Parallelizes processing at the instance level if enabled.

        Args:
            hdf5_file: Opened HDF5 file handle
            object_type: Name of the object type to process
            objects_dir: Directory where object CSV files will be written
            use_multiprocessing: Whether to parallelize instance processing
            n_workers: Number of worker processes
        """
        object_type_snake = to_snake_case(object_type)

        # Map Prometheus names to Atlas names
        if object_type_snake in MAPPING_OBJECTS_TO_ATLAS:
            object_type_snake = MAPPING_OBJECTS_TO_ATLAS[object_type_snake]

        # Skip unknown object types
        if object_type_snake not in cfg.MODEL_MAPPING_NAME:
            logger.warning(f"Object type {object_type_snake} not found in Atlas model mapping, skipping.")
            return

        logger.info(f"Processing object type: {object_type} (as {object_type_snake})")

        group = hdf5_file[object_type]
        instances = list(group.keys())

        if not instances:
            logger.warning(f"No instances found for {object_type_snake}. Skipping.")
            return

        logger.info(f"Instances found for {object_type_snake}: {instances}")

        # Create matrix directories
        for matrix_type in MATRIX_TYPES:
            _ensure_directory(self.output_dir / matrix_type / object_type_snake)

        # Process instances in parallel or sequentially
        if use_multiprocessing and len(instances) > 1:
            n_workers = n_workers or min(os.cpu_count() or 1, len(instances))
            logger.info(f"Processing {len(instances)} instances in parallel using {n_workers} workers")

            with ProcessPoolExecutor(max_workers=n_workers) as executor:
                futures = [
                    executor.submit(self._process_instance_wrapper, instance, object_type, object_type_snake)
                    for instance in instances
                ]
                attrs_list = [future.result() for future in futures]
        else:
            if use_multiprocessing:
                logger.info(f"Processing {len(instances)} instance(s) sequentially (only 1 instance)")
            attrs_list = []
            for instance in instances:
                attrs = self._process_instance(group, instance, object_type, object_type_snake)
                attrs_list.append(attrs)

        if attrs_list:
            self._write_object_csv(attrs_list, objects_dir, object_type_snake)

    def _process_instance_wrapper(self, instance: str, object_type: str, object_type_snake: str) -> dict[str, Any]:
        """Wrapper for processing an instance that opens its own HDF5 file handle.

        This is needed for multiprocessing since HDF5 file handles cannot be shared
        across processes.

        Args:
            instance: Name of the instance to process
            object_type: Original object type name from HDF5
            object_type_snake: Snake-case name of the object type

        Returns:
            Dictionary of attributes for this instance
        """
        with h5py.File(self.hdf5_path, "r") as hdf5_file:
            group = hdf5_file[object_type]
            return self._process_instance(group, instance, object_type, object_type_snake)

    def _process_instance(
        self, group: h5py.Group, instance: str, object_type: str, object_type_snake: str
    ) -> dict[str, Any]:
        """Process a single instance of an object type.

        Args:
            group: HDF5 group containing the instances
            instance: Name of the instance to process
            object_type: Original object type name from HDF5
            object_type_snake: Snake-case name of the object type

        Returns:
            Dictionary of attributes for this instance
        """
        instance_snake = to_snake_case(instance)
        logger.info(f"Processing instance: {instance} (as {instance_snake})")

        instance_group = group[instance]
        attrs: dict[str, Any] = {"name": instance_snake}

        # Process datasets (timeseries, matrices, and scalar attributes)
        for attr_name in instance_group:
            self._process_attribute(
                instance_group, attr_name, attrs, object_type, object_type_snake, instance, instance_snake
            )

        # Apply default values based on inheritance chain
        self._apply_default_values(attrs, object_type_snake)

        # Process HDF5 group-level attributes
        for attr_name, attr_value in instance_group.attrs.items():
            attr_name_snake = to_snake_case(attr_name)
            attrs[attr_name_snake] = attr_value
            logger.debug(f"Instance-level attribute: {attr_name_snake} = {attr_value}")

        return attrs

    def _process_attribute(
        self,
        instance_group: h5py.Group,
        attr_name: str,
        attrs: dict[str, Any],
        object_type: str,
        object_type_snake: str,
        instance: str,
        instance_snake: str,
    ) -> None:
        """Process a single attribute of an instance.

        Args:
            instance_group: HDF5 group for this instance
            attr_name: Name of the attribute to process
            attrs: Dictionary to update with attribute values
            object_type: Original object type name from HDF5
            object_type_snake: Snake-case name of the object type
            instance: Original instance name
            instance_snake: Snake-case instance name
        """
        attr_name_snake = to_snake_case(attr_name)

        # Apply name mapping
        if attr_name_snake in NAME_MAPPING:
            attr_name_snake = NAME_MAPPING[attr_name_snake]

        # Validate attribute exists in model
        model_fields = cfg.MODEL_MAPPING_NAME[object_type_snake].model_fields.keys()
        if attr_name_snake not in model_fields:
            logger.debug(
                f"The attribute '{attr_name_snake}' is not present in Atlas model object: {object_type_snake}, skipping it."
            )
            return

        logger.debug(f"Processing attribute: {attr_name} (as {attr_name_snake}) for instance {instance_snake}")

        # Check if this is a timeseries/matrix file
        # Use original object_type name from HDF5 for file lookup
        csv_file = _find_file_with_subpaths(
            _list_all_files(self.timeseries_path),
            object_type,
            instance,
            f"{attr_name}.csv",
        )

        if csv_file:
            self._process_matrix_file(csv_file, attrs, attr_name_snake, object_type_snake, instance_snake)
        else:
            # Process scalar/array attributes from HDF5
            item = instance_group[attr_name]
            if isinstance(item, h5py.Dataset):
                self._process_dataset(item, attrs, attr_name_snake, object_type_snake)

    def _process_matrix_file(
        self,
        csv_file: str,
        attrs: dict[str, Any],
        attr_name_snake: str,
        object_type_snake: str,
        instance_snake: str,
    ) -> None:
        """Process a timeseries or matrix CSV file.

        Args:
            csv_file: Path to the CSV file
            attrs: Dictionary to update with matrix type
            attr_name_snake: Snake-case attribute name
            object_type_snake: Snake-case object type
            instance_snake: Snake-case instance name
        """
        logger.debug("Found a timeseries/matrix, copying it to Atlas dataset.")

        # Determine matrix type from file path
        matrix_type = self._determine_matrix_type(csv_file)
        if not matrix_type:
            logger.warning(f"Failed to determine matrix type for {csv_file}")
            return

        attrs[attr_name_snake] = matrix_type

        # Read and process the CSV file
        try:
            df = self._read_and_parse_csv(csv_file)
        except Exception as e:
            logger.warning(f"File is present but can't be read properly. Check {csv_file}: {e}")
            return

        # Special handling for forecasting matrices
        if matrix_type == "forecasting_matrix":
            df = self._normalize_forecasting_matrix(df)

        # Ensure regular frequency
        df = self._ensure_regular_frequency(df)

        # Add attribute column and select proper column order
        df = df.with_columns(pl.lit(attr_name_snake).alias("attribute")).select(
            pl.selectors.datetime(),
            pl.selectors.string(),
            pl.selectors.numeric(),
        )

        # Write to parquet (concatenate if file exists)
        self._write_matrix_parquet(df, matrix_type, object_type_snake, instance_snake, attrs, attr_name_snake)

    def _determine_matrix_type(self, file_path: str) -> str | None:
        """Determine the matrix type from the file path.

        Args:
            file_path: Path to the CSV file

        Returns:
            Matrix type string or None if not recognized
        """
        if "forecast_matrix" in file_path:
            return "forecasting_matrix"
        elif "scenario_matrix" in file_path:
            return "scenario_matrix"
        elif "timeseries" in file_path:
            return "timeseries"
        return None

    def _read_and_parse_csv(self, csv_file: str) -> pl.DataFrame:
        """Read CSV file and parse the TimeStep column.

        Args:
            csv_file: Path to the CSV file

        Returns:
            Parsed DataFrame with datetime TimeStep column
        """
        return (
            pl.read_csv(csv_file, separator=CSV_SEPARATOR)
            .with_columns(
                pl.col("TimeStep").str.strptime(pl.Datetime(), pendulum_to_datetime(self.date_format_timestep))
            )
            .sort("TimeStep")
        )

    def _normalize_forecasting_matrix(self, df: pl.DataFrame) -> pl.DataFrame:
        """Normalize forecasting matrix column names to Atlas format.

        Forecasting matrices have forecast dates as column names that need to be
        sorted and standardized to the Atlas date format.

        Args:
            df: DataFrame with forecasting matrix data

        Returns:
            DataFrame with normalized column names
        """
        # Remove duplicated columns
        duplicated_columns = [col for col in df.columns if "duplicated" in col]
        df = df.drop(*duplicated_columns)

        # Get numeric columns (forecast dates)
        old_indexes = df.select(pl.selectors.numeric()).columns

        if not old_indexes:
            return df

        # Sort columns by date
        indexes_sorted = (
            pl.DataFrame({"indexes": old_indexes})
            .with_columns(
                pl.col("indexes").str.strptime(
                    pl.Datetime(time_unit="us"),
                    pendulum_to_datetime(self.date_format_forecasting),
                    strict=False,
                )
            )
            .sort("indexes")
            .with_columns(pl.col("indexes").dt.strftime(pendulum_to_datetime(self.date_format_forecasting)))
            .to_series()
            .to_list()
        )

        # Reorder columns
        df = df.select("TimeStep", *indexes_sorted).sort("TimeStep")

        # Rename to Atlas format
        new_indexes = (
            pl.DataFrame({"indexes": indexes_sorted})
            .with_columns(
                pl.col("indexes").str.strptime(
                    pl.Datetime(time_unit="us", time_zone="UTC"),
                    pendulum_to_datetime(self.date_format_forecasting),
                    strict=False,
                )
            )
            .sort("indexes")
            .with_columns(pl.col("indexes").dt.strftime(pendulum_to_datetime(ATLAS_DATE_FORMAT)))
            .to_series()
            .to_list()
        )

        renaming_mapping = dict(zip(indexes_sorted, new_indexes, strict=False))
        return df.rename(renaming_mapping)

    def _ensure_regular_frequency(self, df: pl.DataFrame) -> pl.DataFrame:
        """Ensure the DataFrame has a regular time frequency.

        If frequency is irregular, upsample to most frequent timestep and forward fill.

        Args:
            df: DataFrame with TimeStep column

        Returns:
            DataFrame with regular frequency
        """
        try:
            infer_frequency(df.rename({"TimeStep": "time"}))
            return df
        except ValueError:
            logger.debug("Irregular frequency detected, upsampling to most frequent timestep")
            timestep = get_most_frequent_timestep(df.rename({"TimeStep": "time"}))
            return df.upsample(time_column="TimeStep", every=timestep).fill_null(strategy="forward").sort("TimeStep")

    def _write_matrix_parquet(
        self,
        df: pl.DataFrame,
        matrix_type: str,
        object_type_snake: str,
        instance_snake: str,
        attrs: dict[str, Any],
        attr_name_snake: str,
    ) -> None:
        """Write matrix DataFrame to parquet file, concatenating if exists.

        Args:
            df: DataFrame to write
            matrix_type: Type of matrix (timeseries, scenario_matrix, forecasting_matrix)
            object_type_snake: Snake-case object type
            instance_snake: Snake-case instance name
            attrs: Attribute dictionary to update if DataFrame is empty
            attr_name_snake: Snake-case attribute name
        """
        if df.is_empty():
            logger.warning("CSV has structure but is empty, skipping it")
            attrs[attr_name_snake] = None
            return

        parquet_path = self.output_dir / matrix_type / object_type_snake / f"{instance_snake}.parquet"

        if parquet_path.exists():
            # Concatenate with existing data
            df_existing = pl.read_parquet(parquet_path).select(
                pl.selectors.datetime(),
                pl.selectors.string(),
                pl.selectors.numeric(),
            )
            df_concat = pl.concat([df_existing, df], how="diagonal")
            df_concat.write_parquet(parquet_path)
        else:
            df.write_parquet(parquet_path)

    def _process_dataset(
        self, item: h5py.Dataset, attrs: dict[str, Any], attr_name_snake: str, object_type_snake: str
    ) -> None:
        """Process an HDF5 dataset (scalar or array attribute).

        Args:
            item: HDF5 Dataset object
            attrs: Dictionary to update with attribute value
            attr_name_snake: Snake-case attribute name
            object_type_snake: Snake-case object type
        """
        val = item[()]

        if _is_simple_scalar(val) or _array_is_scalar(val):
            # Handle scalar values
            attrs[attr_name_snake] = self._extract_scalar_value(val)

            # Apply type conversions based on the pydantic model type
            type_attribute = self._get_resolved_type(object_type_snake, attr_name_snake)

            if isinstance(attrs[attr_name_snake], bytes):
                attrs[attr_name_snake] = self._decode_bytes_attribute(attrs[attr_name_snake], type_attribute)
            elif isinstance(attrs[attr_name_snake], float | int):
                attrs[attr_name_snake] = self._convert_numeric_by_type(attrs[attr_name_snake], type_attribute)

            # Handle None/empty values
            if attrs[attr_name_snake] in ("None", ""):
                attrs[attr_name_snake] = None
                return

            # Apply name mapping to values
            if attrs[attr_name_snake] in NAME_MAPPING:
                attrs[attr_name_snake] = NAME_MAPPING[attrs[attr_name_snake]]

            # Convert to snake_case if referencing another model object
            if attr_name_snake == "equipment" or type_attribute in cfg.MODEL_MAPPING_NAME.values():
                attrs[attr_name_snake] = to_snake_case(attrs[attr_name_snake])

            logger.debug(f"Scalar attribute: {attr_name_snake} = {attrs[attr_name_snake]}")

        elif isinstance(val, np.ndarray) and val.ndim == 1:
            attrs[attr_name_snake] = self._process_array_attribute(val, object_type_snake, attr_name_snake)

        else:
            attrs[attr_name_snake] = str(item)
            logger.warning(f"Unhandled attribute: {attr_name_snake} (type: {type(item)})")

    def _extract_scalar_value(self, val: Any) -> Any:
        """Extract scalar value from numpy array or other types.

        Args:
            val: Value to extract from

        Returns:
            Scalar value
        """
        if hasattr(val, "item") and np.size(val) == 1:
            return val.item()
        return val

    def _decode_bytes_attribute(self, val: bytes, type_attribute: Any) -> str:
        """Decode bytes attribute and convert based on expected type.

        Args:
            val: Bytes value to decode
            type_attribute: Expected type from pydantic model

        Returns:
            Decoded string, potentially converted to datetime or duration format
        """
        decoded = val.decode("utf-8")

        # Check if the expected type is datetime or DateTime
        if type_attribute in (datetime, pendulum.DateTime, DateTime):
            try:
                return pendulum.from_format(decoded, self.date_format_input_files).to_datetime_string()
            except Exception:
                logger.debug(f"Failed to parse '{decoded}' as datetime, returning as string")
                return decoded

        return decoded

    def _convert_numeric_by_type(self, val: float | int, type_attribute: Any) -> str | float | int:
        """Convert numeric values based on expected type.

        Args:
            val: Numeric value
            type_attribute: Expected type from pydantic model

        Returns:
            Converted value (ISO8601 duration string for Duration types, original value otherwise)
        """
        # Check if the expected type is Duration
        if type_attribute in (Duration, pendulum.Duration):
            try:
                val = Duration(hours=float(val)).to_iso8601_string()  # type: ignore[assignment]
            except Exception as e:
                logger.debug(f"Failed to convert {val} to Duration: {e}, returning as is")
                return val

        return val

    def _get_resolved_type(self, object_type_snake: str, attr_name_snake: str) -> Any:
        """Get the resolved type of an attribute, unwrapping Union/Optional if needed.

        Args:
            object_type_snake: Snake-case object type
            attr_name_snake: Snake-case attribute name

        Returns:
            Resolved type annotation
        """

        type_attribute = get_type_attribute(object_type_snake, attr_name_snake)
        try:
            return get_args(type_attribute)[0]
        except (IndexError, TypeError):
            return type_attribute

    def _process_array_attribute(self, val: npt.NDArray[Any], object_type_snake: str, attr_name_snake: str) -> str:
        """Process 1D array attribute into colon-delimited string.

        Args:
            val: NumPy array
            object_type_snake: Snake-case object type
            attr_name_snake: Snake-case attribute name

        Returns:
            Colon-delimited string representation
        """

        items: list[Any] = [item.decode("utf-8") if isinstance(item, bytes) else item for item in val]

        type_attribute = get_type_attribute(object_type_snake, attr_name_snake)
        if type_attribute is not None:
            try:
                type_args = get_args(type_attribute)
                if type_args:
                    inner_type = type_args[0]
                    if inner_type in cfg.MODEL_MAPPING_NAME.values():
                        items = [to_snake_case(str(item)) for item in items]
            except (IndexError, TypeError):
                pass

        return ":".join(map(str, items))

    def _apply_default_values(self, attrs: dict[str, Any], object_type_snake: str) -> None:
        """Apply default values based on class inheritance chain.

        Args:
            attrs: Dictionary to update with default values
            object_type_snake: Snake-case object type
        """
        inheritance_chain = get_class_inheritance_chain(object_type_snake)
        for base_class in inheritance_chain:
            # base_class is str from the inheritance chain
            base_class_str = str(base_class) if not isinstance(base_class, str) else base_class
            if base_class_str in DEFAULT_VALUE_IO:
                defaults = DEFAULT_VALUE_IO[base_class_str]
                if isinstance(defaults, dict):
                    for default_attr_name, default_value in defaults.items():
                        if default_attr_name not in attrs:
                            attrs[default_attr_name] = default_value

    def _write_object_csv(self, attrs_list: list[dict[str, Any]], objects_dir: Path, object_type_snake: str) -> None:
        """Write object attributes to CSV file.

        Args:
            attrs_list: List of attribute dictionaries
            objects_dir: Directory for object CSV files
            object_type_snake: Snake-case object type
        """
        df_attrs = pl.DataFrame(attrs_list)
        df_attrs = df_attrs.rename({col: to_snake_case(col) for col in df_attrs.columns})
        csv_path = objects_dir / f"{object_type_snake}.csv"
        df_attrs.write_csv(csv_path, separator=CSV_SEPARATOR)
        logger.success(f"Wrote attributes CSV for {object_type_snake} to {csv_path}")


def _ensure_directory(path: Path) -> None:
    """Ensure a directory exists, creating it if necessary.

    Args:
        path: Directory path to ensure exists
    """
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Created directory: {path}")


def _list_all_files(root_dir: Path) -> list[str]:
    """Recursively list all files under a root directory.

    Args:
        root_dir: Root directory to search

    Returns:
        List of absolute file paths
    """
    file_paths = []
    for dirpath, _, filenames in os.walk(root_dir):
        for fname in filenames:
            file_paths.append(os.path.join(dirpath, fname))
    return file_paths


def _find_file_with_subpaths(file_paths: list[str], str1: str, str2: str, str3: str) -> str | None:
    """Find a file whose path contains all three specified substrings.

    Args:
        file_paths: List of file paths to search
        str1: First substring to match
        str2: Second substring to match
        str3: Third substring to match

    Returns:
        Matching file path or None if not found
    """
    for full_path in file_paths:
        path_parts = full_path.split(os.sep)
        if {str1, str2, str3}.issubset(path_parts):
            return full_path
    return None


def _is_simple_scalar(val: Any) -> bool:
    """Check if a value is a simple scalar (number, string, bytes).

    Args:
        val: Value to check

    Returns:
        True if value is a simple scalar
    """
    return np.isscalar(val) or isinstance(val, str | bytes)


def _array_is_scalar(arr: Any) -> bool:
    """Check if an array contains only a single unique value.

    Args:
        arr: Array-like object to check

    Returns:
        True if array has only one unique value
    """
    try:
        arr_flat = np.asarray(arr).flatten()
        return bool(arr_flat.size == 1 or np.all(arr_flat == arr_flat[0]))
    except Exception:
        return False


def find_hdf5_files(directory: Path) -> list[Path]:
    """
    Find all valid HDF5 files in the given directory.
    """

    if not directory.exists():
        return []

    files = [f for f in directory.iterdir() if f.is_file() and not f.name.startswith(".")]

    valid_hdf5_files = []
    for file_path in files:
        try:
            # Try to open the file as HDF5
            with h5py.File(file_path, "r") as _:
                valid_hdf5_files.append(file_path)
        except (OSError, ValueError, KeyError):
            continue

    return valid_hdf5_files
