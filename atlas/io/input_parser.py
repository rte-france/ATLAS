from pathlib import Path

import polars as pl


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
        dataframes = {}
        for file_path in Path(directory_path).iterdir():
            if file_path.is_file() and file_path.suffix in [".csv", ".parquet"]:
                df = cls.from_file(file_path)
                dataframes[file_path] = df

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

    @staticmethod
    def _from_parquet(file_path: str | Path) -> pl.DataFrame:
        """Parse input from a Parquet file.

        :param file_path: The path to the Parquet file.
        :type file_path: str or pathlib.Path
        :return: A DataFrame containing the parsed Parquet data.
        :rtype: pl.DataFrame
        """
        return pl.read_parquet(file_path)
