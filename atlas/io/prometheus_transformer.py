import os
import re
from pathlib import Path

import h5py  # type: ignore[import-untyped]
import numpy as np
import polars as pl

from atlas.config import logger

MAPPING_OBJECTS_TO_ATLAS = {
    "hydraulic": "hydro",
    "thermic": "thermal",
    "photovoltaic": "solar",
}
NAME_MAPPING = {
    "Baseload": "BaseLoad",
    "is_v2_g": "is_v2g",
}


class PrometheusToAtlasDataParser:
    def __init__(self, hdf5_path, root_input_directory):
        self.hdf5_path = hdf5_path
        self.root_input_directory = root_input_directory
        logger.info(f"Initialized parser with HDF5 path: {self.hdf5_path} and output root: {self.root_input_directory}")

    def ensure_dir(self, path):
        if not os.path.exists(path):
            Path(path).mkdir(parents=True, exist_ok=True)
            logger.info(f"Created directory: {path}")

    @staticmethod
    def to_snake_case(name):
        name = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
        name = re.sub("([a-z0-9])([A-Z])", r"\1_\2", name)
        name = re.sub(r"[^0-9a-zA-Z]+", "_", name)
        return name.lower().strip("_")

    def is_simple_scalar(self, val):
        return np.isscalar(val) or isinstance(val, str | bytes)

    def array_is_scalar(self, arr):
        # True if array has one unique value
        try:
            arr_flat = np.asarray(arr).flatten()
            return arr_flat.size == 1 or np.all(arr_flat == arr_flat[0])
        except Exception:
            return False

    def matrix_is_forecasting(self, df: pl.DataFrame):
        # If any column can be parsed as a datetime, treat as forecasting_matrix
        for col in df.columns:
            try:
                parsed = pl.Series(df[col]).str.strptime(pl.Datetime, strict=False)
                if (~parsed.is_null()).sum() > 0:
                    return True
            except Exception:
                continue
        return False

    def process(self):
        logger.info("Starting the parsing process.")
        with h5py.File(self.hdf5_path, "r") as f:
            object_types = list(f.keys())
            logger.info(f"Found object types: {object_types}")

            # Prepare output directories (snake_case)
            objects_dir = os.path.join(self.root_input_directory, "objects")
            self.ensure_dir(objects_dir)

            for object_type in object_types:
                object_type_snake = self.to_snake_case(object_type)
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
                    self.ensure_dir(os.path.join(self.root_input_directory, matrix_type, object_type_snake))

                for instance in instances:
                    instance_snake = self.to_snake_case(instance)
                    logger.info(f"Processing instance: {instance} (as {instance_snake})")
                    instance_group = group[instance]
                    attrs = {"name": instance_snake}

                    for attr_name in instance_group:
                        attr_name_snake = self.to_snake_case(attr_name)
                        if attr_name_snake in NAME_MAPPING:
                            attr_name_snake = NAME_MAPPING[attr_name_snake]
                        item = instance_group[attr_name]
                        logger.debug(
                            f"Processing attribute: {attr_name} (as {attr_name_snake}) for instance {instance_snake}"
                        )

                        if isinstance(item, h5py.Dataset):
                            val = item[()]
                            # Improved scalar/array logic
                            if self.is_simple_scalar(val) or self.array_is_scalar(val):
                                attrs[attr_name_snake] = (
                                    val.item() if hasattr(val, "item") and np.size(val) == 1 else val
                                )
                                if isinstance(attrs[attr_name_snake], bytes):
                                    attrs[attr_name_snake] = attrs[attr_name_snake].decode("utf-8")
                                if attrs[attr_name_snake] == "None":
                                    attrs[attr_name_snake] = None
                                if attrs[attr_name_snake] == "":
                                    attrs[attr_name_snake] = None
                                if attrs[attr_name_snake] in NAME_MAPPING:
                                    attrs[attr_name_snake] = NAME_MAPPING[attrs[attr_name_snake]]
                                if attr_name_snake == "equipment":
                                    attrs[attr_name_snake] = self.to_snake_case(attrs[attr_name_snake])
                                logger.debug(f"Scalar attribute: {attr_name_snake} = {attrs[attr_name_snake]}")
                            elif isinstance(val, np.ndarray):
                                if val.ndim == 1:
                                    if isinstance(list(val)[0], bytes):
                                        val = [v.decode("utf-8") for v in val]
                                    if attr_name_snake == "orders":
                                        val = [self.to_snake_case(order) for order in val]
                                    attrs[attr_name_snake] = ":".join(map(str, list(val)))
                                elif val.ndim == 2:
                                    df = pl.DataFrame({attr_name_snake: val})
                                    df = df.with_columns(pl.lit(attr_name_snake).alias("attribute"))
                                    df = df.rename({col: self.to_snake_case(col) for col in df.columns})
                                    out_path = os.path.join(
                                        self.root_input_directory,
                                        "timeseries",
                                        object_type_snake,
                                        f"{instance_snake}.parquet",
                                    )
                                    df.write_parquet(out_path)
                                    logger.debug(
                                        f"Wrote 1D timeseries for {attr_name_snake} of {instance_snake} to {out_path}"
                                    )
                                    attrs[attr_name_snake] = "timeseries"
                                elif val.ndim == 2:
                                    df = pl.DataFrame(val)
                                    df = df.with_columns(pl.lit(attr_name_snake).alias("attribute"))
                                    df = df.rename({col: self.to_snake_case(col) for col in df.columns})
                                    ts_type = "scenario_matrix"
                                    if self.matrix_is_forecasting(df):
                                        ts_type = "forecasting_matrix"
                                    out_path = os.path.join(
                                        self.root_input_directory,
                                        ts_type,
                                        object_type_snake,
                                        f"{instance_snake}.parquet",
                                    )
                                    df.write_parquet(out_path)
                                    logger.info(
                                        f"Wrote 2D {ts_type} for {attr_name_snake} of {instance_snake} to {out_path}"
                                    )
                                    attrs[attr_name_snake] = ts_type
                                else:
                                    df = pl.DataFrame(val.reshape(val.shape[0], -1))
                                    df = df.with_columns(pl.lit(attr_name_snake).alias("attribute"))
                                    df = df.rename({col: self.to_snake_case(col) for col in df.columns})
                                    ts_type = "forecasting_matrix"
                                    out_path = os.path.join(
                                        self.root_input_directory,
                                        ts_type,
                                        object_type_snake,
                                        f"{instance_snake}.parquet",
                                    )
                                    df.write_parquet(out_path)
                                    logger.debug(
                                        f"Wrote >2D forecasting_matrix for {attr_name_snake} of {instance_snake} to {out_path}"
                                    )
                                    attrs[attr_name_snake] = ts_type
                            else:
                                attrs[attr_name_snake] = str(item)
                                logger.warning(f"Unhandled attribute: {attr_name_snake} (type: {type(item)})")
                    # Attributes defined at the instance level
                    for attr_name, attr_value in instance_group.attrs.items():
                        attr_name_snake = self.to_snake_case(attr_name)
                        attrs[attr_name_snake] = attr_value
                        logger.info(f"Instance-level attribute: {attr_name_snake} = {attr_value}")
                    attrs_list.append(attrs)

                # Write CSV for this object_type using Polars
                if attrs_list:
                    df_attrs = pl.DataFrame(attrs_list)
                    df_attrs = df_attrs.rename({col: self.to_snake_case(col) for col in df_attrs.columns})
                    csv_path = os.path.join(objects_dir, f"{object_type_snake}.csv")
                    df_attrs.write_csv(csv_path, separator=";")
                    logger.success(f"Wrote attributes CSV for {object_type_snake} to {csv_path}")
