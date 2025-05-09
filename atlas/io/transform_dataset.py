import csv
import json
import os
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import h5py
import numpy as np
import polars as pl

from atlas.config import logger


class AtlasTransformerDataset:
    """Transforms the original energy data directory structure to the target format."""

    def __init__(self, source_root, target_root):
        """
        Initialize the transformer.

        Args:
            source_root: Path to the source directory containing the original structure
            target_root: Path to the target directory where the new structure will be created
            intermediate_path: Path to the intermediate directory for temporary files (optional)
        """
        self.source_root = Path(source_root)
        self.target_root = Path(target_root)

        # Create the main directories in the target structure
        self.data_dir = self.target_root / "objects"
        self.timeseries_dir = self.target_root / "timeseries"
        self.scenario_matrix_dir = self.target_root / "scenario_matrix"
        self.forecasting_matrix_dir = self.target_root / "forecasting_matrix"

        # Create directories if they don't exist
        for directory in [
            self.data_dir,
            self.timeseries_dir,
            self.scenario_matrix_dir,
            self.forecasting_matrix_dir,
        ]:
            os.makedirs(directory, exist_ok=True)

        # Store instance data for creating the final CSV files
        self.instances_data = {}

    def explore_hdf5(self, hdf_file, output_dir):
        """
        Recursively explore HDF5 file and recreate structure while converting datasets to CSV

        Args:
            hdf_file: The HDF5 file object or group to explore
            output_dir: The directory where to save the folder structure and CSV files

        """
        # Create the output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # Explore all items in the current group
        for key in hdf_file.keys():
            item = hdf_file[key]
            path = os.path.join(output_dir, key)

            # If item is a group (folder), recursively explore it
            if isinstance(item, h5py.Group):
                self.explore_hdf5(item, path)

            # If item is a dataset, convert to Polars dataframe and save as CSV
            elif isinstance(item, h5py.Dataset):
                try:
                    # Read the dataset into a numpy array
                    data = item[()]

                    # Handle different dataset types
                    if len(item.shape) == 1:
                        # 1D array - single column
                        df = pl.DataFrame({key: data})
                    elif len(item.shape) == 2:
                        # 2D array - potentially a table with rows and columns
                        if item.dtype.kind in {"S", "O"}:
                            # String/object type - needs special handling
                            # Convert bytes to strings if necessary
                            if item.dtype.kind == "S":
                                data = np.array(
                                    [s.decode("utf-8") if isinstance(s, bytes) else s for s in data.flatten()]
                                )
                                data = data.reshape(item.shape)

                            # Try to create a dataframe based on shape
                            if item.shape[1] == 1:
                                df = pl.DataFrame({key: data.flatten()})
                            else:
                                # Multiple columns - create column names
                                columns = {f"col_{i}": data[:, i] for i in range(item.shape[1])}
                                df = pl.DataFrame(columns)
                        # Numeric data
                        elif item.shape[1] == 1:
                            df = pl.DataFrame({key: data.flatten()})
                        else:
                            # Multiple columns - create column names
                            columns = {f"col_{i}": data[:, i] for i in range(item.shape[1])}
                            df = pl.DataFrame(columns)
                    else:
                        # Higher dimensional data - flatten and save structure info
                        df = pl.DataFrame({"data": data.flatten(), "original_shape": str(item.shape)})

                    # Save to CSV
                    csv_path = f"{path}.csv"

                    df.write_csv(csv_path, separator=";")

                except Exception as e:
                    print(f"Error processing dataset {key}: {e}")

    def convert_hdf5_to_csv(self, hdf_path, output_dir):
        """
        Main function to convert HDF5 file to CSV files

        Args:
            hdf_path: Path to the HDF5 file
            output_dir: Output directory for the folder structure and CSV files

        """
        with h5py.File(hdf_path, "r") as hdf_file:
            hdf_file.visit(lambda name: print(f"- {name}"))

            self.explore_hdf5(hdf_file, output_dir)

    def is_datetime_file(self, filename):
        """Check if a filename is a datetime format."""
        name = Path(filename).stem  # Get filename without extension

        # Check if the filename matches the format DD_MM_YYYY HH:MM:SS
        pattern = r"\d{2}_\d{2}_\d{4} \d{2}:\d{2}:\d{2}"
        return bool(re.match(pattern, name))

    def convert_datetime_format(self, old_format):
        """Convert from DD_MM_YYYY HH:MM:SS to YYYY-MM-DD."""
        # Parse the old format
        dt = datetime.strptime(old_format, "%d_%m_%Y %H:%M:%S")
        # Return only the date part in the new format
        return dt.strftime("%Y-%m-%d")

    def process_source_tree(self):
        """Process the source directory tree and transform it to the target structure."""
        # Process each business type directory
        for business_type_dir in self.source_root.iterdir():
            if not business_type_dir.is_dir():
                continue

            business_type = business_type_dir.name

            # Process each instance in this business type
            for instance_dir in business_type_dir.iterdir():
                if not instance_dir.is_dir():
                    continue

                name = instance_dir.name

                # Create an entry for this instance in our data dictionary
                if name not in self.instances_data:
                    self.instances_data[self.to_snake_case(name)] = {
                        "business_type": self.to_snake_case(business_type),
                        "name": self.to_snake_case(name),
                    }

                # Process each attribute in this instance
                for attribute_dir in instance_dir.iterdir():
                    attribute_name = attribute_dir.stem

                    # Determine the attribute type
                    if attribute_dir.is_file() and attribute_dir.suffix == ".csv":
                        # This is a Timeseries
                        self._process_timeseries(business_type, name, attribute_name, attribute_dir)
                    elif attribute_dir.is_dir():
                        # Check the files inside to determine if it's a ForecastingMatrix or ScenarioMatrix
                        csv_files = list(attribute_dir.glob("*.csv"))
                        if not csv_files:
                            continue

                        if self.is_datetime_file(csv_files[0].name):
                            # This is a ForecastingMatrix
                            self._process_forecasting_matrix(business_type, name, attribute_name, attribute_dir)
                        else:
                            # This is a ScenarioMatrix
                            self._process_scenario_matrix(business_type, name, attribute_name, attribute_dir)

    def _process_timeseries(self, business_type, name, attribute_name, file_path):
        """Process a Timeseries attribute."""
        # Copy the CSV file to the timeseries directory with a meaningful name
        profile_name = f"{attribute_name}.csv"
        target_path = (
            self.timeseries_dir
            / self.to_snake_case(business_type)
            / self.to_snake_case(name)
            / f"{self.to_snake_case(attribute_name)}.parquet"
        )
        os.makedirs(target_path.parent, exist_ok=True)

        # Copy the file
        logger.info(f"Processing Timeseries for {name} {attribute_name}")
        pl.read_csv(file_path).with_columns(pl.from_epoch(pl.nth(0), time_unit="ns")).rename(
            {"col_0": "date", "col_1": "value"}
        ).write_parquet(target_path)

        # Update the instance data
        self.instances_data[self.to_snake_case(name)][self.to_snake_case(attribute_name)] = "timeseries"

    def _process_forecasting_matrix(self, business_type, name, attribute_name, dir_path):
        """Process a ForecastingMatrix attribute."""
        # Create a directory for this matrix in the forecasting_matrix directory
        matrix_dir = self.forecasting_matrix_dir / self.to_snake_case(business_type) / self.to_snake_case(name)
        os.makedirs(matrix_dir, exist_ok=True)

        logger.info(f"Processing ForecastingMatrix for {name} {attribute_name}")
        # Process each CSV file in the directory
        for csv_file in dir_path.glob("*.csv"):
            if not self.is_datetime_file(csv_file.name):
                continue

            # Convert the old datetime format to the new one
            date_name = csv_file.stem  # Get filename without extension

            # Read the CSV file with polars
            df = pl.read_csv(csv_file)

            # Try to convert the first column to datetime if it's numeric
            try:
                df = df.with_columns(pl.from_epoch(pl.nth(0), time_unit="ns")).rename(
                    {"col_0": "date", "col_1": f"{date_name}"}
                )
            except Exception:
                print(f"Error converting column {df.columns[0]} to datetime")

            # Convert to parquet and save
            parquet_path = matrix_dir / self.to_snake_case(attribute_name) / f"{date_name}.parquet"
            os.makedirs(parquet_path.parent, exist_ok=True)
            df.write_parquet(parquet_path)

            self.instances_data[self.to_snake_case(name)][self.to_snake_case(attribute_name)] = "forecasting_matrix"
        self.merge_matrices(matrix_dir / self.to_snake_case(attribute_name), self.to_snake_case(attribute_name))


    def _process_scenario_matrix(self, business_type, name, attribute_name, dir_path):
        """Process a ScenarioMatrix attribute."""
        # Create a directory for this matrix in the scenario_matrix directory
        matrix_dir = self.scenario_matrix_dir / self.to_snake_case(business_type) / self.to_snake_case(name)
        os.makedirs(matrix_dir, exist_ok=True)

        # Process each CSV file in the directory
        scenarios = []

        logger.info(f"Processing ScenarioMatrix for {name} {attribute_name}")
        for i, csv_file in enumerate(dir_path.glob("*.csv"), 1):
            # Create a scenario name
            scenario_name = f"scenario_{i:03d}"
            scenarios.append(scenario_name)

            # Read the CSV file with polars
            df = pl.read_csv(csv_file)

            try:
                df = df.with_columns(pl.from_epoch(pl.nth(0), time_unit="ns")).rename(
                    {"col_0": "date", "col_1": f"{scenario_name}"}
                )
            except Exception:
                print(f"Error converting column {df.columns[0]} to datetime")

            parquet_path = matrix_dir / self.to_snake_case(attribute_name) / f"{scenario_name}.parquet"
            os.makedirs(parquet_path.parent, exist_ok=True)
            df.write_parquet(parquet_path)

        self.instances_data[self.to_snake_case(name)][self.to_snake_case(attribute_name)] = "scenario_matrix"
        self.merge_matrices(matrix_dir / self.to_snake_case(attribute_name), self.to_snake_case(attribute_name))


    def merge_matrices(self, base_path, attribute_name):
        parquet_files = sorted(base_path.glob("*.parquet"))
        dfs = [pl.read_parquet(f) for f in parquet_files]
        logger.info(f"Found {len(parquet_files)} files to merge in path: {base_path}")
        df_merged = None

        if len(parquet_files) > 1:
            for i, file in enumerate(parquet_files):
                df = pl.read_parquet(file)

                if df_merged is None:
                    df_merged = df
                else:
                    # Perform a full outer join with coalescing on 'date'
                    df_merged = df_merged.join(df, on="date", how="full", coalesce=True)
        else:
            df_merged = pl.read_parquet(parquet_files[0])

        # Save the final merged DataFrame
        merged_file_path = base_path / f"{attribute_name}.parquet"
        df_merged.write_parquet(merged_file_path)
        logger.info(f"Merged file: {merged_file_path}")
        # Remove original files (except the merged one)
        for file in parquet_files:
            if file != merged_file_path:
                file.unlink()


    def merge_parquet_files_recursive(self,path: str) -> pl.DataFrame:
        path = Path(path)
        parquet_files = list(path.rglob("*.parquet"))
        if not parquet_files:
            raise ValueError("No parquet files found.")

        df = pl.DataFrame()
        if "timeseries" in str(path):
            idx_instance = 0
            idx_type = 1
        else:
            idx_instance = 1
            idx_type = 2
        for f in parquet_files:
            attribute = f.stem
            instance = f.parents[idx_instance].stem

            type = f.parents[idx_type].stem
            next_df = (
                pl.read_parquet(f)
                .with_columns(
                    pl.lit(attribute).alias("attribute"),
                )
                .select(pl.selectors.datetime(), pl.selectors.string(), pl.selectors.numeric())
            )
            df = pl.concat([df, next_df], how="diagonal")
        logger.info(f"File to write {path.parent /type/ f'{instance}.parquet'}")

        df.write_parquet(path.parent /f"{instance}.parquet")
        shutil.rmtree(path.parent / instance)
        logger.info(f"Removed path {path.parent / instance}")
        return df

    def flatten_attributes_with_filter(self, instance_name, instance_dict):
        """
        Flatten attributes:
        - Use snake_case for attribute names
        - If a value is a dict with 'object' and non-empty 'timeseries', store the object value
        - Use instance name only if 'name' attribute is not present
        """
        flat = {}
        has_name = "name" in instance_dict

        for attr, value in instance_dict.items():
            snake_attr = self.to_snake_case(attr)
            if isinstance(value, dict):
                if "object" in value:
                    ts = value.get("timeseries")
                    if ts not in (None, {}, []):
                        flat[snake_attr] = value["object"]
            else:
                flat[snake_attr] = value

        if not has_name:
            flat["name"] = instance_name  # fallback if 'name' not present
        return flat

    def from_objects_json_to_csv_files(self, objects_json_file):
        # Load filtered_data
        with open(objects_json_file, "r") as f:
            filtered_data = json.load(f)

        # Traverse structure
        namespaces = filtered_data.get("Namespaces", {})
        for ns_name, ns_content in namespaces.items():
            classes = ns_content.get("Classes", {})
            for class_name, class_content in classes.items():
                instances = class_content.get("Instances", {})

                rows = []
                all_attrs = set()

                for inst_name, inst_data in instances.items():
                    flat = self.flatten_attributes_with_filter(inst_name, inst_data)
                    if "object" in flat:
                        del flat["object"]
                    if "comment" in flat:
                        del flat["comment"]
                    flat['name'] = self.to_snake_case(flat['name'])
                    rows.append(flat)
                    all_attrs.update(flat.keys())

                # Determine first column
                first_col = "name" if any("name" in row for row in rows) else None
                fieldnames = [first_col] if first_col else []
                fieldnames += sorted(attr for attr in all_attrs if attr != first_col)

                # Write to CSV
                csv_file = self.data_dir / f"{self.to_snake_case(class_name)}.csv"
                if instances == {}:
                    continue
                with open(csv_file, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
                    writer.writeheader()
                    writer.writerows(rows)

    @staticmethod
    def to_snake_case(name: str) -> str:
        """Convert a given string from camel case or kebab case to snake case."""
        # Replace hyphens with underscores
        name = name.replace("-", "_")
        # Insert underscore before any capital letter that follows a lowercase letter or number
        name = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
        # Insert underscore between sequences of capitals followed by lowercase letters
        name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
        # Convert everything to lowercase
        return name.lower()

    def transform(self, objects_json_path):
        """Main method to perform the complete transformation."""
        # self.process_source_tree()

        for folders in Path(self.target_root).iterdir():
            if 'timeseries' in str(folders) or 'forecasting' in str(folders) or 'scenario' in str(folders):
                for path in folders.iterdir():
                    for instance in path.iterdir():
                        self.merge_parquet_files_recursive(instance)

        self.from_objects_json_to_csv_files(objects_json_path)

        return self.target_root

    def run(self, hdf_path, objects_json_path):
        """Run the transformation process."""
        self.convert_hdf5_to_csv(hdf_path=hdf_path, output_dir=self.source_root)
        self.transform(objects_json_path)
        print(f"Transformation complete. Output directory: {self.target_root}")
