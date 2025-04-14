from pathlib import Path

import polars as pl


class InputParser:
    """A class to handle input parsing from various sources such as
    files, command-line arguments, or raw strings.
    """

    def __init__(self, source: str | Path = None):
        """Initialize the InputParser.

        Parameters
        ----------
        - source (str or Path): The input source (optional).

        """
        self.source = source

    def from_csv(self, file_path: str | Path) -> pl.DataFrame:
        """Parse input from a CSV file.

        Parameters
        ----------
        - file_path (str): The path to the CSV file.

        """
        return pl.read_csv(file_path)

    def from_parquet(self, file_path: str | Path) -> pl.DataFrame:
        """Parse input from a Parquet file.

        Parameters
        ----------
        - file_path (str): The path to the Parquet file.

        """
        return pl.read_parquet(file_path)
