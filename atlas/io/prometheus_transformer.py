import re
from pathlib import Path

import h5py
import numpy as np
import polars as pl


class HDF5Parser:
    """Parser for HDF5 files to create a structured output directory."""

    def __init__(self, hdf5_file_path: str, output_directory: str, file_extension: str = ".parquet"):
        """
        Initialize the HDF5 parser.

        Args:
            hdf5_file_path: Path to the HDF5 file to parse
            output_directory: Directory where the parsed data will be stored
            file_extension: File extension for the output files (default: .parquet)
        """
        self.hdf5_file_path = hdf5_file_path
        self.output_directory = Path(output_directory)
        self.file_extension = file_extension

        # Create the main output directory structure
        self.objects_dir = self.output_directory / "objects"
        self.timeseries_dir = self.output_directory / "timeseries"
        self.scenario_matrix_dir = self.output_directory / "scenario_matrix"
        self.forecasting_matrix_dir = self.output_directory / "forecasting_matrix"

        self._create_directory_structure()

    def _create_directory_structure(self):
        """Create the required directory structure."""
        directories = [
            self.objects_dir,
            self.timeseries_dir,
            self.scenario_matrix_dir,
            self.forecasting_matrix_dir,
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def _to_snake_case(self, name: str) -> str:
        """
        Convert a string to snake_case.

        Args:
            name: The string to convert

        Returns:
            The string in snake_case
        """
        # Replace spaces, dashes, and dots with underscores
        s1 = re.sub(r"[\s\-\.]", "_", name)
        # Insert underscore before capital letters and convert to lowercase
        s2 = re.sub(r"([A-Z])", r"_\1", s1).lower()
        # Remove consecutive underscores and leading/trailing underscores
        s3 = re.sub(r"_+", "_", s2).strip("_")
        return s3

    def parse(self):
        """Parse the HDF5 file and create the output structure."""
        with h5py.File(self.hdf5_file_path, "r") as hdf_file:
            # First, identify all object types in the HDF5 file
            object_types = self._identify_object_types(hdf_file)

            # Process each object type
            for obj_type in object_types:
                # Convert object type to snake_case for output
                snake_obj_type = self._to_snake_case(obj_type)

                # Extract and save object metadata
                objects_df = self._extract_objects(hdf_file, obj_type)
                if objects_df is not None and len(objects_df) > 0:
                    self._save_objects(objects_df, snake_obj_type)

                # Create subdirectories for matrices
                (self.timeseries_dir / snake_obj_type).mkdir(exist_ok=True)
                (self.scenario_matrix_dir / snake_obj_type).mkdir(exist_ok=True)
                (self.forecasting_matrix_dir / snake_obj_type).mkdir(exist_ok=True)

                # Extract and save timeseries, scenario matrices, and forecasting matrices
                self._process_matrices(hdf_file, obj_type, snake_obj_type)

    def _identify_object_types(self, hdf_file) -> list[str]:
        """
        Identify all object types in the HDF5 file.

        Args:
            hdf_file: Open HDF5 file object

        Returns:
            List of object types
        """
        object_types = []

        # This logic will depend on the structure of your HDF5 file
        # Here's a simple approach that assumes top-level groups represent object types
        for key in hdf_file.keys():
            if isinstance(hdf_file[key], h5py.Group):
                object_types.append(key)

        return object_types

    def _extract_objects(self, hdf_file, obj_type: str) -> pl.DataFrame | None:
        """
        Extract object metadata for a specific object type.

        Args:
            hdf_file: Open HDF5 file object
            obj_type: The object type to extract

        Returns:
            Polars DataFrame with object metadata, or None if not available
        """
        try:
            obj_group = hdf_file[obj_type]

            # Each key in obj_group is an instance of the object type
            instance_ids = list(obj_group.keys())

            # Skip reserved directories
            instance_ids = [
                id
                for id in instance_ids
                if id not in ("timeseries", "scenario_matrix", "forecasting_matrix", "metadata")
            ]

            if not instance_ids:
                return None

            # Collect all attribute names across all instances
            all_attributes = set()
            for instance_id in instance_ids:
                instance = obj_group[instance_id]

                # Add all attribute names from this instance
                if isinstance(instance, h5py.Group):
                    all_attributes.update(instance.keys())

            # Convert attribute names to snake_case
            attr_mapping = {attr: self._to_snake_case(attr) for attr in all_attributes}

            # Prepare data structure for the DataFrame
            rows = []

            # Process each instance
            for instance_id in instance_ids:
                instance = obj_group[instance_id]

                if isinstance(instance, h5py.Group):
                    # Create a row for this instance
                    row = {"id": instance_id}

                    # Initialize all attributes to None
                    for orig_attr, snake_attr in attr_mapping.items():
                        row[snake_attr] = None

                    # Process each attribute in this instance
                    for attr_name in instance.keys():
                        # Get the snake_case version of the attribute name
                        snake_attr = attr_mapping.get(attr_name, self._to_snake_case(attr_name))

                        # Get the attribute dataset
                        attr_dataset = instance[attr_name]

                        if isinstance(attr_dataset, h5py.Dataset):
                            # Get the attribute value
                            value = attr_dataset[()]

                            # Process based on data shape
                            if isinstance(value, np.ndarray):
                                if len(value.shape) == 2 and value.shape[1] == 2:
                                    # Array with 2 columns - datetime
                                    row[snake_attr] = "datetime_array"
                                elif len(value.shape) >= 2:
                                    # Other multi-dimensional array - matrix
                                    row[snake_attr] = "matrix"
                                else:
                                    # 1D array - might be a simple list or array
                                    # If it's a small array, include the value
                                    if len(value) <= 10:  # Arbitrary limit to avoid huge values
                                        row[snake_attr] = value.tolist()
                                    else:
                                        row[snake_attr] = "array"
                            else:
                                # Scalar value
                                row[snake_attr] = value

                    rows.append(row)

            # Create DataFrame from collected rows
            if rows:
                return pl.DataFrame(rows)

            return None

        except (KeyError, Exception) as e:
            print(f"Error extracting objects for {obj_type}: {e}")
            return None

    def _save_objects(self, df: pl.DataFrame, obj_type: str):
        """
        Save object metadata to a CSV file.

        Args:
            df: Polars DataFrame with object metadata
            obj_type: The object type
        """
        output_path = self.objects_dir / f"{obj_type}.csv"
        df.write_csv(output_path)

    def _process_matrices(self, hdf_file, obj_type: str, output_obj_type: str):
        """
        Process and save timeseries, scenario matrices, and forecasting matrices.

        Args:
            hdf_file: Open HDF5 file object
            obj_type: The original object type to process from HDF5
            output_obj_type: The snake_case version of object type for output
        """
        obj_group = hdf_file.get(obj_type)
        if obj_group is None:
            return

        # Create subdirectories for matrices if they don't exist
        (self.timeseries_dir / output_obj_type).mkdir(exist_ok=True)
        (self.scenario_matrix_dir / output_obj_type).mkdir(exist_ok=True)
        (self.forecasting_matrix_dir / output_obj_type).mkdir(exist_ok=True)

        # Each instance of the object type
        instance_ids = list(obj_group.keys())

        # Skip reserved directories if they exist
        instance_ids = [id for id in instance_ids if id not in ("metadata",)]

        for instance_id in instance_ids:
            instance = obj_group[instance_id]

            # Skip if not a group
            if not isinstance(instance, h5py.Group):
                continue

            # Convert instance ID to snake_case for output filenames
            snake_instance_id = self._to_snake_case(instance_id)

            # Process timeseries if they exist
            if "timeseries" in instance:
                self._extract_and_save_matrix_data(
                    instance, "timeseries", snake_instance_id, output_obj_type, self.timeseries_dir
                )

            # Process scenario matrices if they exist
            if "scenario_matrix" in instance:
                self._extract_and_save_matrix_data(
                    instance,
                    "scenario_matrix",
                    snake_instance_id,
                    output_obj_type,
                    self.scenario_matrix_dir,
                )

            # Process forecasting matrices if they exist
            if "forecasting_matrix" in instance:
                self._extract_and_save_matrix_data(
                    instance,
                    "forecasting_matrix",
                    snake_instance_id,
                    output_obj_type,
                    self.forecasting_matrix_dir,
                )

    def _extract_and_save_matrix_data(
        self, instance, matrix_type: str, instance_id: str, obj_type: str, output_dir: Path
    ):
        """
        Extract and save matrix data from the HDF5 file to the appropriate format.

        Args:
            instance: HDF5 group representing an instance of object type
            matrix_type: Type of matrix ('timeseries', 'scenario_matrix', or 'forecasting_matrix')
            instance_id: Instance identifier (already in snake_case)
            obj_type: Type of the object (already in snake_case)
            output_dir: Base directory for output
        """
        matrix_group = instance[matrix_type]

        # Create a list to hold all dataframes
        all_dfs = []

        # Process each attribute in the matrix group
        for attr_name in matrix_group.keys():
            attr_data = matrix_group[attr_name]

            if isinstance(attr_data, h5py.Dataset):
                # Convert attribute name to snake_case
                snake_attr_name = self._to_snake_case(attr_name)

                # Extract the data
                data_array = attr_data[()]

                # Create the dataframe based on data dimensionality
                df = self._create_dataframe_from_data(data_array, snake_attr_name, matrix_type)

                if df is not None:
                    all_dfs.append(df)

        # Combine all dataframes if we have any
        if all_dfs:
            combined_df = pl.concat(all_dfs)

            # Save the combined dataframe
            output_subdir = output_dir / obj_type
            output_path = output_subdir / f"{instance_id}{self.file_extension}"

            if self.file_extension.lower() == ".parquet":
                combined_df.write_parquet(output_path)
            elif self.file_extension.lower() == ".csv":
                combined_df.write_csv(output_path)
            else:
                # Default to parquet
                combined_df.write_parquet(output_path.with_suffix(".parquet"))

    def _create_dataframe_from_data(
        self, data_array: np.ndarray, attr_name: str, data_type: str
    ) -> pl.DataFrame | None:
        """
        Create a Polars DataFrame from numpy array data with snake_case column names.

        Args:
            data_array: Numpy array with data
            attr_name: Name of the attribute (already in snake_case)
            data_type: Type of data ('timeseries', 'scenario_matrix', or 'forecasting_matrix')

        Returns:
            Polars DataFrame with the data, including an 'attribute' column
        """
        # Handle different data dimensions
        if len(data_array.shape) == 1:
            # 1D array - simple timeseries
            df = pl.DataFrame({"value": data_array, "attribute": [attr_name] * len(data_array)})

            # Add index as timestamp or appropriate identifier
            df = df.with_columns(pl.Series("timestamp", list(range(len(data_array)))))

            return df

        elif len(data_array.shape) == 2:
            # 2D array - matrix
            rows, cols = data_array.shape

            # Create a flat list of values
            values = data_array.flatten()

            # Create corresponding indices
            if data_type == "scenario_matrix":
                # For scenario matrices, use scenario and timestamp
                scenarios = np.repeat(np.arange(rows), cols)
                timestamps = np.tile(np.arange(cols), rows)

                df = pl.DataFrame(
                    {
                        "value": values,
                        "scenario": scenarios,
                        "timestamp": timestamps,
                        "attribute": [attr_name] * len(values),
                    }
                )

            elif data_type == "forecasting_matrix":
                # For forecasting matrices, use forecast_time and lead_time
                forecast_times = np.repeat(np.arange(rows), cols)
                lead_times = np.tile(np.arange(cols), rows)

                df = pl.DataFrame(
                    {
                        "value": values,
                        "forecast_time": forecast_times,
                        "lead_time": lead_times,
                        "attribute": [attr_name] * len(values),
                    }
                )

            else:  # Default case - timeseries
                # Use row and column indices
                row_indices = np.repeat(np.arange(rows), cols)
                col_indices = np.tile(np.arange(cols), rows)

                df = pl.DataFrame(
                    {
                        "value": values,
                        "row_index": row_indices,
                        "col_index": col_indices,
                        "attribute": [attr_name] * len(values),
                    }
                )

            return df

        elif len(data_array.shape) >= 3:
            # 3D+ arrays - more complex case
            # Flatten the array and create appropriate indices
            flat_data = data_array.flatten()

            # Create a dictionary to hold the DataFrame columns
            data_dict = {"value": flat_data, "attribute": [attr_name] * len(flat_data)}

            # Create dimension indices
            shape = data_array.shape
            indices = np.indices(shape)

            # Add each dimension as a separate column
            for i, dim_size in enumerate(shape):
                dim_indices = indices[i].flatten()
                data_dict[f"dim_{i}"] = dim_indices

            return pl.DataFrame(data_dict)

        return None


def parse_hdf5(hdf5_file_path: str, output_directory: str, file_extension: str = ".parquet"):
    """
    Parse an HDF5 file and create the specified directory structure.

    Args:
        hdf5_file_path: Path to the HDF5 file
        output_directory: Directory to save the parsed data
        file_extension: File extension for the output files (default: .parquet)
    """
    parser = HDF5Parser(hdf5_file_path, output_directory, file_extension)
    parser.parse()
    print(f"Parsing complete. Results saved to {output_directory}")
