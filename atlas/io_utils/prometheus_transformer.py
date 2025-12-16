import os
import shutil
from pathlib import Path
from typing import Any, get_args

import h5py  # type: ignore[import-untyped]
import numpy as np
import pendulum
import polars as pl
import yaml

import atlas.config as cfg
from atlas.config import DEFAULT_VALUE_IO, logger
from atlas.io_utils.utils import to_snake_case
from atlas.timing import get_most_frequent_timestep, infer_frequency, pendulum_to_datetime
from atlas.typing import get_class_inheritance_chain, get_type_attribute

MAPPING_OBJECTS_TO_ATLAS = {"hydraulic": "hydro", "thermic": "thermal", "photovoltaic": "solar"}
NAME_MAPPING = {
    "Baseload": "BaseLoad",
    "is_v2_g": "is_v2g",
    "idpo_for_orders": "id_po_for_orders",
    "co2_emission": "co2_emissions",
    "daptdf": "da_ptdf",
}


class PrometheusToAtlasDataParser:
    def __init__(
        self,
        timeseries_path,
        hdf5_path,
        root_input_directory,
        date_format_forecasting="DD/MM/YYYY HH:mm:ss",
        date_format_input_files="DD/MM/YYYY HH:mm:ss",
        date_format_timestep="DD_MM_YYYY_HH_mm_ss",
    ):
        self.hdf5_path = hdf5_path
        self.root_input_directory = root_input_directory
        self.timeseries_path = timeseries_path
        self.date_format_forecasting = date_format_forecasting
        self.date_format_input_files = date_format_input_files
        self.date_format_timestep = date_format_timestep
        logger.info(f"Initialized parser with HDF5 path: {self.hdf5_path} and output root: {self.root_input_directory}")

        if Path(self.root_input_directory).exists():
            self.rm_root_dir()

    def rm_root_dir(self):
        shutil.rmtree(self.root_input_directory)

    def process(self):
        logger.info("Starting the parsing process.")
        with h5py.File(self.hdf5_path, "r") as f:
            object_types = list(f.keys())
            logger.info(f"Found object types: {object_types}")

            # Prepare output directories (snake_case)
            objects_dir = os.path.join(self.root_input_directory, "objects")
            ensure_dir(objects_dir)

            for object_type in object_types:
                object_type_snake = to_snake_case(object_type)

                if (
                    object_type_snake not in cfg.MODEL_MAPPING_NAME
                    and object_type_snake not in MAPPING_OBJECTS_TO_ATLAS
                ):
                    logger.warning(f"Object type {object_type_snake} not found in Atlas model mapping, skipping.")
                    continue
                if object_type_snake in MAPPING_OBJECTS_TO_ATLAS:
                    object_type_snake = MAPPING_OBJECTS_TO_ATLAS[object_type_snake]

                logger.info(f"Processing object type: {object_type} (as {object_type_snake})")
                group = f[object_type]
                instances = list(group.keys())
                logger.info(f"Instances found for {object_type_snake}: {instances}")
                attrs_list = []

                if instances is None or len(instances) == 0:
                    logger.warning(f"No instances found for {object_type_snake}. Skipping.")
                    continue

                for matrix_type in ["timeseries", "scenario_matrix", "forecasting_matrix"]:
                    ensure_dir(os.path.join(self.root_input_directory, matrix_type, object_type_snake))

                for instance in instances:
                    instance_snake = to_snake_case(instance)
                    logger.info(f"Processing instance: {instance} (as {instance_snake})")
                    instance_group = group[instance]
                    attrs = {"name": instance_snake}

                    for attr_name in instance_group:
                        attr_name_snake = to_snake_case(attr_name)

                        if (
                            attr_name_snake not in list(cfg.MODEL_MAPPING_NAME[object_type_snake].model_fields.keys())
                            and attr_name_snake not in NAME_MAPPING
                        ):
                            cfg.logger.warning(
                                f"The attribute {attr_name_snake} is not present in Atlas model object: {object_type_snake}, skipping it."
                            )
                            continue

                        if attr_name_snake in NAME_MAPPING:
                            attr_name_snake = NAME_MAPPING[attr_name_snake]
                        item = instance_group[attr_name]

                        logger.debug(
                            f"Processing attribute: {attr_name} (as {attr_name_snake}) for instance {instance_snake}"
                        )

                        file = find_file_with_subpaths(
                            list_all_files(self.timeseries_path),
                            object_type,
                            instance,
                            f"{attr_name}.csv",
                        )

                        if file:
                            logger.debug("Find a timeseries / matrix, copying it to Atlas dataset.")
                            if "forecast_matrix" in file:
                                matrix_type = "forecasting_matrix"
                                attrs[attr_name_snake] = "forecasting_matrix"
                            elif "scenario_matrix" in file:
                                matrix_type = "scenario_matrix"
                                attrs[attr_name_snake] = "scenario_matrix"
                            elif "timeseries" in file:
                                matrix_type = "timeseries"
                                attrs[attr_name_snake] = "timeseries"
                            else:
                                logger.warning("Failed to get the matrix / timeseries type")

                            try:
                                df = (
                                    pl.read_csv(file, separator=";")
                                    .with_columns(
                                        pl.col("TimeStep").str.strptime(
                                            pl.Datetime(), pendulum_to_datetime(self.date_format_timestep)
                                        )
                                    )
                                    .sort("TimeStep")
                                )
                                read_correctly = True
                            except Exception:
                                read_correctly = False
                                logger.warning(f"File is present but can't be read properly. Check {file}")
                            if read_correctly:
                                if matrix_type == "forecasting_matrix":
                                    duplicated_columns = [e for e in df.columns if "duplicated" in e]
                                    old_indexes = df.drop(*duplicated_columns).select(pl.selectors.numeric()).columns
                                    if len(old_indexes) > 0:
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
                                            .with_columns(
                                                pl.col("indexes").dt.strftime(
                                                    pendulum_to_datetime(self.date_format_forecasting)
                                                )
                                            )
                                            .to_series()
                                            .to_list()
                                        )

                                        df = df.select("TimeStep", *indexes_sorted).sort(
                                            "TimeStep"
                                        )  # sort indexes in case its not done

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
                                            .with_columns(
                                                pl.col("indexes").dt.strftime(
                                                    pendulum_to_datetime("YYYY-MM-DD HH:mm:ss")
                                                )
                                            )
                                            .to_series()
                                            .to_list()
                                        )

                                        renaming_mapping = dict(zip(indexes_sorted, new_indexes, strict=False))
                                        df = df.rename(renaming_mapping)

                                try:
                                    infer_frequency(df.rename({"TimeStep": "time"}))
                                except ValueError:
                                    timestep = get_most_frequent_timestep(df.rename({"TimeStep": "time"}))
                                    df = df.sort("TimeStep")
                                    df = (
                                        df.upsample(time_column="TimeStep", every=timestep)
                                        .fill_null(strategy="forward")
                                        .sort("TimeStep")
                                    )
                                df = df.with_columns(
                                    pl.lit(attr_name_snake).alias("attribute"),
                                ).select(
                                    pl.selectors.datetime(),
                                    pl.selectors.string(),
                                    pl.selectors.numeric(),
                                )

                                path_file_to_instance_matrix = (
                                    Path(self.root_input_directory)
                                    / matrix_type
                                    / object_type_snake
                                    / f"{instance_snake}.parquet"
                                )
                                if path_file_to_instance_matrix.exists():
                                    df_existing = pl.read_parquet(path_file_to_instance_matrix).select(
                                        pl.selectors.datetime(),
                                        pl.selectors.string(),
                                        pl.selectors.numeric(),
                                    )
                                    if len(df) > 0:
                                        df_concat = pl.concat([df_existing, df], how="diagonal")
                                        df_concat.write_parquet(path_file_to_instance_matrix)
                                    else:
                                        logger.warning("Csv has structure but is empty, skipping it")
                                        attrs[attr_name_snake] = None
                                else:
                                    if len(df) > 0:
                                        df.write_parquet(path_file_to_instance_matrix)
                                    else:
                                        logger.warning("Csv has structure but is empty, skipping it")
                                        attrs[attr_name_snake] = None
                                continue

                        if isinstance(item, h5py.Dataset):
                            val = item[()]
                            # Improved scalar/array logic
                            if is_simple_scalar(val) or array_is_scalar(val):
                                attrs[attr_name_snake] = (
                                    val.item() if hasattr(val, "item") and np.size(val) == 1 else val
                                )
                                if isinstance(attrs[attr_name_snake], bytes):
                                    attrs[attr_name_snake] = attrs[attr_name_snake].decode("utf-8")
                                    try:
                                        attrs[attr_name_snake] = pendulum.from_format(
                                            attrs[attr_name_snake], self.date_format_input_files
                                        ).to_datetime_string()
                                    except Exception:
                                        pass
                                if attrs[attr_name_snake] == "None":
                                    attrs[attr_name_snake] = None
                                if attrs[attr_name_snake] == "":
                                    attrs[attr_name_snake] = None
                                if attrs[attr_name_snake] in NAME_MAPPING:
                                    attrs[attr_name_snake] = NAME_MAPPING[attrs[attr_name_snake]]

                                type_attribute = get_type_attribute(
                                    object_type_snake, attr_name_snake
                                )  # gets the type of the attribute in the pydantic model
                                try:
                                    type_attribute = get_args(type_attribute)[0]
                                    # get the sub type if it's a Union or a list, to get the actual business model object into it if it exists
                                except Exception:
                                    pass
                                if attr_name_snake == "equipment" or type_attribute in cfg.MODEL_MAPPING_NAME.values():
                                    attrs[attr_name_snake] = to_snake_case(
                                        attrs[attr_name_snake]
                                    )  # convert to snake case to make a proper reference to the other business model object already in snake case
                                logger.debug(f"Scalar attribute: {attr_name_snake} = {attrs[attr_name_snake]}")
                            elif isinstance(val, np.ndarray):
                                if val.ndim == 1:
                                    if isinstance(list(val)[0], bytes):
                                        val = [v.decode("utf-8") for v in val]
                                    if (
                                        get_args(get_type_attribute(object_type_snake, attr_name_snake))[0]
                                        in cfg.MODEL_MAPPING_NAME.values()
                                    ):
                                        val = [to_snake_case(order) for order in val]
                                    attrs[attr_name_snake] = ":".join(map(str, list(val)))
                            else:
                                attrs[attr_name_snake] = str(item)
                                logger.warning(f"Unhandled attribute: {attr_name_snake} (type: {type(item)})")

                    for k in DEFAULT_VALUE_IO:
                        if k in get_class_inheritance_chain(object_type_snake):
                            for default_attr_name in DEFAULT_VALUE_IO[k]:
                                if default_attr_name not in attrs:
                                    attrs[default_attr_name] = DEFAULT_VALUE_IO[k][default_attr_name]
                        else:
                            continue

                    for attr_name, attr_value in instance_group.attrs.items():
                        attr_name_snake = to_snake_case(attr_name)
                        attrs[attr_name_snake] = attr_value
                        logger.info(f"Instance-level attribute: {attr_name_snake} = {attr_value}")
                    attrs_list.append(attrs)

                if attrs_list:
                    df_attrs = pl.DataFrame(attrs_list)
                    df_attrs = df_attrs.rename({col: to_snake_case(col) for col in df_attrs.columns})
                    csv_path = os.path.join(objects_dir, f"{object_type_snake}.csv")
                    df_attrs.write_csv(csv_path, separator=";")
                    logger.success(f"Wrote attributes CSV for {object_type_snake} to {csv_path}")
            logger.success("Export done to Atlas dataset !")


