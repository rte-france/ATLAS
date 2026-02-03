"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Test suite for AtlasDataset
"""

from datetime import datetime

import polars as pl
import pytest
from pendulum import DateTime, Duration, Timezone

from atlas.enum import ComplementDirection, CouplingType, OrderType, Product, ThermalStrategy
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.io_utils.container import Container

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
    def test_empty_dataset_creation(self):
        dataset = AtlasDataset()
        assert len(dataset) == 0
        assert dataset.node.is_empty()
        assert dataset.hydro.is_empty()
        assert "any_object_name" not in dataset

    def test_dataset_with_objects(self):
        nodes = Container([Node(name="node1"), Node(name="node2")])
        dataset = AtlasDataset(node=nodes)

        assert len(dataset) == 2
        assert len(dataset.node) == 2
        assert dataset.node.get("node1")
        assert dataset.node.get("node2")
        assert "node1" in dataset

    def test_attribute_access(self):
        control_blocks = Container([ControlBlock(name="cb1")])
        nodes = Container([Node(name="node1")])

        dataset = AtlasDataset(control_block=control_blocks, node=nodes)

        assert dataset.control_block is control_blocks
        assert dataset.node is nodes
        assert dataset.thermal.is_empty()

    def test_contains_operator(self):
        control_blocks = Container([ControlBlock(name="cb1")])
        nodes = Container([Node(name="node1"), Node(name="node2")])
        dataset = AtlasDataset(node=nodes, control_block=control_blocks)

        assert "node1" in dataset
        assert "node2" in dataset
        assert "cb1" in dataset

        assert "node3" not in dataset
        assert "nonexistent" not in dataset

        assert nodes.get("node1") in dataset
        assert nodes.get("node2") in dataset
        assert control_blocks.get("cb1") in dataset

        assert Node(name="node1") not in dataset
        assert 123 not in dataset
        assert None not in dataset

    def test_len_operator(self):
        dataset = AtlasDataset(
            node=Container([Node(name="node1"), Node(name="node2")]),
            control_block=Container([ControlBlock(name="cb1")]),
        )
        assert len(dataset) == 3

    def test_repr_and_str(self):
        dataset = AtlasDataset(node=Container([Node(name="node1")]))
        assert "AtlasDataset" in repr(dataset)
        assert "node=1" in repr(dataset)
        assert str(dataset) == repr(dataset)

    def test_iter_operator(self):
        dataset = AtlasDataset(
            node=Container([Node(name="node1"), Node(name="node2")]),
            control_block=Container([ControlBlock(name="cb1")]),
        )

        objects = list(dataset)
        names = {o.name for o in objects}
        assert names == {"node1", "node2", "cb1"}

    def test_iter_operator_empty(self):
        assert list(AtlasDataset()) == []

    def test_iter_operator_multiple_times(self):
        dataset = AtlasDataset(node=Container([Node(name="node1"), Node(name="node2")]))
        assert sum(1 for _ in dataset) == 2
        assert sum(1 for _ in dataset) == 2


class TestAtlasDatasetLookup:
    def test_get_nonexistent_name(self):
        dataset = AtlasDataset(node=Container([Node(name="node1")]))
        assert dataset.get("node", "nope") is None

    def test_get_nonexistent_type(self):
        dataset = AtlasDataset(node=Container([Node(name="node1")]))
        assert dataset.get("thermal", "x") is None

    def test_iter_by_types(self):
        nodes = Container([Node(name="n1"), Node(name="n2")])
        control_blocks = Container([ControlBlock(name="cb1")])

        dataset = AtlasDataset(node=nodes, control_block=control_blocks)

        collected = list(dataset.iter_by_types("node", "control_block"))
        assert collected[:2] == list(nodes)
        assert collected[2:] == list(control_blocks)

    def test_iter_by_types_invalid(self):
        with pytest.raises(ValueError):
            list(AtlasDataset().iter_by_types("invalid"))

    def test_duplicate_names_validation(self):
        with pytest.raises(ValueError):
            AtlasDataset(node=Container([Node(name="dup"), Node(name="dup")]))


class TestAtlasDatasetConversion:
    def test_to_dict(self):
        nodes = Container([Node(name="node1")])
        control_blocks = Container([ControlBlock(name="cb1")])

        dataset = AtlasDataset(node=nodes, control_block=control_blocks)
        result = dataset.to_dict()

        assert list(result["node"]) == list(nodes)
        assert list(result["control_block"]) == list(control_blocks)
        assert "thermal" not in result

    def test_from_dict(self):
        nodes = [Node(name="node1")]
        dataset = AtlasDataset.from_dict({"node": nodes})

        assert isinstance(dataset.node, Container)
        assert list(dataset.node) == nodes

    def test_roundtrip_dict(self):
        dataset1 = AtlasDataset(
            node=Container([Node(name="node1")]),
            control_block=Container([ControlBlock(name="cb1")]),
        )

        dataset2 = AtlasDataset.from_dict(dataset1.to_dict())

        assert len(dataset2) == len(dataset1)
        assert list(dataset2.node) == list(dataset1.node)


class TestAtlasDatasetIO:
    def test_from_directory(self, tmp_path):
        test_dir = tmp_path / "data"
        (test_dir / "objects").mkdir(parents=True)

        pl.DataFrame([{"name": "node1"}]).write_csv(test_dir / "objects" / "node.csv", separator=";")

        dataset = AtlasDataset.from_directory(test_dir)
        assert len(dataset.node) == 1
        assert dataset.node.get("node1")

    def test_to_directory(self, tmp_path):
        dataset = AtlasDataset(node=Container([Node(name="node1")]))
        dataset.to_directory(tmp_path)

        df = pl.read_csv(tmp_path / "objects" / "node.csv", separator=";")
        assert df["name"][0] == "node1"


class TestAtlasDatasetPickling:
    def test_pickle_roundtrip(self, tmp_path):
        dataset = AtlasDataset(
            node=Container([Node(name="node1"), Node(name="node2")]),
            control_block=Container([ControlBlock(name="cb1")]),
        )

        path = tmp_path / "dataset.pkl"
        dataset.to_pickle(path)

        restored = AtlasDataset.from_pickle(path)
        assert len(restored) == 3
        assert restored.node.get("node1")


class TestAtlasDatasetComplexRoundtrip:
    def test_full_roundtrip(self, tmp_path):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node1", control_block=cb, market_area=ma)
        portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)

        inflows = Timeseries.from_values(
            start_date="2024-01-01 00:00:00",
            frequency="1h",
            values=[100, 110, 120],
            timezone="UTC",
        )

        matrix = ForecastingMatrix(
            pl.DataFrame(
                {
                    "time": pl.datetime_range(
                        start=datetime(2024, 1, 1),
                        end=datetime(2024, 1, 1, 2),
                        interval="1h",
                        eager=True,
                    ),
                    "2024-01-01 00:00:00": [1, 2, 3],
                }
            )
        )

        hydro = Hydro(
            name="hydro1",
            node=node,
            portfolio=portfolio,
            inflows=inflows,
            stored_energy=matrix,
            fragment_prices=[10.0, 20.0],
            fragment_volumes=[0.5, 0.5],
        )

        thermal = Thermal(
            name="thermal1",
            node=node,
            portfolio=portfolio,
            installed_capacity=1000,
            minimum_time_on=Duration(hours=2),
            strategy=ThermalStrategy.BASE,
        )

        order = Order(
            name="order1",
            equipment=thermal,
            market_area=ma,
            portfolio=portfolio,
            execution_date=DateTime(2024, 1, 1, 10, 0, tzinfo=Timezone("UTC")),
            start_date=DateTime(2024, 1, 1, 12, 0, tzinfo=Timezone("UTC")),
            end_date=DateTime(2024, 1, 1, 18, 0, tzinfo=Timezone("UTC")),
            order_type=OrderType.Sell,
            product=Product.DayAhead,
            price=50,
            qmax=100,
            qmin=0,
        )

        coupling = OrderCoupling(
            name="c1",
            orders=[order],
            coupling_type=CouplingType.COMPLEMENT,
            complement_direction=ComplementDirection.EqualTo,
            complement_energy=100,
        )

        dataset = AtlasDataset(
            control_block=Container([cb]),
            market_area=Container([ma]),
            node=Container([node]),
            portfolio=Container([portfolio]),
            hydro=Container([hydro]),
            thermal=Container([thermal]),
            order=Container([order]),
            order_coupling=Container([coupling]),
        )

        dataset.to_directory(tmp_path)
        restored = AtlasDataset.from_directory(tmp_path)

        assert restored.hydro.get("hydro1").stored_energy == matrix
        assert restored.order_coupling.get("c1").orders[0].name == "order1"


class TestAtlasDatasetContainerValidator:
    def test_container_validator_accepts_container(self):
        nodes = Container([Node(name="node1")])

        dataset = AtlasDataset(node=nodes)

        assert dataset.node is nodes
        assert dataset.node.get("node1")

    def test_container_validator_wraps_list_into_container(self):
        nodes = [Node(name="node1"), Node(name="node2")]

        dataset = AtlasDataset(node=nodes)  # type: ignore[arg-type]

        assert isinstance(dataset.node, Container)
        assert len(dataset.node) == 2
        assert dataset.node.get("node1")
        assert dataset.node.get("node2")

    def test_container_validator_rejects_invalid_type(self):
        with pytest.raises(TypeError, match="node must be a Container or a list"):
            AtlasDataset(node="not a container")  # type: ignore[arg-type]
