from pathlib import Path

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
