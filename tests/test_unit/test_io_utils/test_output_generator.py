"""Unit tests for save_to_directory class."""

import shutil

import pendulum
import polars as pl
import pytest

from atlas.io_utils.output_writer import save_to_directory
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.matrix import ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.equipment import Equipment
from atlas.models.node import Node
from atlas.models.portfolio import Portfolio


@pytest.fixture
def temp_output_dir(tmp_path):
    """Create a temporary directory for test outputs."""
    output_dir = tmp_path / "test_output"
    output_dir.mkdir()
    yield output_dir
    # Cleanup after test
    if output_dir.exists():
        shutil.rmtree(output_dir)


@pytest.fixture
def simple_timeseries():
    """Create a simple timeseries for testing."""
    df = pl.DataFrame(
        {
            "datetime": [
                pendulum.datetime(2024, 1, 1, 0),
                pendulum.datetime(2024, 1, 1, 1),
                pendulum.datetime(2024, 1, 1, 2),
            ],
            "value": [10.0, 20.0, 30.0],
        }
    )
    return Timeseries(timeseries=df)


@pytest.fixture
def simple_forecasting_matrix():
    """Create a simple forecasting matrix for testing."""
    df = pl.DataFrame(
        {
            "time": [
                pendulum.datetime(2024, 1, 1, 0),
                pendulum.datetime(2024, 1, 1, 1),
                pendulum.datetime(2024, 1, 1, 2),
            ],
            "2024-01-01 00:00:00": [10.0, 20.0, 30.0],
            "2024-01-01 01:00:00": [15.0, 25.0, 35.0],
        }
    )
    return ForecastingMatrix(matrix=df)


@pytest.fixture
def simple_scenario_matrix():
    """Create a simple scenario matrix for testing."""
    df = pl.DataFrame(
        {
            "datetime": [
                pendulum.datetime(2024, 1, 1, 0),
                pendulum.datetime(2024, 1, 1, 1),
            ],
            "scenario": [0, 1],
            "value": [50.0, 60.0],
        }
    )
    return ScenarioMatrix(matrix=df)


