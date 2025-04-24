import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl


class AtlasTransformerDataset:
    """Transforms the original energy data directory structure to the target format."""

    def __init__(self, source_root, target_root):
        """
        Initialize the transformer.

        Args:
            source_root: Path to the source directory containing the original structure
            target_root: Path to the target directory where the new structure will be created

        """
        self.source_root = Path(source_root)
        self.target_root = Path(target_root)

        # Create the main directories in the target structure
        self.data_dir = self.target_root / "data"
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

    def detect_frequency(self, df):
        """
        Detect the time frequency of the DataFrame.

        Args:
            df: Polars DataFrame with a datetime column

        Returns:
            str: The detected frequency as a string (e.g., '30min', '1h')

        """
        if len(df) <= 1:
            return "1h"

        # Calculate differences between consecutive timestamps
        diff = df.with_columns(pl.nth(0).diff()).drop_nulls().select(pl.nth(0))

        if len(diff) == 0:
            return "1h"  # Default if can't determine

        most_common_diff = diff.to_pandas().value_counts().idxmax()[0]

        minutes = most_common_diff.total_seconds() / 60 if isinstance(most_common_diff, timedelta) else most_common_diff / 1e9

        # Determine frequency string
        if minutes < 1:
            return f"{int(minutes * 60)}s"
        if minutes < 60:
            return f"{int(minutes)}min"
        return f"{int(minutes / 60)}h"

    def detect_unit(self, df, attribute_name):
        """
        Detect or infer the unit of measurement based on the attribute name and data.

        Args:
            df: Polars DataFrame with value column
            attribute_name: Name of the attribute

        Returns:
            str: The inferred unit (e.g., 'MW', 'MWh', '€')

        """
        attribute_lower = attribute_name.lower()

        if any(term in attribute_lower for term in ["power", "procured", "upward", "downward"]):
            return "MW"
        if any(term in attribute_lower for term in ["energy", "volume"]):
            return "MWh"
        if any(term in attribute_lower for term in ["price", "cost"]):
            return "€/MWh"
        if any(term in attribute_lower for term in ["flow", "exchange"]):
            return "MW"

        value_col = df.select(pl.nth(1)).columns[0] if len(df.columns) > 1 else None
        if value_col is not None:
            col_name = df.columns[1].lower()
            if any(term in col_name for term in ["price", "cost"]):
                return "€/MWh"
            if any(term in col_name for term in ["power", "capacity"]):
                return "MW"
            if any(term in col_name for term in ["energy"]):
                return "MWh"

        return "MW"



    def compute_forecast_horizon(self, df, date_str):
        """
        Compute the forecast horizon based on the data.

        Args:
            df: Polars DataFrame with datetime column
            date_str: The date string for this forecast

        Returns:
            str: The forecast horizon (e.g., '48h')

        """
        if len(df) <= 1:
            return None

        try:
            # Get min and max timestamps
            min_date = df.select(pl.nth(0)).min().item(0, 0)
            max_date = df.select(pl.nth(0)).max().item(0, 0)

            # Calculate duration in hours
            if isinstance(min_date, datetime) and isinstance(max_date, datetime):
                duration = (max_date - min_date).total_seconds() / 3600
                return f"{int(duration)}h"
        except:
            pass

        # Default to 48h if calculation fails
        return None

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

                instance_name = instance_dir.name

                # Create an entry for this instance in our data dictionary
                if instance_name not in self.instances_data:
                    self.instances_data[to_snake_case(instance_name)] = {
                        "business_type": to_snake_case(business_type),
                        "instance_name": to_snake_case(instance_name),
                    }

                # Process each attribute in this instance
                for attribute_dir in instance_dir.iterdir():
                    attribute_name = attribute_dir.stem

                    # Determine the attribute type
                    if attribute_dir.is_file() and attribute_dir.suffix == ".csv":
                        # This is a Timeseries
                        self._process_timeseries(
                            business_type, instance_name, attribute_name, attribute_dir
                        )
                    elif attribute_dir.is_dir():
                        # Check the files inside to determine if it's a ForecastingMatrix or ScenarioMatrix
                        csv_files = list(attribute_dir.glob("*.csv"))
                        if not csv_files:
                            continue

                        if self.is_datetime_file(csv_files[0].name):
                            # This is a ForecastingMatrix
                            self._process_forecasting_matrix(
                                business_type, instance_name, attribute_name, attribute_dir
                            )
                        else:
                            # This is a ScenarioMatrix
                            self._process_scenario_matrix(
                                business_type, instance_name, attribute_name, attribute_dir
                            )

    def _process_timeseries(self, business_type, instance_name, attribute_name, file_path):
        """Process a Timeseries attribute."""
        # Copy the CSV file to the timeseries directory with a meaningful name
        profile_name = f"{attribute_name}.csv"
        target_path = self.timeseries_dir / to_snake_case(business_type) / to_snake_case(instance_name) / f"{to_snake_case(attribute_name)}.csv"
        os.makedirs(target_path.parent, exist_ok=True)

        # Copy the file

        pl.read_csv(file_path).with_columns(pl.from_epoch(pl.nth(0), time_unit="ns")).rename({'col_0':'date', 'col_1':"value"}).write_parquet(
            target_path
        )

        # Update the instance data
        self.instances_data[to_snake_case(instance_name)][to_snake_case(attribute_name)] = to_snake_case(profile_name)

    def _process_forecasting_matrix(self, business_type, instance_name, attribute_name, dir_path):
        """Process a ForecastingMatrix attribute."""
        # Create a directory for this matrix in the forecasting_matrix directory
        matrix_dir = self.forecasting_matrix_dir / to_snake_case(business_type) / to_snake_case(instance_name)
        os.makedirs(matrix_dir, exist_ok=True)

        # Create metadata.json
        forecast_dates = []

        # Store metadata info for each forecast date
        frequency = None
        unit = None
        columns = None

        # Process each CSV file in the directory
        for csv_file in dir_path.glob("*.csv"):
            if not self.is_datetime_file(csv_file.name):
                continue

            # Convert the old datetime format to the new one
            date_name = csv_file.stem  # Get filename without extension
            forecast_dates.append(date_name)

            # Read the CSV file with polars
            df = pl.read_csv(csv_file)

            # Try to convert the first column to datetime if it's numeric
            try:
                df = df.with_columns(pl.from_epoch(pl.nth(0), time_unit="ns")).rename({'col_0':'date', 'col_1':f"{date_name}"})
            except Exception:
                print(f"Error converting column {df.columns[0]} to datetime")

            # Get metadata from the actual data
            if frequency is None:
                frequency = self.detect_frequency(df)

            if unit is None:
                unit = self.detect_unit(df, attribute_name)

            # Get the forecast horizon for this file
            forecast_horizon = self.compute_forecast_horizon(df, date_name)

            # Convert to parquet and save
            parquet_path = matrix_dir / to_snake_case(attribute_name) / f"{date_name}.parquet"
            os.makedirs(parquet_path.parent, exist_ok=True)
            df.write_parquet(parquet_path)

            self.instances_data[to_snake_case(instance_name)][to_snake_case(attribute_name)] = to_snake_case(attribute_name)

        # Create metadata.json with dynamically computed values
        metadata = {
            "matrix_type": "forecast",
            "unit": unit or "MW",
            "frequency": frequency or "1h",
            "timezone": "UTC",
            "forecast_dates": forecast_dates,
            "forecast_horizon": forecast_horizon or "48h",
            "columns": columns or ["datetime", "value"],
            "description": f"Forecasts for {instance_name} {attribute_name}",
        }

        with open(matrix_dir / to_snake_case(attribute_name) / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

    def _process_scenario_matrix(self, business_type, instance_name, attribute_name, dir_path):
        """Process a ScenarioMatrix attribute."""
        # Create a directory for this matrix in the scenario_matrix directory
        matrix_dir = self.scenario_matrix_dir / to_snake_case(business_type) / to_snake_case(instance_name)
        os.makedirs(matrix_dir, exist_ok=True)

        # Process each CSV file in the directory
        scenarios = []

        # Store metadata info
        frequency = None
        timezone = None
        unit = None
        columns = None

        for i, csv_file in enumerate(dir_path.glob("*.csv"), 1):
            # Create a scenario name
            scenario_name = f"scenario_{i:03d}"
            scenarios.append(scenario_name)

            # Read the CSV file with polars
            df = pl.read_csv(csv_file)

            try:
                df = df.with_columns(pl.from_epoch(pl.nth(0), time_unit="ns")).rename({'col_0':'date', 'col_1':f"{scenario_name}"})
            except Exception:
                print(f"Error converting column {df.columns[0]} to datetime")

            # Get metadata from the actual data
            if frequency is None:
                frequency = self.detect_frequency(df)
            if unit is None:
                unit = self.detect_unit(df, attribute_name)

            parquet_path = matrix_dir / to_snake_case(attribute_name) / f"{scenario_name}.parquet"
            os.makedirs(parquet_path.parent, exist_ok=True)
            df.write_parquet(parquet_path)

        self.instances_data[to_snake_case(instance_name)][to_snake_case(attribute_name)] = to_snake_case(attribute_name)

        # Create metadata.json with dynamically computed values
        metadata = {
            "matrix_type": "scenario",
            "unit": unit or "MW",
            "frequency": frequency or "30min",
            "timezone": timezone or "UTC",
            "scenarios": scenarios,
            "description": f"Simulated production for {instance_name} {attribute_name} under different weather scenarios",
        }

        with open(matrix_dir / to_snake_case(attribute_name) / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

    def create_instance_csv(self):
        """Create CSV files for each business type containing instance data."""
        # Group instances by business type
        business_types = {}
        for instance_name, data in self.instances_data.items():
            business_type = data["business_type"]
            if business_type not in business_types:
                business_types[business_type] = []
            business_types[business_type].append(data)

        # Create a CSV file for each business type
        for business_type, instances in business_types.items():
            # Find all possible attribute columns across all instances of this type
            all_attributes = set()
            for instance_data in instances:
                all_attributes.update(instance_data.keys())

            # Remove non-attribute keys
            for key in ["business_type", "instance_name", "matrices"]:
                if key in all_attributes:
                    all_attributes.remove(key)

            # Create CSV data
            csv_data = []
            for instance_data in instances:
                # Start with the instance name
                row_data = {"instance_name": instance_data["instance_name"]}

                # Add all possible attributes (whether present for this instance or not)
                for attr in all_attributes:
                    row_data[attr] = instance_data.get(attr, "")

                csv_data.append(row_data)

            # Create DataFrame and save as CSV
            df = pl.DataFrame(csv_data)
            csv_path = self.data_dir / f"{to_snake_case(business_type)}.csv"
            df.write_csv(csv_path, separator=";")

    def transform(self):
        """Main method to perform the complete transformation."""
        self.process_source_tree()
        self.create_instance_csv()
        return self.target_root




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
