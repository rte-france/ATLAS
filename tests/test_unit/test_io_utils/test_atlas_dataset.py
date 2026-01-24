"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Test suite for AtlasDataset
"""

import pytest

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.models.control_block import ControlBlock
from atlas.models.node import Node


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
        import polars as pl

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
        import polars as pl

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

        import polars as pl

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