class TestOutputGeneratorToDirectory:
    """Test the to_directory method of save_to_directory."""

    def test_to_directory_simple_objects(self, temp_output_dir):
        """Test exporting simple BusinessModel objects without math fields."""
        # Create simple business models
        node1 = Node(name="node_1")
        node2 = Node(name="node_2")

        dataset = {"node": [node1, node2]}

        # Export to directory
        save_to_directory(dataset, temp_output_dir)

        # Verify directory structure
        assert (temp_output_dir / "objects").exists()
        assert (temp_output_dir / "objects" / "node.csv").exists()

        # Read and verify CSV content
        csv_content = (temp_output_dir / "objects" / "node.csv").read_text()
        lines = csv_content.strip().split("\n")

        # Check header starts with "name" and has other fields
        assert lines[0].startswith("name;")
        assert "balance_forecast" in lines[0]  # Node has other fields

        # Check data rows contain the node names
        assert "node_1" in lines[1]
        assert "node_2" in lines[2]

    def test_to_directory_with_none_values(self, temp_output_dir):
        """Test that None values are exported as empty strings in CSV."""

        # Create equipment with some None values
        equipment = Equipment(
            name="test_equipment",
            node=None,
            portfolio=None,
            co2_emission_factor=None,
            maximum_afrr=100.0,
        )

        dataset = {"equipment": [equipment]}

        # Export to directory
        save_to_directory(dataset, temp_output_dir)

        # Read CSV content
        csv_content = (temp_output_dir / "objects" / "equipment.csv").read_text()
        lines = csv_content.strip().split("\n")

        # Find the data row (second line)
        data_row = lines[1]
        fields = data_row.split(";")

        # Check that name is first
        assert fields[0] == "test_equipment"

        # Check that None values appear as empty strings (not "None")
        # The exact position depends on alphabetical ordering of fields
        assert "" in fields  # At least one empty field for None values
        assert "None" not in data_row  # Should not contain the string "None"

    def test_to_directory_with_timeseries(self, temp_output_dir, simple_timeseries):
        """Test exporting objects with Timeseries fields."""

        # Create equipment with timeseries
        equipment = Equipment(
            name="test_equipment",
            variable_cost=simple_timeseries,
        )

        dataset = {"equipment": [equipment]}

        # Export to directory
        save_to_directory(dataset, temp_output_dir)

        # Verify directory structure
        assert (temp_output_dir / "timeseries").exists()
        assert (temp_output_dir / "timeseries" / "equipment").exists()
        assert (temp_output_dir / "timeseries" / "equipment" / "test_equipment.parquet").exists()

        # Read CSV and verify timeseries is marked
        csv_content = (temp_output_dir / "objects" / "equipment.csv").read_text()
        assert "timeseries" in csv_content

        # Verify parquet file can be read and has correct structure
        parquet_path = temp_output_dir / "timeseries" / "equipment" / "test_equipment.parquet"
        df = pl.read_parquet(parquet_path)
        # Timeseries with attribute are saved as time, attribute, value columns
        assert "time" in df.columns
        assert "attribute" in df.columns
        assert "value" in df.columns
        # Check the attribute column contains "variable_cost"
        assert "variable_cost" in df["attribute"].to_list()
        assert len(df) == 3

    def test_to_directory_with_forecasting_matrix(self, temp_output_dir, simple_forecasting_matrix):
        """Test exporting objects with ForecastingMatrix fields."""

        # Create equipment with forecasting matrix
        equipment = Equipment(
            name="test_equipment",
            power=simple_forecasting_matrix,
        )

        dataset = {"equipment": [equipment]}

        # Export to directory
        save_to_directory(dataset, temp_output_dir)

        # Verify directory structure
        assert (temp_output_dir / "forecasting_matrix").exists()
        assert (temp_output_dir / "forecasting_matrix" / "equipment").exists()
        assert (temp_output_dir / "forecasting_matrix" / "equipment" / "test_equipment.parquet").exists()

        # Read CSV and verify forecasting_matrix is marked
        csv_content = (temp_output_dir / "objects" / "equipment.csv").read_text()
        assert "forecasting_matrix" in csv_content

        # Verify parquet file can be read
        parquet_path = temp_output_dir / "forecasting_matrix" / "equipment" / "test_equipment.parquet"
        df = pl.read_parquet(parquet_path)
        # ForecastingMatrix with attribute are saved as time, attribute, value, horizon columns
        assert "attribute" in df.columns
        assert "power" in df["attribute"].to_list()

    def test_to_directory_with_scenario_matrix(self, temp_output_dir, simple_scenario_matrix):
        """Test exporting objects with ScenarioMatrix fields."""

        # Create equipment with scenario matrix
        equipment = Equipment(
            name="test_equipment",
            storage_marginal_value=simple_scenario_matrix,
        )

        dataset = {"equipment": [equipment]}

        # Export to directory
        save_to_directory(dataset, temp_output_dir)

        # Verify directory structure
        assert (temp_output_dir / "scenario_matrix").exists()
        assert (temp_output_dir / "scenario_matrix" / "equipment").exists()
        assert (temp_output_dir / "scenario_matrix" / "equipment" / "test_equipment.parquet").exists()

        # Read CSV and verify scenario_matrix is marked
        csv_content = (temp_output_dir / "objects" / "equipment.csv").read_text()
        assert "scenario_matrix" in csv_content

        # Verify parquet file can be read
        parquet_path = temp_output_dir / "scenario_matrix" / "equipment" / "test_equipment.parquet"
        df = pl.read_parquet(parquet_path)
        # ScenarioMatrix with attribute are saved as time, attribute, value, scenario columns
        assert "attribute" in df.columns
        assert "storage_marginal_value" in df["attribute"].to_list()

    def test_to_directory_multiple_objects(self, temp_output_dir, simple_timeseries):
        """Test exporting multiple objects of the same type."""

        # Create multiple equipment objects
        equipment1 = Equipment(name="equipment_1", co2_emission_factor=0.5)
        equipment2 = Equipment(name="equipment_2", co2_emission_factor=0.8, variable_cost=simple_timeseries)

        dataset = {"equipment": [equipment1, equipment2]}

        # Export to directory
        save_to_directory(dataset, temp_output_dir)

        # Read CSV content
        csv_content = (temp_output_dir / "objects" / "equipment.csv").read_text()
        lines = csv_content.strip().split("\n")

        # Verify both objects are in the CSV
        assert len(lines) == 3  # Header + 2 data rows
        assert "equipment_1" in csv_content
        assert "equipment_2" in csv_content

    def test_to_directory_multiple_object_types(self, temp_output_dir):
        """Test exporting multiple different object types."""
        node = Node(name="test_node")
        portfolio = Portfolio(name="test_portfolio")

        dataset = {"node": [node], "portfolio": [portfolio]}

        # Export to directory
        save_to_directory(dataset, temp_output_dir)

        # Verify both CSV files exist
        assert (temp_output_dir / "objects" / "node.csv").exists()
        assert (temp_output_dir / "objects" / "portfolio.csv").exists()

        # Verify content
        node_csv = (temp_output_dir / "objects" / "node.csv").read_text()
        assert "test_node" in node_csv

        portfolio_csv = (temp_output_dir / "objects" / "portfolio.csv").read_text()
        assert "test_portfolio" in portfolio_csv

    def test_to_directory_with_business_model_references(self, temp_output_dir):
        """Test exporting objects with BusinessModel reference fields."""

        # Create related business models
        node = Node(name="test_node")
        portfolio = Portfolio(name="test_portfolio")

        # Create equipment referencing them
        equipment = Equipment(
            name="test_equipment",
            node=node,
            portfolio=portfolio,
            co2_emission_factor=0.5,
        )

        dataset = {"equipment": [equipment]}

        # Export to directory
        save_to_directory(dataset, temp_output_dir)

        # Read CSV content
        csv_content = (temp_output_dir / "objects" / "equipment.csv").read_text()

        # Verify that BusinessModel references are serialized to names
        assert "test_node" in csv_content
        assert "test_portfolio" in csv_content

    def test_to_directory_custom_separator(self, temp_output_dir):
        """Test exporting with custom CSV separator."""
        node = Node(name="test_node")

        dataset = {"node": [node]}

        # Export with custom separator
        save_to_directory(dataset, temp_output_dir, separator=",")

        # Read CSV content
        csv_content = (temp_output_dir / "objects" / "node.csv").read_text()

        # Verify separator is used (header should have commas)
        assert "," in csv_content.split("\n")[0]

    def test_to_directory_csv_file_extension(self, temp_output_dir, simple_timeseries):
        """Test exporting timeseries with CSV file extension."""
        from atlas.models.equipment.equipment import Equipment

        equipment = Equipment(name="test_equipment", variable_cost=simple_timeseries)

        dataset = {"equipment": [equipment]}

        # Export with CSV extension for timeseries
        save_to_directory(dataset, temp_output_dir, timeseries_file_extension="csv")

        # Verify CSV file exists instead of parquet
        assert (temp_output_dir / "timeseries" / "equipment" / "test_equipment.csv").exists()

    def test_to_directory_empty_dataset(self, temp_output_dir):
        """Test exporting empty dataset."""
        dataset = {}

        # Should not raise error
        save_to_directory(dataset, temp_output_dir)

        # Objects directory should still be created
        assert (temp_output_dir / "objects").exists()

    def test_to_directory_creates_nested_directories(self, temp_output_dir):
        """Test that all required directories are created."""
        node = Node(name="test_node")
        dataset = {"node": [node]}

        # Export to directory
        save_to_directory(dataset, temp_output_dir)

        # Verify all directories are created
        assert (temp_output_dir / "objects").is_dir()
        assert (temp_output_dir / "timeseries").is_dir()
        assert (temp_output_dir / "scenario_matrix").is_dir()
        assert (temp_output_dir / "forecasting_matrix").is_dir()
