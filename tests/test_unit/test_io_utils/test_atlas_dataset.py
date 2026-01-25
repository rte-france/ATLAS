"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Test suite for AtlasDataset
"""

import pickle
from datetime import datetime

import polars as pl
import pytest
from pendulum import DateTime, Duration, Timezone

from atlas.enum import ComplementDirection, CouplingType, OrderType, Product, ThermalStrategy
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.control_block import ControlBlock
from atlas.models.equipment.hydro import Hydro
from atlas.models.equipment.thermal import Thermal
from atlas.models.market.market_area import MarketArea
from atlas.models.market.order import Order
from atlas.models.market.order_coupling import OrderCoupling
from atlas.models.node import Node
from atlas.models.portfolio import Portfolio


class TestAtlasDatasetBasic:
    """Test basic AtlasDataset functionality."""

    def test_empty_dataset_creation(self):
        """Test creating an empty AtlasDataset."""
        dataset = AtlasDataset()
        assert len(dataset) == 0
        assert dataset.node == []
        assert dataset.hydro == []
        assert "any_object_name" not in dataset

    def test_dataset_with_objects(self):
        """Test creating a dataset with objects."""
        nodes = [
            Node(name="node1"),
            Node(name="node2"),
        ]

        dataset = AtlasDataset(node=nodes)

        assert len(dataset) == 2
        assert len(dataset.node) == 2
        assert dataset.node[0].name == "node1"
        assert dataset.node[1].name == "node2"
        assert "node1" in dataset

    def test_attribute_access(self):
        """Test attribute-style access to object types."""
        control_blocks = [ControlBlock(name="cb1")]
        nodes = [Node(name="node1")]

        dataset = AtlasDataset(control_block=control_blocks, node=nodes)

        assert dataset.control_block == control_blocks
        assert dataset.node == nodes
        assert dataset.thermal == []

    def test_contains_operator(self):
        """Test the 'in' operator checks for object names and instances."""
        nodes = [Node(name="node1"), Node(name="node2")]
        control_blocks = [ControlBlock(name="cb1")]
        dataset = AtlasDataset(node=nodes, control_block=control_blocks)

        # Test that object names (str) are found
        assert "node1" in dataset
        assert "node2" in dataset
        assert "cb1" in dataset

        # Test that non-existent names are not found
        assert "node3" not in dataset
        assert "nonexistent" not in dataset

        # Test that object instances are found
        assert nodes[0] in dataset
        assert nodes[1] in dataset
        assert control_blocks[0] in dataset

        # Test that a different instance with same name is not found
        different_node = Node(name="node1")
        assert different_node not in dataset

        # Test invalid type returns False
        assert 123 not in dataset
        assert None not in dataset

    def test_len_operator(self):
        """Test the len() operator."""
        nodes = [Node(name="node1"), Node(name="node2")]
        control_blocks = [ControlBlock(name="cb1")]

        dataset = AtlasDataset(node=nodes, control_block=control_blocks)

        assert len(dataset) == 3

    def test_repr_and_str(self):
        """Test string representation."""
        nodes = [Node(name="node1")]
        dataset = AtlasDataset(node=nodes)

        repr_str = repr(dataset)
        assert "AtlasDataset" in repr_str
        assert "node=1" in repr_str

        str_str = str(dataset)
        assert str_str == repr_str

    def test_iter_operator(self):
        """Test iterating over the entire dataset."""
        nodes = [Node(name="node1"), Node(name="node2")]
        control_blocks = [ControlBlock(name="cb1")]

        dataset = AtlasDataset(node=nodes, control_block=control_blocks)

        # Collect all objects
        all_objects = list(dataset)
        assert len(all_objects) == 3

        # Verify we got all objects
        names = [obj.name for obj in all_objects]
        assert "node1" in names
        assert "node2" in names
        assert "cb1" in names

    def test_iter_operator_empty(self):
        """Test iterating over an empty dataset."""
        dataset = AtlasDataset()

        all_objects = list(dataset)
        assert all_objects == []

    def test_iter_operator_multiple_times(self):
        """Test that iteration can be performed multiple times."""
        nodes = [Node(name="node1"), Node(name="node2")]
        dataset = AtlasDataset(node=nodes)

        # First iteration
        first_count = sum(1 for _ in dataset)
        assert first_count == 2

        # Second iteration (should work again)
        second_count = sum(1 for _ in dataset)
        assert second_count == 2

        # Both should produce same results
        assert first_count == second_count


class TestAtlasDatasetLookup:
    """Test efficient lookup functionality."""

    def test_get_by_name(self):
        """Test O(1) lookup by name."""
        nodes = [
            Node(name="node1"),
            Node(name="node2"),
            Node(name="node3"),
        ]
        dataset = AtlasDataset(node=nodes)

        found = dataset.get("node", "node2")
        assert found is not None
        assert found.name == "node2"
        assert found is nodes[1]  # Same object reference

    def test_get_nonexistent_name(self):
        """Test lookup for non-existent name returns None."""
        nodes = [Node(name="node1")]
        dataset = AtlasDataset(node=nodes)

        found = dataset.get("node", "nonexistent")
        assert found is None

    def test_get_nonexistent_type(self):
        """Test lookup for non-existent type returns None."""
        nodes = [Node(name="node1")]
        dataset = AtlasDataset(node=nodes)

        found = dataset.get("thermal", "anything")
        assert found is None

    def test_iter_by_types_single(self):
        """Test iter_by_types method with a single type."""
        nodes = [Node(name="node1"), Node(name="node2"), Node(name="node3")]
        dataset = AtlasDataset(node=nodes)

        # Test iteration over single type
        collected_nodes = list(dataset.iter_by_types("node"))
        assert collected_nodes == nodes
        assert len(collected_nodes) == 3

        # Test with empty type
        collected_thermal = list(dataset.iter_by_types("thermal"))
        assert collected_thermal == []

    def test_iter_by_types_multiple(self):
        """Test iter_by_types method with multiple types."""
        nodes = [Node(name="node1"), Node(name="node2")]
        control_blocks = [ControlBlock(name="cb1"), ControlBlock(name="cb2")]
        dataset = AtlasDataset(node=nodes, control_block=control_blocks)

        # Test iteration over multiple types
        collected = list(dataset.iter_by_types("node", "control_block"))
        assert len(collected) == 4
        # First nodes, then control_blocks (order matters)
        assert collected[:2] == nodes
        assert collected[2:] == control_blocks

    def test_iter_by_types_invalid_type(self):
        """Test iter_by_types with invalid type raises error."""
        dataset = AtlasDataset()

        with pytest.raises(ValueError, match="Invalid object type"):
            list(dataset.iter_by_types("invalid_type"))

        # Test with mix of valid and invalid
        nodes = [Node(name="node1")]
        dataset = AtlasDataset(node=nodes)
        with pytest.raises(ValueError, match="Invalid object type"):
            list(dataset.iter_by_types("node", "invalid_type"))

    def test_iter_by_types_lazy_evaluation(self):
        """Test that iter_by_types is a generator and can be consumed multiple times."""
        nodes = [Node(name="node1"), Node(name="node2")]
        dataset = AtlasDataset(node=nodes)

        # First iteration
        count1 = sum(1 for _ in dataset.iter_by_types("node"))
        assert count1 == 2

        # Second iteration (should work again)
        count2 = sum(1 for _ in dataset.iter_by_types("node"))
        assert count2 == 2

    def test_duplicate_names_validation(self):
        """Test that duplicate names within a type are detected."""
        nodes = [
            Node(name="duplicate"),
            Node(name="duplicate"),
        ]

        with pytest.raises(ValueError, match="Duplicate object name"):
            AtlasDataset(node=nodes)


class TestAtlasDatasetConversion:
    """Test conversion between dict and AtlasDataset."""

    def test_to_dict(self):
        """Test converting AtlasDataset to dict."""
        nodes = [Node(name="node1")]
        control_blocks = [ControlBlock(name="cb1")]

        dataset = AtlasDataset(node=nodes, control_block=control_blocks)
        result = dataset.to_dict()

        assert isinstance(result, dict)
        assert "node" in result
        assert "control_block" in result
        assert result["node"] == nodes
        assert result["control_block"] == control_blocks
        # Empty lists should not be included
        assert "thermal" not in result

    def test_from_dict(self):
        """Test creating AtlasDataset from dict."""
        nodes = [Node(name="node1")]
        data = {"node": nodes}

        dataset = AtlasDataset.from_dict(data)

        assert dataset.node == nodes
        assert dataset.thermal == []

    def test_from_dict_empty(self):
        """Test creating AtlasDataset from empty dict."""
        dataset = AtlasDataset.from_dict({})

        assert len(dataset) == 0
        assert dataset.node == []

    def test_roundtrip_dict_conversion(self):
        """Test that to_dict and from_dict are inverses."""
        nodes = [Node(name="node1"), Node(name="node2")]
        control_blocks = [ControlBlock(name="cb1")]

        dataset1 = AtlasDataset(node=nodes, control_block=control_blocks)
        data = dataset1.to_dict()
        dataset2 = AtlasDataset.from_dict(data)

        assert len(dataset2) == len(dataset1)
        assert dataset2.node == dataset1.node
        assert dataset2.control_block == dataset1.control_block


class TestAtlasDatasetIO:
    """Test I/O operations (from_directory and to_directory)."""

    def test_from_directory_integration(self, tmp_path):
        """Test loading from a real directory structure."""
        # Setup test directory
        test_dir = tmp_path / "test_data"
        test_dir.mkdir()
        (test_dir / "objects").mkdir()

        # Create minimal test data

        pl.DataFrame([{"name": "node1"}]).write_csv(test_dir / "objects" / "node.csv", separator=";")

        # Load dataset
        dataset = AtlasDataset.from_directory(test_dir)

        assert isinstance(dataset, AtlasDataset)
        assert len(dataset.node) == 1
        assert dataset.node[0].name == "node1"

    def test_to_directory_integration(self, tmp_path):
        """Test writing to a directory structure."""
        nodes = [Node(name="node1")]
        dataset = AtlasDataset(node=nodes)

        output_dir = tmp_path / "output"
        dataset.to_directory(output_dir)

        # Verify directory structure was created
        assert (output_dir / "objects").exists()
        assert (output_dir / "objects" / "node.csv").exists()

        # Verify content

        df = pl.read_csv(output_dir / "objects" / "node.csv", separator=";")
        assert len(df) == 1
        assert df["name"][0] == "node1"

    def test_roundtrip_io(self, tmp_path):
        """Test that from_directory and to_directory are compatible."""
        # Use ControlBlock which has minimal dependencies
        control_blocks = [ControlBlock(name="cb1"), ControlBlock(name="cb2")]
        dataset1 = AtlasDataset(control_block=control_blocks)

        # Write to directory
        output_dir = tmp_path / "output"
        dataset1.to_directory(output_dir)

        # Read back
        dataset2 = AtlasDataset.from_directory(output_dir)

        # Verify
        assert len(dataset2.control_block) == len(dataset1.control_block)
        assert dataset2.control_block[0].name == dataset1.control_block[0].name
        assert dataset2.control_block[1].name == dataset1.control_block[1].name

    def test_from_directory_with_string_path(self, tmp_path):
        """Test that from_directory accepts string paths."""
        test_dir = tmp_path / "test_data"
        test_dir.mkdir()
        (test_dir / "objects").mkdir()

        pl.DataFrame([{"name": "node1"}]).write_csv(test_dir / "objects" / "node.csv", separator=";")

        # Pass as string
        dataset = AtlasDataset.from_directory(str(test_dir))

        assert isinstance(dataset, AtlasDataset)
        assert len(dataset.node) == 1

    def test_to_directory_with_string_path(self, tmp_path):
        """Test that to_directory accepts string paths."""
        nodes = [Node(name="node1")]
        dataset = AtlasDataset(node=nodes)

        output_dir = tmp_path / "output"

        # Pass as string
        dataset.to_directory(str(output_dir))

        assert output_dir.exists()
        assert (output_dir / "objects" / "node.csv").exists()


class TestAtlasDatasetValidation:
    """Test Pydantic validation features."""

    def test_type_validation(self):
        """Test that Pydantic validates object types."""
        # This should work
        dataset = AtlasDataset(node=[Node(name="node1")])
        assert len(dataset.node) == 1

        # This should fail - wrong type
        with pytest.raises(Exception):  # Pydantic validation error
            AtlasDataset(node=[ControlBlock(name="cb1")])

    def test_assignment_validation(self):
        """Test that assignment triggers validation."""
        dataset = AtlasDataset()

        # Valid assignment
        dataset.node = [Node(name="node1")]
        assert len(dataset.node) == 1

        # After assignment, indices should be rebuilt
        found = dataset.get("node", "node1")
        assert found is not None


class TestAtlasDatasetEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_lists_in_to_dict(self):
        """Test that empty object lists are excluded from to_dict."""
        dataset = AtlasDataset(node=[Node(name="node1")])
        result = dataset.to_dict()

        assert "node" in result
        assert "thermal" not in result
        assert "equipment" not in result

    def test_multiple_object_types(self):
        """Test dataset with many different object types."""
        dataset = AtlasDataset(
            node=[Node(name="n1"), Node(name="n2")],
            control_block=[ControlBlock(name="cb1")],
        )

        assert len(dataset) == 3
        assert len(dataset.node) == 2
        assert len(dataset.control_block) == 1

        # Test lookups across types
        assert dataset.get("node", "n1") is not None
        assert dataset.get("node", "n2") is not None
        assert dataset.get("control_block", "cb1") is not None
        assert dataset.get("thermal", "anything") is None


class TestAtlasDatasetPickling:
    """Test pickling support for AtlasDataset."""

    def test_to_pickle_method(self, tmp_path):
        """Test the to_pickle method."""
        nodes = [Node(name="node1"), Node(name="node2")]
        control_blocks = [ControlBlock(name="cb1")]
        dataset = AtlasDataset(node=nodes, control_block=control_blocks)

        # Save to pickle file
        pickle_file = tmp_path / "dataset.pkl"
        dataset.to_pickle(pickle_file)

        # Verify file was created
        assert pickle_file.exists()

        with open(pickle_file, "rb") as f:
            restored = pickle.load(f)

        assert isinstance(restored, AtlasDataset)
        assert len(restored) == 3
        assert restored.node[0].name == "node1"

    def test_from_pickle_method(self, tmp_path):
        """Test the from_pickle method."""
        nodes = [Node(name="node1"), Node(name="node2")]
        control_blocks = [ControlBlock(name="cb1")]
        dataset = AtlasDataset(node=nodes, control_block=control_blocks)

        # Save using standard pickle
        pickle_file = tmp_path / "dataset.pkl"

        with open(pickle_file, "wb") as f:
            pickle.dump(dataset, f)

        # Load using from_pickle method
        restored = AtlasDataset.from_pickle(pickle_file)

        assert isinstance(restored, AtlasDataset)
        assert len(restored) == 3
        assert restored.node[0].name == "node1"
        assert restored.node[1].name == "node2"
        assert restored.control_block[0].name == "cb1"

    def test_roundtrip_pickle_methods(self, tmp_path):
        """Test roundtrip using to_pickle and from_pickle methods."""
        nodes = [Node(name="node1"), Node(name="node2"), Node(name="node3")]
        control_blocks = [ControlBlock(name="cb1"), ControlBlock(name="cb2")]
        dataset1 = AtlasDataset(node=nodes, control_block=control_blocks)

        # Save and load
        pickle_file = tmp_path / "dataset.pkl"
        dataset1.to_pickle(pickle_file)
        dataset2 = AtlasDataset.from_pickle(pickle_file)

        # Verify all data is preserved
        assert len(dataset2) == len(dataset1)
        assert len(dataset2.node) == len(dataset1.node)
        assert len(dataset2.control_block) == len(dataset1.control_block)

        # Verify object names
        for i, node in enumerate(dataset1.node):
            assert dataset2.node[i].name == node.name

        for i, cb in enumerate(dataset1.control_block):
            assert dataset2.control_block[i].name == cb.name

        # Verify lookups work
        assert dataset2.get("node", "node2") is not None
        assert dataset2.get("control_block", "cb1") is not None

    def test_pickle_methods_with_string_path(self, tmp_path):
        """Test that pickle methods accept string paths."""
        nodes = [Node(name="node1")]
        dataset = AtlasDataset(node=nodes)

        # Test with string path
        pickle_file = str(tmp_path / "dataset.pkl")
        dataset.to_pickle(pickle_file)

        # Load with string path
        restored = AtlasDataset.from_pickle(pickle_file)

        assert isinstance(restored, AtlasDataset)
        assert len(restored) == 1
        assert restored.node[0].name == "node1"

    def test_roundtrip_io_reading_writing(self, tmp_path):
        """Test round-trip with dataset containing timeseries, matrices, references, lists, Duration, DateTime, and list of BusinessModels."""

        control_block = ControlBlock(name="cb1")
        market_area = MarketArea(name="ma1", control_block=control_block)
        node = Node(name="node1", control_block=control_block, market_area=market_area)
        portfolio = Portfolio(name="portfolio1", control_block=control_block, market_area=market_area)

        timeseries_inflows = Timeseries.from_values(
            start_date="2024-01-01 00:00:00",
            frequency="1h",
            values=[100.0, 110.0, 120.0],
            timezone="UTC",
        )
        timeseries_max_power = Timeseries.from_values(
            start_date="2024-01-01 00:00:00",
            frequency="1h",
            values=[500.0, 500.0, 500.0],
            timezone="UTC",
        )

        matrix_df = pl.DataFrame(
            {
                "time": pl.datetime_range(
                    start=datetime(2024, 1, 1, 0, 0, 0),
                    end=datetime(2024, 1, 1, 2, 0, 0),
                    interval="1h",
                    time_unit="us",
                    eager=True,
                ),
                "2024-01-01 00:00:00": [150.0, 160.0, 170.0],
                "2024-01-01 01:00:00": [180.0, 190.0, 200.0],
            }
        )
        forecasting_matrix = ForecastingMatrix(matrix_df)

        hydro1 = Hydro(
            name="hydro1",
            node=node,
            portfolio=portfolio,
            inflows=timeseries_inflows,
            maximum_power=timeseries_max_power,
            stored_energy=forecasting_matrix,
            fragment_prices=[10.0, 20.0, 30.0],
            fragment_volumes=[0.3, 0.5, 0.2],
        )

        hydro2 = Hydro(
            name="hydro2",
            node=node,
            portfolio=portfolio,
            fragment_prices=[15.0, 25.0],
            fragment_volumes=[0.6, 0.4],
        )

        thermal = Thermal(
            name="thermal1",
            node=node,
            portfolio=portfolio,
            installed_capacity=1000.0,
            minimum_stable_power_duration=Duration(hours=2),
            minimum_time_off=Duration(hours=4),
            minimum_time_on=Duration(hours=6),
            shutdown_duration=Duration(hours=1),
            startup_duration=Duration(hours=1.5),
            strategy=ThermalStrategy.BASE,
        )

        order1 = Order(
            name="order1",
            equipment=thermal,
            market_area=market_area,
            portfolio=portfolio,
            execution_date=DateTime(2024, 1, 1, 10, 0, 0),
            start_date=DateTime(2024, 1, 1, 12, 0, 0),
            end_date=DateTime(2024, 1, 1, 18, 0, 0),
            order_type=OrderType.Sell,
            product=Product.DayAhead,
            price=50.0,
            qmax=100.0,
            qmin=0.0,
        )

        order2 = Order(
            name="order2",
            equipment=hydro1,
            market_area=market_area,
            portfolio=portfolio,
            execution_date=DateTime(2024, 1, 1, 11, 0, 0),
            start_date=DateTime(2024, 1, 1, 13, 0, 0),
            end_date=DateTime(2024, 1, 1, 19, 0, 0),
            order_type=OrderType.Buy,
            product=Product.DayAhead,
            price=45.0,
            qmax=150.0,
            qmin=10.0,
        )

        order_coupling = OrderCoupling(
            name="coupling1",
            orders=[order1, order2],
            coupling_type=CouplingType.COMPLEMENT,
            complement_direction=ComplementDirection.EqualTo,
            complement_energy=250.0,
        )

        dataset1 = AtlasDataset(
            control_block=[control_block],
            market_area=[market_area],
            node=[node],
            portfolio=[portfolio],
            hydro=[hydro1, hydro2],
            thermal=[thermal],
            order=[order1, order2],
            order_coupling=[order_coupling],
        )

        output_dir = tmp_path / "output"
        dataset1.to_directory(output_dir)

        # Read back
        dataset2 = AtlasDataset.from_directory(output_dir)

        assert len(dataset2) == 10
        assert len(dataset2.hydro) == 2
        assert len(dataset2.node) == 1
        assert len(dataset2.portfolio) == 1
        assert len(dataset2.control_block) == 1
        assert len(dataset2.market_area) == 1
        assert len(dataset2.thermal) == 1
        assert len(dataset2.order) == 2
        assert len(dataset2.order_coupling) == 1

        assert dataset2.hydro[0].name == "hydro1"
        assert dataset2.hydro[1].name == "hydro2"

        assert dataset2.hydro[0].node.name == "node1"
        assert dataset2.hydro[0].portfolio.name == "portfolio1"

        assert dataset2.hydro[0].inflows == timeseries_inflows
        assert dataset2.hydro[0].maximum_power == timeseries_max_power

        assert dataset2.hydro[0].stored_energy == forecasting_matrix

        assert dataset2.hydro[0].fragment_prices == [10.0, 20.0, 30.0]
        assert dataset2.hydro[0].fragment_volumes == [0.3, 0.5, 0.2]
        assert dataset2.hydro[1].fragment_prices == [15.0, 25.0]
        assert dataset2.hydro[1].fragment_volumes == [0.6, 0.4]

        assert dataset2.thermal[0].name == "thermal1"
        assert dataset2.thermal[0].minimum_stable_power_duration == Duration(hours=2)
        assert dataset2.thermal[0].minimum_time_off == Duration(hours=4)
        assert dataset2.thermal[0].minimum_time_on == Duration(hours=6)
        assert dataset2.thermal[0].shutdown_duration == Duration(hours=1)
        assert dataset2.thermal[0].startup_duration == Duration(hours=1.5)
        assert dataset2.thermal[0].strategy == ThermalStrategy.BASE

        assert dataset2.order[0].name == "order1"
        assert dataset2.order[0].execution_date == DateTime(2024, 1, 1, 10, 0, 0, tzinfo=Timezone("UTC"))
        assert dataset2.order[0].start_date == DateTime(2024, 1, 1, 12, 0, 0, tzinfo=Timezone("UTC"))
        assert dataset2.order[0].end_date == DateTime(2024, 1, 1, 18, 0, 0, tzinfo=Timezone("UTC"))
        assert dataset2.order[0].order_type == OrderType.Sell
        assert dataset2.order[0].product == Product.DayAhead

        assert dataset2.order[1].name == "order2"
        assert dataset2.order[1].execution_date == DateTime(2024, 1, 1, 11, 0, 0, tzinfo=Timezone("UTC"))
        assert dataset2.order[1].start_date == DateTime(2024, 1, 1, 13, 0, 0, tzinfo=Timezone("UTC"))
        assert dataset2.order[1].end_date == DateTime(2024, 1, 1, 19, 0, 0, tzinfo=Timezone("UTC"))

        assert dataset2.order_coupling[0].name == "coupling1"
        assert len(dataset2.order_coupling[0].orders) == 2
        assert dataset2.order_coupling[0].orders[0].name == "order1"
        assert dataset2.order_coupling[0].orders[1].name == "order2"
        assert dataset2.order_coupling[0].coupling_type == CouplingType.COMPLEMENT
        assert dataset2.order_coupling[0].complement_direction == ComplementDirection.EqualTo
        assert dataset2.order_coupling[0].complement_energy == 250.0
