from pathlib import Path
from typing import Literal

from pydantic import BaseModel, model_validator
from pydantic_extra_types.timezone_name import TimeZoneName

import atlas.config as cfg
from atlas.custom_errors import DataValidationError, DirectoryStructureError
from atlas.validators import DateFormat


class _IOConfig(BaseModel):
    """Shared configuration fields for reading and writing an ATLAS dataset directory."""

    directory_path: Path
    separator: str = ";"
    timeseries_file_extension: Literal["csv", "parquet", "pickle"] = "parquet"
    matrix_file_extension: Literal["csv", "parquet", "pickle"] = "parquet"
    lazy: bool = False
    timezone: TimeZoneName = TimeZoneName("UTC")
    date_format_forecasting_matrix: DateFormat = "YYYY-MM-DD HH:mm:ss"
    date_format_input_files: DateFormat = "YYYY-MM-DD HH:mm:ss"


class InputLoaderConfig(_IOConfig):
    """Pydantic model for AtlasDataset configuration validation."""

    @model_validator(mode="after")
    def validate_directory_structure(self) -> "InputLoaderConfig":
        if not self.directory_path.exists():
            raise DirectoryStructureError(f"Directory does not exist: {self.directory_path}")

        if not self.directory_path.is_dir():
            raise DirectoryStructureError(f"Path is not a directory: {self.directory_path}")

        objects_dir = self.directory_path / "objects"
        if not objects_dir.exists():
            raise DirectoryStructureError(
                f"Required 'objects' subdirectory not found in: {self.directory_path}. "
                f"Expected structure: {self.directory_path}/objects/"
            )

        if not objects_dir.is_dir():
            raise DirectoryStructureError(f"'objects' path is not a directory: {objects_dir}")

        return self

    @model_validator(mode="after")
    def validate_object_dir(self) -> "InputLoaderConfig":
        """Validate that all object types are recognized."""

        objects_dir = self.directory_path / "objects"
        objects = [f for f in objects_dir.iterdir() if f.is_file()]
        invalid_elements = [x for x in objects if x.stem not in cfg.MODEL_MAPPING_NAME]

        if any(x for x in objects if x.suffix != ".csv"):
            raise DataValidationError(
                f"All files in the 'objects' directory must be CSV files. "
                f"Found non-CSV files: {[x.name for x in objects if x.suffix != '.csv']}"
            )

        if invalid_elements:
            available_types = list(cfg.MODEL_MAPPING_NAME.keys())
            raise DataValidationError(
                f"Object type(s) {invalid_elements} are not recognized. "
                f"Available types are: {available_types}. "
                f"Please ensure your CSV files in the 'objects' directory are named correctly."
            )

        return self


class OutputGeneratorConfig(_IOConfig):
    """Pydantic model for OutputGenerator configuration validation."""