def deep_update(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively update the base dictionary with overrides.
    """
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = deep_update(base.get(key, {}), value)
        else:
            base[key] = value
    return base


def load_config(config_path: Path) -> dict[str, Any]:
    """
    Load configuration by overriding defaults with values from a YAML file.

    """
    config = DEFAULT_VALUE_IO.copy()

    if not config_path.exists():
        logger.debug("Config file not found at %s. Using defaults.", config_path)
        return config

    try:
        with config_path.open("r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
        return deep_update(config, user_config)
    except (yaml.YAMLError, OSError) as e:
        logger.warning("Failed to load config from %s: %s", config_path, e)
        return config


def ensure_dir(path):
    if not os.path.exists(path):
        Path(path).mkdir(parents=True, exist_ok=True)
        logger.info(f"Created directory: {path}")


def list_all_files(root_dir):
    file_paths = []
    for dirpath, _, filenames in os.walk(root_dir):
        for fname in filenames:
            full_path = os.path.join(dirpath, fname)
            file_paths.append(full_path)
    return file_paths


def find_file_with_subpaths(file_paths, str1, str2, str3):
    for full_path in file_paths:
        path_parts = full_path.split(os.sep)
        if {str1, str2, str3}.issubset(path_parts):
            return full_path
    return None


def is_simple_scalar(val):
    return np.isscalar(val) or isinstance(val, str | bytes)


def array_is_scalar(arr):
    # True if array has one unique value
    try:
        arr_flat = np.asarray(arr).flatten()
        return arr_flat.size == 1 or np.all(arr_flat == arr_flat[0])
    except Exception:
        return False
