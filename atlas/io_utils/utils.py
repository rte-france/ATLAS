"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

"""

import copy
import re
from pathlib import Path
from typing import Any

import pandas as pd
import pendulum
import polars as pl

from atlas.math.abstract_scenario_matrix import AbstractScenarioMatrix
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.objects.business_model import BusinessModel


def read_data_file(
    file_path: str | Path,
    filters: tuple[str, str] | None = None,
    separator: str = ";",
    use_lazy: bool = True,
) -> pl.DataFrame:
    """Read a dataframe from csv or parquet with optional lazy scanning for better performance"""
    if isinstance(file_path, str):
        file_path = Path(file_path)

    # Use lazy scanning when filters are applied for better performance
    if filters and use_lazy:
        if file_path.suffix == ".csv":
            df = pl.scan_csv(file_path, separator=separator, try_parse_dates=True)
        elif file_path.suffix == ".parquet":
            df = pl.scan_parquet(file_path)
        else:
            raise NotImplementedError("Atlas file should be a csv or parquet.")

        # Apply filter lazily and collect
        df = df.filter(pl.col(f"{filters[0]}") == filters[1]).drop(filters[0])
        return df.collect()

    else:
        if file_path.suffix == ".csv":
            df_eager = pl.read_csv(file_path, separator=separator, try_parse_dates=True)
        elif file_path.suffix == ".parquet":
            df_eager = pl.read_parquet(file_path)
        else:
            raise NotImplementedError("Atlas file should be a csv or parquet.")

        if filters:
            df_eager = df_eager.filter(pl.col(f"{filters[0]}") == filters[1]).drop(filters[0])

        return df_eager


def scan_data_file(
    file_path: str | Path,
    filters: tuple[str, str] | None = None,
    separator: str = ";",
):
    """Scan a dataframe from csv or parquet"""
    if isinstance(file_path, str):
        file_path = Path(file_path)
    if file_path.suffix == ".csv":
        df = pl.scan_csv(file_path, separator=separator, try_parse_dates=True)
    elif file_path.suffix == ".parquet":
        df = pl.scan_parquet(file_path)
    else:
        raise NotImplementedError("Atlas file should be a csv or parquet.")
    if filters:
        df = df.filter(pl.col(f"{filters[0]}") == filters[1]).drop(filters[0])

    return df


def get_metadata_from_frame(df: pd.DataFrame | pl.DataFrame) -> dict[str, Any]:
    """
    Get metadata about the dataframe.

    :param df: DataFrame containing the data.
    :type df: pd.DataFrame | pl.DataFrame
    :return: A dictionnary containing dataframe metadata
    :rtype: dict[str, Any]
    """
    if isinstance(df, pd.DataFrame):
        df = pl.DataFrame(df)
    elif isinstance(df, pl.DataFrame):
        pass
    else:
        raise NotImplementedError("Can't parse input data. Provide a dataframe or a Timeseries")

    summary = {
        "shape": df.shape,
        "memory_mb": f"{df.estimated_size('mb'):.02f}",
    }

    datetime_cols = df.select(pl.selectors.datetime() | pl.selectors.date()).columns
    string_cols = df.select(pl.selectors.string()).columns
    numeric_cols = df.select(pl.selectors.numeric()).columns

    if len(datetime_cols) == 1:
        dt_col = datetime_cols[0]
        dt_series = df[dt_col]
        summary["datetime"] = {  # type: ignore[assignment]
            "column": dt_col,
            "min": pendulum.instance(dt_series.min()).to_datetime_string(),  # type: ignore[attr-defined, arg-type]
            "max": pendulum.instance(dt_series.max()).to_datetime_string(),  # type: ignore[attr-defined, arg-type]
            "nulls": dt_series.null_count(),
        }
    else:
        raise ValueError("Expected one datetime column exactly")

    if len(string_cols) == 1:
        cat_col = string_cols[0]
        cat_series = df[cat_col]
        categories = sorted(cat_series.unique().to_list())
        summary["categorical"] = {  # type: ignore[assignment]
            "column": cat_col,
            "categories": categories,
            "nulls": cat_series.null_count(),
        }

    if len(numeric_cols) == 1:
        num_col = numeric_cols[0]
        num_series = df[num_col]
        summary["numerical"] = {  # type: ignore[assignment]
            "column": num_col,
            "nulls": num_series.null_count(),
            "min": num_series.min(),
            "max": num_series.max(),
        }
    else:
        summary["numericals"] = numeric_cols

    return summary


def get_metadata_from_file(
    file_path: str | Path,
    separator: str = ";",
    filters: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """
    Get metadata about the dataframe.

    :param file_path: Path to the file.
    :type file_path: str | Path
    :param filters: Filters to apply to the dataframe.
    :type filters: tuple[str, str] | None
    :param separator: Separator used in the csv file.
    :type separator: str
    :return: A dictionnary containing dataframe metadata
    :rtype: dict[str, Any]
    """
    df = read_data_file(file_path, separator=separator, filters=filters)
    return get_metadata_from_frame(df)


def to_snake_case(name: str) -> str:
    name = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    name = re.sub("([a-z0-9])([A-Z])", r"\1_\2", name)
    name = re.sub(r"[^0-9a-zA-Z]+", "_", name)
    return name.lower().strip("_")


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
            nested_diffs = diff_business_model(val, other_val, _visited)
            if nested_diffs:
                field_diffs[field_name] = {
                    "type": "nested",
                    "object_name": val.name,
                    "diffs": nested_diffs,
                }
        elif isinstance(val, list) and isinstance(other_val, list):
            diff = diff_lists(val, other_val, _visited)
            if diff:
                field_diffs[field_name] = diff
        else:
            diff = diff_on_other_than_business_model(val, other_val, _visited)
            if diff:
                field_diffs[field_name] = diff

    return field_diffs


_TIMESERIES_DIFF_RTOL = 1e-9


def diff_on_other_than_business_model(
    val: Any, other_val: Any, _visited: set[tuple[int, int]] | None = None
) -> dict[str, Any] | None:
    if isinstance(val, list) and isinstance(other_val, list):
        return diff_lists(val, other_val, _visited)

    elif isinstance(val, str | int | float | bool):
        try:
            if val != other_val:
                return {"self": val, "other": other_val}
        except Exception:
            return {"self": str(val), "other": str(other_val)}
    elif isinstance(val, AbstractTimeseries) and isinstance(other_val, AbstractTimeseries):
        # Timeseries accumulate float ops so use tolerance rather than exact equality.
        try:
            df_val = val.dataframe
            df_other = other_val.dataframe
            joined = df_val.join(df_other, on="time", suffix="_other")
            max_diff = (joined["value"] - joined["value_other"]).abs().max() or 0.0
            ref = joined["value"].abs().max() or 1.0
            if max_diff > _TIMESERIES_DIFF_RTOL * ref or joined.height != df_val.height:
                return {"changed": "not-serializable yet"}
        except Exception:
            return {"error": "Couldn't check diff"}
    elif isinstance(val, AbstractScenarioMatrix) and isinstance(other_val, AbstractScenarioMatrix):
        # ForecastingMatrix columns accumulate float ops — use tolerance.
        # val's columns must be a subset of other_val's columns (other_val may have extra
        # historical columns from prior sessions that val doesn't have yet).
        try:
            df_val = val.dataframe
            df_other = other_val.dataframe
            val_cols = [c for c in df_val.columns if c != "time"]
            other_cols = set(df_other.columns)
            missing = [c for c in val_cols if c not in other_cols]
            if missing:
                return {"changed": "not-serializable yet"}
            for col in val_cols:
                diff = (df_val[col].fill_null(0.0) - df_other[col].fill_null(0.0)).abs()
                max_diff = diff.max() or 0.0
                ref = df_val[col].fill_null(0.0).abs().max() or 1.0
                if max_diff > _TIMESERIES_DIFF_RTOL * ref:
                    return {"changed": "not-serializable yet"}
        except Exception:
            return {"error": "Couldn't check diff"}
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
            nested_diffs = diff_business_model(a, b, _visited)
            if nested_diffs:
                diffs[str(i)] = {
                    "type": "nested",
                    "object_name": a.name,
                    "diffs": nested_diffs,
                }
        else:
            try:
                diff = diff_on_other_than_business_model(a, b, _visited)
                if diff:
                    diffs[str(i)] = diff
            except Exception:
                diffs[str(i)] = {"error": "Couldn't check diff"}
    return diffs if diffs else None


def deep_update(base: dict, updates: dict, override: bool):
    """
    Similar to function update from dictionary but works with nested dictionaries.
    If override is True, any value in dictionary base will be overwritten.
    Otherwise, all value in dictionary base will stay intact.
    """
    for key, value in updates.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            deep_update(base[key], value, override)
        elif override or key not in base:
            base[key] = copy.copy(value)
