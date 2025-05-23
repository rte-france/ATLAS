from pathlib import Path
from typing import Any

import pandas as pd
import pendulum
import polars as pl


def read_data_file(
    file_path: str | Path,
    filters: tuple[str, str] | None = None,
    separator: str = ";",
) -> pl.DataFrame:
    """Read a dataframe from csv or parquet"""
    if isinstance(file_path, str):
        file_path = Path(file_path)
    if file_path.suffix == ".csv":
        df = pl.read_csv(file_path, separator=separator, try_parse_dates=True)
    elif file_path.suffix == ".parquet":
        df = pl.read_parquet(file_path)
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
