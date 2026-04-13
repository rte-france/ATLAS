"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Test suite for AtlasDataset
"""

from datetime import datetime

import polars as pl
import pytest
from pendulum import DateTime, Duration, Timezone

from atlas.enums import ComplementDirection, CouplingType, OrderType, Product, ThermalStrategy
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.io_utils.container import Container
from atlas.io_utils.utils import diff_business_model, diff_lists, diff_on_other_than_business_model
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.matrix import ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.objects.equipment.hydro import Hydro
from atlas.objects.equipment.load import Load
from atlas.objects.equipment.solar import Solar
from atlas.objects.equipment.storage import Storage
from atlas.objects.equipment.thermal import Thermal
from atlas.objects.equipment.wind import Wind
from atlas.objects.market.critical_branch import CriticalBranch
from atlas.objects.market.market_area import MarketArea
from atlas.objects.market.market_area_ptdf import MarketAreaPtdf
from atlas.objects.market.market_border import MarketBorder
from atlas.objects.market.node_ptdf import NodePtdf
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling
from atlas.objects.market_operator.portfolio import Portfolio
from atlas.objects.network.node import Node
from atlas.objects.network_operator.control_block import ControlBlock


class TestAtlasDatasetBasic:
    def test_empty_dataset_creation(self):
        dataset = AtlasDataset()
        assert len(dataset) == 0
        assert dataset.node.is_empty()
        assert dataset.hydro.is_empty()
        assert "any_object_name" not in dataset

    def test_dataset_with_objects(self):
        cb = ControlBlock(name="cb")
        ma = MarketArea(name="ma", control_block=cb)
        nodes = [
            Node(name="node1", control_block=cb, market_area=ma),
            Node(name="node2", control_block=cb, market_area=ma),
        ]
        dataset = AtlasDataset(node=nodes)

        assert len(dataset) == 2
        assert len(dataset.node) == 2
        assert dataset.node.get("node1")
        assert dataset.node.get("node2")
        assert "node1" in dataset

    def test_attribute_access_empty_attribute(self):
        control_blocks = [ControlBlock(name="cb1")]
        ma = MarketArea(name="ma1", control_block=control_blocks[0])
        nodes = [Node(name="node1", control_block=control_blocks[0], market_area=ma)]

        dataset = AtlasDataset(control_block=control_blocks, node=nodes)

        assert dataset.thermal.is_empty()

    def test_contains_operator(self):
        control_blocks = [ControlBlock(name="cb1")]
        ma = MarketArea(name="ma1", control_block=control_blocks[0])
        nodes = [
            Node(name="node1", control_block=control_blocks[0], market_area=ma),
            Node(name="node2", control_block=control_blocks[0], market_area=ma),
        ]
        dataset = AtlasDataset(node=nodes, control_block=control_blocks)

        assert "node1" in dataset
        assert "node2" in dataset
        assert "cb1" in dataset

        assert "node3" not in dataset
        assert "nonexistent" not in dataset

        assert Node(name="node1", control_block=control_blocks[0], market_area=ma) not in dataset
        assert 123 not in dataset
        assert None not in dataset

    def test_len_operator(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        dataset = AtlasDataset(
            node=[
                Node(name="node1", control_block=cb, market_area=ma),
                Node(name="node2", control_block=cb, market_area=ma),
            ],
            control_block=[cb],
        )
        assert len(dataset) == 3

    def test_repr_and_str(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        dataset = AtlasDataset(node=[Node(name="node1", control_block=cb, market_area=ma)])
        assert "AtlasDataset" in repr(dataset)
        assert "node=1" in repr(dataset)
        assert str(dataset) == repr(dataset)

    def test_iter_operator(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        dataset = AtlasDataset(
            node=[
                Node(name="node1", control_block=cb, market_area=ma),
                Node(name="node2", control_block=cb, market_area=ma),
            ],
            control_block=[cb],
        )

        objects = list(dataset)
        names = {o.name for o in objects}
        assert names == {"node1", "node2", "cb1"}

    def test_iter_operator_empty(self):
        assert list(AtlasDataset()) == []

    def test_iter_operator_multiple_times(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        dataset = AtlasDataset(
            node=[
                Node(name="node1", control_block=cb, market_area=ma),
                Node(name="node2", control_block=cb, market_area=ma),
            ]
        )
        assert sum(1 for _ in dataset) == 2
        assert sum(1 for _ in dataset) == 2


class TestAtlasDatasetLookup:
    def test_get_nonexistent_name(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        dataset = AtlasDataset(node=[Node(name="node1", control_block=cb, market_area=ma)])
        assert dataset.get("node", "nope") is None

    def test_get_nonexistent_type(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        dataset = AtlasDataset(node=[Node(name="node1", control_block=cb, market_area=ma)])
        assert dataset.get("thermal", "x") is None

    def test_iter_by_types(self):
        control_blocks = [ControlBlock(name="cb1")]
        ma = MarketArea(name="ma1", control_block=control_blocks[0])
        nodes = [
            Node(name="n1", control_block=control_blocks[0], market_area=ma),
            Node(name="n2", control_block=control_blocks[0], market_area=ma),
        ]

        dataset = AtlasDataset(node=nodes, control_block=control_blocks)

        collected = list(dataset.iter_by_types("node", "control_block"))
        assert collected[:2] == list(nodes)
        assert collected[2:] == list(control_blocks)

    def test_iter_by_types_invalid(self):
        with pytest.raises(ValueError):
            list(AtlasDataset().iter_by_types("invalid"))

    def test_duplicate_names_validation(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        with pytest.raises(ValueError):
            AtlasDataset(
                node=[
                    Node(name="dup", control_block=cb, market_area=ma),
                    Node(name="dup", control_block=cb, market_area=ma),
                ]
            )

    def test_iter_by_equipments_empty(self):
        dataset = AtlasDataset()
        equipments = list(dataset.iter_by_equipments())
        assert equipments == []

    def test_iter_by_equipments_single_type(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node1", control_block=cb, market_area=ma)
        portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)
        thermal = Thermal(name="plant1", node=node, portfolio=portfolio)
        dataset = AtlasDataset(thermal=[thermal])
        equipments = list(dataset.iter_by_equipments())
        assert len(equipments) == 1
        assert equipments[0] == thermal

    def test_iter_by_equipments_multiple_types(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node1", control_block=cb, market_area=ma)
        portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)
        thermal = Thermal(name="plant1", node=node, portfolio=portfolio)
        solar = Solar(name="solar1", node=node, portfolio=portfolio)
        wind = Wind(name="wind1", node=node, portfolio=portfolio)
        hydro = Hydro(name="hydro1", node=node, portfolio=portfolio)
        load = Load(name="load1", node=node, portfolio=portfolio)
        storage = Storage(name="storage1", node=node, portfolio=portfolio)

        dataset = AtlasDataset(
            thermal=[thermal],
            solar=[solar],
            wind=[wind],
            hydro=[hydro],
            load=[load],
            storage=[storage],
        )

        equipments = list(dataset.iter_by_equipments())
        assert len(equipments) == 6
        equipment_names = {eq.name for eq in equipments}
        assert equipment_names == {"plant1", "solar1", "wind1", "hydro1", "load1", "storage1"}

    def test_iter_by_equipments_multiple_of_same_type(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node1", control_block=cb, market_area=ma)
        portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)
        thermal1 = Thermal(name="plant1", node=node, portfolio=portfolio)
        thermal2 = Thermal(name="plant2", node=node, portfolio=portfolio)
        thermal3 = Thermal(name="plant3", node=node, portfolio=portfolio)
        dataset = AtlasDataset(thermal=[thermal1, thermal2, thermal3])

        equipments = list(dataset.iter_by_equipments())
        assert len(equipments) == 3
        assert equipments[0] == thermal1
        assert equipments[1] == thermal2
        assert equipments[2] == thermal3

    def test_iter_by_equipments_excludes_non_equipment(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node1", control_block=cb, market_area=ma)
        portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)
        thermal = Thermal(name="plant1", node=node, portfolio=portfolio)

        dataset = AtlasDataset(
            thermal=[thermal],
            node=[node],
            control_block=[cb],
            market_area=[ma],
        )

        equipments = list(dataset.iter_by_equipments())
        assert len(equipments) == 1
        assert equipments[0] == thermal

    def test_iter_by_equipments_multiple_times(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node1", control_block=cb, market_area=ma)
        portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)
        thermal = Thermal(name="plant1", node=node, portfolio=portfolio)
        solar = Solar(name="solar1", node=node, portfolio=portfolio)
        dataset = AtlasDataset(thermal=[thermal], solar=[solar])

        # First iteration
        equipments1 = list(dataset.iter_by_equipments())
        assert len(equipments1) == 2

        # Second iteration should work the same
        equipments2 = list(dataset.iter_by_equipments())
        assert len(equipments2) == 2
        assert equipments1 == equipments2


class TestAtlasDatasetConversion:
    def test_to_dict(self):
        control_blocks = [ControlBlock(name="cb1")]
        ma = MarketArea(name="ma1", control_block=control_blocks[0])
        nodes = [Node(name="node1", control_block=control_blocks[0], market_area=ma)]

        dataset = AtlasDataset(node=nodes, control_block=control_blocks)
        result = dataset.to_dict()

        assert list(result["node"]) == list(nodes)
        assert list(result["control_block"]) == list(control_blocks)
        assert "thermal" not in result

    def test_from_dict(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        nodes = [Node(name="node1", control_block=cb, market_area=ma)]
        dataset = AtlasDataset.from_dict({"node": nodes})

        assert isinstance(dataset.node, Container)
        assert list(dataset.node) == nodes

    def test_roundtrip_dict_comprehensive(self):
        """Test dict roundtrip with comprehensive attribute verification."""
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node1", control_block=cb, market_area=ma)
        portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)

        thermal = Thermal(
            name="thermal1",
            node=node,
            portfolio=portfolio,
            installed_capacity=1000,
            minimum_time_on=Duration(hours=2),
            minimum_time_off=Duration(hours=1),
            strategy=ThermalStrategy.BASE,
            outage_probability=0.05,
        )

        dataset1 = AtlasDataset(
            control_block=[cb],
            market_area=[ma],
            node=[node],
            portfolio=[portfolio],
            thermal=[thermal],
        )

        dataset2 = AtlasDataset.from_dict(dataset1.to_dict())

        # Verify counts
        assert len(dataset2) == len(dataset1)
        assert len(dataset2.thermal) == 1
        assert len(dataset2.node) == 1
        assert len(dataset2.control_block) == 1
        assert len(dataset2.market_area) == 1
        assert len(dataset2.portfolio) == 1

        # Verify object attributes
        thermal2 = dataset2.thermal.get("thermal1")
        assert thermal2 is not None
        assert thermal2.name == thermal.name
        assert thermal2.installed_capacity == thermal.installed_capacity
        assert thermal2.minimum_time_on == thermal.minimum_time_on
        assert thermal2.minimum_time_off == thermal.minimum_time_off
        assert thermal2.strategy == thermal.strategy
        assert thermal2.outage_probability == thermal.outage_probability

        # Verify relationships are preserved (by name)
        assert thermal2.node.name == node.name
        assert thermal2.portfolio.name == portfolio.name
        assert thermal2.node.control_block.name == cb.name
        assert thermal2.node.market_area.name == ma.name


class TestAtlasDatasetIO:
    def test_from_directory(self, tmp_path):
        test_dir = tmp_path / "data"
        (test_dir / "objects").mkdir(parents=True)

        # Create control_block and market_area CSVs first
        pl.DataFrame([{"name": "cb1"}]).write_csv(test_dir / "objects" / "control_block.csv", separator=";")
        pl.DataFrame([{"name": "ma1", "control_block": "cb1"}]).write_csv(
            test_dir / "objects" / "market_area.csv", separator=";"
        )
        pl.DataFrame([{"name": "node1", "control_block": "cb1", "market_area": "ma1"}]).write_csv(
            test_dir / "objects" / "node.csv", separator=";"
        )

        dataset = AtlasDataset.from_directory(test_dir)
        assert len(dataset.node) == 1
        assert dataset.node.get("node1")

    def test_to_directory(self, tmp_path):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        dataset = AtlasDataset(node=[Node(name="node1", control_block=cb, market_area=ma)])
        dataset.to_directory(tmp_path)

        df = pl.read_csv(tmp_path / "objects" / "node.csv", separator=";")
        assert df["name"][0] == "node1"


class TestAtlasDatasetPickling:
    def test_pickle_roundtrip(self, tmp_path):
        """Test pickle roundtrip with comprehensive verification."""
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node1 = Node(name="node1", control_block=cb, market_area=ma)
        node2 = Node(name="node2", control_block=cb, market_area=ma)
        portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)

        inflows = Timeseries.from_values(
            start_date="2024-01-01 00:00:00",
            frequency="1h",
            values=[100.0, 200.0, 300.0],
            timezone="UTC",
        )

        hydro = Hydro(
            name="hydro1",
            node=node1,
            portfolio=portfolio,
            inflows=inflows,
            fragment_prices=[10.0, 20.0],
            fragment_volumes=[0.5, 0.5],
        )

        dataset = AtlasDataset(
            node=[node1, node2],
            control_block=[cb],
            market_area=[ma],
            portfolio=[portfolio],
            hydro=[hydro],
        )

        path = tmp_path / "dataset.pkl"
        dataset.to_pickle(path)

        restored = AtlasDataset.from_pickle(path)

        # Verify counts
        assert len(restored) == len(dataset)
        assert len(restored.node) == 2
        assert len(restored.hydro) == 1

        # Verify objects exist
        assert restored.node.get("node1") is not None
        assert restored.node.get("node2") is not None
        assert restored.hydro.get("hydro1") is not None

        # Verify hydro attributes
        hydro_restored = restored.hydro.get("hydro1")
        assert hydro_restored.fragment_prices == hydro.fragment_prices
        assert hydro_restored.fragment_volumes == hydro.fragment_volumes

        # Verify timeseries data
        assert hydro_restored.inflows == inflows
        assert hydro_restored.inflows.values == [100.0, 200.0, 300.0]

        # Verify relationships
        assert hydro_restored.node.name == node1.name
        assert hydro_restored.portfolio.name == portfolio.name


class TestAtlasDatasetComplexRoundtrip:
    def test_full_roundtrip(self, tmp_path):
        """Test directory roundtrip with comprehensive verification of all attributes and relationships."""
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
            outage_probability=0.02,
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
            control_block=[cb],
            market_area=[ma],
            node=[node],
            portfolio=[portfolio],
            hydro=[hydro],
            thermal=[thermal],
            order=[order],
            order_coupling=[coupling],
        )

        dataset.to_directory(tmp_path)
        restored = AtlasDataset.from_directory(tmp_path)

        # Verify counts
        assert len(restored) == len(dataset)
        assert len(restored.hydro) == 1
        assert len(restored.thermal) == 1
        assert len(restored.order) == 1
        assert len(restored.order_coupling) == 1

        # Verify hydro with math objects
        hydro_restored = restored.hydro.get("hydro1")
        assert hydro_restored is not None
        assert hydro_restored.stored_energy == matrix
        assert hydro_restored.inflows == inflows
        assert hydro_restored.inflows.values == [100, 110, 120]
        assert hydro_restored.fragment_prices == [10.0, 20.0]
        assert hydro_restored.fragment_volumes == [0.5, 0.5]
        assert hydro_restored.node.name == node.name
        assert hydro_restored.portfolio.name == portfolio.name

        # Verify thermal with all attributes
        thermal_restored = restored.thermal.get("thermal1")
        assert thermal_restored is not None
        assert thermal_restored.installed_capacity == 1000
        assert thermal_restored.minimum_time_on == Duration(hours=2)
        assert thermal_restored.strategy == ThermalStrategy.BASE
        assert thermal_restored.outage_probability == 0.02
        assert thermal_restored.node.name == node.name
        assert thermal_restored.portfolio.name == portfolio.name

        # Verify order with all datetime and enum attributes
        order_restored = restored.order.get("order1")
        assert order_restored is not None
        assert order_restored.execution_date == DateTime(2024, 1, 1, 10, 0, tzinfo=Timezone("UTC"))
        assert order_restored.start_date == DateTime(2024, 1, 1, 12, 0, tzinfo=Timezone("UTC"))
        assert order_restored.end_date == DateTime(2024, 1, 1, 18, 0, tzinfo=Timezone("UTC"))
        assert order_restored.order_type == OrderType.Sell
        assert order_restored.product == Product.DayAhead
        assert order_restored.price == 50
        assert order_restored.qmax == 100
        assert order_restored.qmin == 0
        assert order_restored.equipment.name == thermal.name
        assert order_restored.market_area.name == ma.name
        assert order_restored.portfolio.name == portfolio.name

        # Verify order coupling with relationships
        coupling_restored = restored.order_coupling.get("c1")
        assert coupling_restored is not None
        assert len(coupling_restored.orders) == 1
        assert coupling_restored.orders[0].name == "order1"
        assert coupling_restored.coupling_type == CouplingType.COMPLEMENT
        assert coupling_restored.complement_direction == ComplementDirection.EqualTo
        assert coupling_restored.complement_energy == 100

    def test_directory_roundtrip_with_multiple_equipment_types(self, tmp_path):
        """Test directory roundtrip with multiple equipment types and verify all are preserved."""

        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node1", control_block=cb, market_area=ma)
        portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)

        # Create various equipment types
        solar = Solar(
            name="solar1",
            node=node,
            portfolio=portfolio,
            installed_capacity=500,
        )

        wind = Wind(
            name="wind1",
            node=node,
            portfolio=portfolio,
            installed_capacity=750,
        )

        storage = Storage(
            name="storage1",
            node=node,
            portfolio=portfolio,
            charge_efficiency=0.85,
            discharge_efficiency=0.90,
        )

        load = Load(
            name="load1",
            node=node,
            portfolio=portfolio,
        )

        dataset = AtlasDataset(
            control_block=[cb],
            market_area=[ma],
            node=[node],
            portfolio=[portfolio],
            solar=[solar],
            wind=[wind],
            storage=[storage],
            load=[load],
        )

        dataset.to_directory(tmp_path)
        restored = AtlasDataset.from_directory(tmp_path)

        # Verify all equipment types are restored
        assert len(restored.solar) == 1
        assert len(restored.wind) == 1
        assert len(restored.storage) == 1
        assert len(restored.load) == 1

        # Verify solar attributes
        solar_restored = restored.solar.get("solar1")
        assert solar_restored is not None
        assert solar_restored.installed_capacity == 500
        assert solar_restored.node.name == node.name

        # Verify wind attributes
        wind_restored = restored.wind.get("wind1")
        assert wind_restored is not None
        assert wind_restored.installed_capacity == 750
        assert wind_restored.node.name == node.name

        # Verify storage attributes
        storage_restored = restored.storage.get("storage1")
        assert storage_restored is not None
        assert storage_restored.charge_efficiency == 0.85
        assert storage_restored.discharge_efficiency == 0.90
        assert storage_restored.node.name == node.name

        # Verify load
        load_restored = restored.load.get("load1")
        assert load_restored is not None
        assert load_restored.node.name == node.name

    def test_roundtrip_preserves_empty_containers(self, tmp_path):
        """Verify that empty containers remain empty after roundtrip."""
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node1", control_block=cb, market_area=ma)

        dataset = AtlasDataset(
            control_block=[cb],
            market_area=[ma],
            node=[node],
        )

        dataset.to_directory(tmp_path)
        restored = AtlasDataset.from_directory(tmp_path)

        # Verify empty containers are still empty
        assert restored.thermal.is_empty()
        assert restored.hydro.is_empty()
        assert restored.solar.is_empty()
        assert len(restored.node) == 1


class TestAtlasDatasetContainerValidator:
    def test_container_validator_accepts_container(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        nodes = Container([Node(name="node1", control_block=cb, market_area=ma)])

        dataset = AtlasDataset(node=nodes)

        assert dataset.node is nodes
        assert dataset.node.get("node1")

    def test_container_validator_wraps_list_into_container(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        nodes = [
            Node(name="node1", control_block=cb, market_area=ma),
            Node(name="node2", control_block=cb, market_area=ma),
        ]

        dataset = AtlasDataset(node=nodes)  # type: ignore[arg-type]

        assert isinstance(dataset.node, Container)
        assert len(dataset.node) == 2
        assert dataset.node.get("node1")
        assert dataset.node.get("node2")

    def test_container_validator_rejects_invalid_type(self):
        with pytest.raises(TypeError, match="node must be a Container or a list"):
            AtlasDataset(node="not a container")  # type: ignore[arg-type]


class TestAtlasDatasetEq:
    def test_two_empty_datasets_are_equal(self):
        assert AtlasDataset() == AtlasDataset()

    def test_same_objects_are_equal(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node_1 = Node(name="node", control_block=cb, market_area=ma)
        node_2 = Node(name="node", control_block=cb, market_area=ma)
        ds1 = AtlasDataset(node=[node_1])
        ds2 = AtlasDataset(node=[node_2])
        assert ds1 == ds2

    def test_different_node_names_are_not_equal(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node_1 = Node(name="node1", control_block=cb, market_area=ma)
        node_2 = Node(name="node2", control_block=cb, market_area=ma)
        ds1 = AtlasDataset(node=[node_1])
        ds2 = AtlasDataset(node=[node_2])
        assert ds1 != ds2

    def test_different_counts_are_not_equal(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node_1 = Node(name="node1", control_block=cb, market_area=ma)
        node_2 = Node(name="node2", control_block=cb, market_area=ma)
        ds1 = AtlasDataset(node=[node_1])
        ds2 = AtlasDataset(node=[node_1, node_2])
        assert ds1 != ds2

    def test_extra_object_type_makes_not_equal(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node", control_block=cb, market_area=ma)
        thermal_node = Node(name="thermal_node", control_block=cb, market_area=ma)
        portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)
        thermal = Thermal(name="thermal", node=thermal_node, portfolio=portfolio)
        ds1 = AtlasDataset(node=[node])
        ds2 = AtlasDataset(node=[node], thermal=[thermal])
        assert ds1 != ds2

    def test_eq_with_non_atlas_dataset_returns_not_implemented(self):
        ds = AtlasDataset()
        result = ds.__eq__("not a dataset")
        assert result is NotImplemented

    def test_eq_is_symmetric(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node", control_block=cb, market_area=ma)
        ds1 = AtlasDataset(node=[node])
        ds2 = AtlasDataset(node=[node])
        assert ds1 == ds2
        assert ds2 == ds1

    def test_eq_with_same_name_different_attributes(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node1", control_block=cb, market_area=ma)
        portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)
        th1 = Thermal(name="th", installed_capacity=100, node=node, portfolio=portfolio)
        th2 = Thermal(name="th", installed_capacity=990, node=node, portfolio=portfolio)
        ds1 = AtlasDataset(thermal=[th1])
        ds2 = AtlasDataset(thermal=[th2])
        assert ds1 != ds2

    def test_eq_with_same_name_same_attribute(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node1", control_block=cb, market_area=ma)
        portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)
        th1 = Thermal(name="th", installed_capacity=100, node=node, portfolio=portfolio)
        th2 = Thermal(name="th", installed_capacity=100, node=node, portfolio=portfolio)
        ds1 = AtlasDataset(thermal=[th1])
        ds2 = AtlasDataset(thermal=[th2])
        assert ds1 == ds2


@pytest.fixture()
def simple_timeseries():
    return Timeseries.from_values(
        start_date="2024-01-01 00:00:00",
        frequency="1h",
        values=[10.0, 20.0, 30.0],
        timezone="UTC",
    )


class TestAtlasDatasetDiff:
    def test_identical_datasets_produce_empty_diff(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        ds = AtlasDataset(node=[Node(name="node", control_block=cb, market_area=ma)])
        assert ds.diff(ds) == {}

    def test_object_only_in_self(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        ds1 = AtlasDataset(node=[Node(name="node", control_block=cb, market_area=ma)])
        ds2 = AtlasDataset()
        result = ds1.diff(ds2)
        assert "node" in result["node"]["only_in_self"]
        assert result["node"]["only_in_other"] == []

    def test_object_only_in_other(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        ds1 = AtlasDataset()
        ds2 = AtlasDataset(node=[Node(name="node", control_block=cb, market_area=ma)])
        result = ds1.diff(ds2)
        assert "node" in result["node"]["only_in_other"]
        assert result["node"]["only_in_self"] == []

    def test_modified_scalar_attribute(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node1", control_block=cb, market_area=ma)
        portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)
        th1 = Thermal(name="th", installed_capacity=100, node=node, portfolio=portfolio)
        th2 = Thermal(name="th", installed_capacity=999, node=node, portfolio=portfolio)
        result = AtlasDataset(thermal=[th1]).diff(AtlasDataset(thermal=[th2]))
        assert result["thermal"]["modified"]["th"]["installed_capacity"] == {"self": 100, "other": 999}

    def test_modified_timeseries_attribute(self, simple_timeseries):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node1", control_block=cb, market_area=ma)
        portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)
        ts_other = Timeseries.from_values(
            start_date="2024-01-01 00:00:00", frequency="1h", values=[99.0, 99.0, 99.0], timezone="UTC"
        )
        result = AtlasDataset(hydro=[Hydro(name="h", inflows=simple_timeseries, node=node, portfolio=portfolio)]).diff(
            AtlasDataset(hydro=[Hydro(name="h", inflows=ts_other, node=node, portfolio=portfolio)])
        )
        assert "inflows" in result["hydro"]["modified"]["h"]

    def test_modified_enum_field(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node1", control_block=cb, market_area=ma)
        portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)
        th1 = Thermal(name="th", strategy=ThermalStrategy.BASE, node=node, portfolio=portfolio)
        th2 = Thermal(name="th", strategy=ThermalStrategy.PEAK, node=node, portfolio=portfolio)
        result = AtlasDataset(thermal=[th1]).diff(AtlasDataset(thermal=[th2]))
        assert "strategy" in result["thermal"]["modified"]["th"]

    def test_modified_duration_field(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node1", control_block=cb, market_area=ma)
        portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)
        th1 = Thermal(name="th", minimum_time_on=Duration(hours=1), node=node, portfolio=portfolio)
        th2 = Thermal(name="th", minimum_time_on=Duration(hours=6), node=node, portfolio=portfolio)
        result = AtlasDataset(thermal=[th1]).diff(AtlasDataset(thermal=[th2]))
        assert "minimum_time_on" in result["thermal"]["modified"]["th"]

    def test_multiple_types_reported_simultaneously(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node1", control_block=cb, market_area=ma)
        portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)
        atlas_1 = AtlasDataset(
            node=[Node(name="n_1", control_block=cb, market_area=ma)],
            thermal=[Thermal(name="th", installed_capacity=100, node=node, portfolio=portfolio)],
        )
        atlas_2 = AtlasDataset(
            node=[Node(name="n_2", control_block=cb, market_area=ma)],
            thermal=[Thermal(name="th", installed_capacity=500, node=node, portfolio=portfolio)],
        )
        result = atlas_1.diff(atlas_2)
        assert "node" in result
        assert "thermal" in result

    def test_common_unchanged_object_not_in_modified(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        n_1 = Node(name="n_1", control_block=cb, market_area=ma)
        n_2 = Node(name="n_2", control_block=cb, market_area=ma)
        result = AtlasDataset(node=[n_1, n_2]).diff(AtlasDataset(node=[n_1]))
        assert "n_1" not in result.get("node", {}).get("modified", {})
        assert "n_2" in result["node"]["only_in_self"]


class TestDiffBusinessModel:
    def test_identical_objects_return_empty_dict(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node", control_block=cb, market_area=ma)
        assert diff_business_model(node, node) == {}

    def test_scalar_field_difference_detected(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node1", control_block=cb, market_area=ma)
        portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)
        th1 = Thermal(name="th", installed_capacity=100, node=node, portfolio=portfolio)
        th2 = Thermal(name="th", installed_capacity=500, node=node, portfolio=portfolio)
        result = diff_business_model(th1, th2)
        assert result["installed_capacity"] == {"self": 100, "other": 500}

    def test_nested_business_model_difference(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node_1 = Node(name="node_1", control_block=cb, market_area=ma)
        node_2 = Node(name="node_2", control_block=cb, market_area=ma)
        portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)
        th1 = Thermal(name="th", node=node_1, portfolio=portfolio)
        th2 = Thermal(name="th", node=node_2, portfolio=portfolio)
        result = diff_business_model(th1, th2)
        assert result["node"]["type"] == "nested"
        assert result["node"]["object_name"] in ("node_1", "node_2")

    def test_circular_reference_does_not_loop(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node", control_block=cb, market_area=ma)
        visited: set[tuple[int, int]] = {(id(node), id(node))}
        assert diff_business_model(node, node, _visited=visited) == {}

    def test_timeseries_field_difference_detected(self, simple_timeseries):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node1", control_block=cb, market_area=ma)
        portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)
        ts_other = Timeseries.from_values(
            start_date="2024-01-01 00:00:00", frequency="1h", values=[0.0, 0.0, 0.0], timezone="UTC"
        )
        result = diff_business_model(
            Hydro(name="h", inflows=simple_timeseries, node=node, portfolio=portfolio),
            Hydro(name="h", inflows=ts_other, node=node, portfolio=portfolio),
        )
        assert "inflows" in result

    def test_only_differing_fields_are_returned(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node1", control_block=cb, market_area=ma)
        portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)
        th1 = Thermal(name="th", installed_capacity=100, outage_probability=0.05, node=node, portfolio=portfolio)
        th2 = Thermal(name="th", installed_capacity=999, outage_probability=0.05, node=node, portfolio=portfolio)
        result = diff_business_model(th1, th2)
        assert "installed_capacity" in result
        assert "outage_probability" not in result


class TestDiffOnOtherThanBusinessModel:
    def test_equal_scalar_returns_none(self):
        assert diff_on_other_than_business_model(42, 42) is None

    def test_different_int_returns_diff(self):
        assert diff_on_other_than_business_model(1, 2) == {"self": 1, "other": 2}

    def test_different_str_returns_diff(self):
        assert diff_on_other_than_business_model("a", "b") == {"self": "a", "other": "b"}

    def test_different_bool_returns_diff(self):
        assert diff_on_other_than_business_model(True, False) == {"self": True, "other": False}

    def test_different_lists_delegates_to_diff_lists(self):
        result = diff_on_other_than_business_model([1, 2], [1, 99])
        assert "1" in result

    def test_equal_timeseries_returns_none(self, simple_timeseries):
        assert diff_on_other_than_business_model(simple_timeseries, simple_timeseries) is None

    def test_different_timeseries_returns_changed(self):
        ts1 = Timeseries.from_values(
            start_date="2024-01-01 00:00:00", frequency="1h", values=[1.0, 2.0], timezone="UTC"
        )
        ts2 = Timeseries.from_values(
            start_date="2024-01-01 00:00:00", frequency="1h", values=[9.0, 2.0], timezone="UTC"
        )
        assert "changed" in diff_on_other_than_business_model(ts1, ts2)

    def test_different_custom_object_returns_changed(self):
        class MyObj:
            def __init__(self, v):
                self.v = v

            def __eq__(self, other):
                return self.v == other.v

        assert diff_on_other_than_business_model(MyObj(1), MyObj(2)) == {"changed": "not-serializable yet"}

    def test_exception_in_eq_returns_error(self):
        class Broken:
            def __eq__(self, other):
                raise RuntimeError("broken")

        assert diff_on_other_than_business_model(Broken(), Broken()) == {"error": "Couldn't check diff"}

    def test_none_vs_value_returns_changed(self):
        assert diff_on_other_than_business_model(None, 42) is not None


class TestDiffLists:
    def test_different_lengths_returns_list_length_diff(self):
        result = diff_lists([1, 2, 3], [1, 2])
        assert result == {"type": "list_length", "self": 3, "other": 2}

    def test_equal_lists_returns_none(self):
        assert diff_lists([1, 2, 3], [1, 2, 3]) is None

    def test_single_differing_element(self):
        result = diff_lists([1, 2, 3], [1, 99, 3])
        assert result["1"] == {"self": 2, "other": 99}
        assert "0" not in result
        assert "2" not in result

    def test_business_model_elements_identical_returns_none(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node", control_block=cb, market_area=ma)
        assert diff_lists([node], [node]) is None

    def test_business_model_elements_different_detected(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        result = diff_lists(
            [Node(name="node_1", control_block=cb, market_area=ma)],
            [Node(name="node_2", control_block=cb, market_area=ma)],
        )
        assert result["0"]["type"] == "nested"

    def test_only_differing_element_reported(self):
        cb = ControlBlock(name="cb1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node", control_block=cb, market_area=ma)
        result = diff_lists(
            [node, Node(name="node_1", control_block=cb, market_area=ma)],
            [node, Node(name="node_2", control_block=cb, market_area=ma)],
        )
        assert "0" not in result
        assert "1" in result


@pytest.fixture
def dataset():
    ds = AtlasDataset()
    cb = ControlBlock(name="cb1")
    ma1 = MarketArea(name="ma1", control_block=cb)
    ma2 = MarketArea(name="ma2", control_block=cb)
    ds.order.add(Order(name="order_1", price=10, market_area=ma1))
    ds.order.add(Order(name="order_2", price=50, market_area=ma2))
    ds.market_area.add(ma1)
    ds.market_area.add(ma2)
    ds.node.add(Node(name="NodeA", control_block=cb, market_area=ma1))
    ds.node.add(Node(name="NodeB", control_block=cb, market_area=ma2))
    return ds


class TestFilterDataset:
    def test_include_types_only(self, dataset):
        subset = dataset.filter_dataset(included_types=["order", "market_area"])
        data = subset.to_dict()
        assert "order" in data
        assert "market_area" in data
        assert "node" not in data
        assert len(subset.order) == 2
        assert len(subset.market_area) == 2

    def test_filter_only(self, dataset):
        subset = dataset.filter_dataset(filters={"node": lambda n: n.name.startswith("NodeA")})
        nodes = subset.node.all()
        assert len(nodes) == 1
        assert nodes[0].name == "NodeA"
        # Only node key should be present
        data_keys = subset.to_dict().keys()
        assert "node" in data_keys
        assert "order" not in data_keys

    def test_include_and_filter(self, dataset):
        subset = dataset.filter_dataset(
            included_types=["order", "node"], filters={"node": lambda n: n.name.startswith("NodeB")}
        )
        data = subset.to_dict()
        # Orders included fully because node has filter
        assert "order" in data
        assert len(subset.order) == 2
        # Nodes filtered
        nodes = subset.node.all()
        assert len(nodes) == 1
        assert nodes[0].name == "NodeB"

    def test_filter_takes_precedence_over_included(self, dataset):
        # Node is in included_types but has a filter → should be filtered
        subset = dataset.filter_dataset(included_types=["node"], filters={"node": lambda n: n.name.startswith("NodeB")})
        nodes = subset.node.all()
        assert len(nodes) == 1
        assert nodes[0].name == "NodeB"

    def test_empty_included_types_and_filters(self, dataset):
        subset = dataset.filter_dataset()
        assert subset.to_dict() == {}

    def test_unknown_type_included_types(self, dataset):
        subset = dataset.filter_dataset(included_types=["unknown_type"])
        assert subset.to_dict() == {}

    def test_unknown_type_in_filters(self, dataset):
        subset = dataset.filter_dataset(filters={"unknown_type": lambda x: True})
        assert subset.to_dict() == {}

    def test_combined_filters_and_included_types(self, dataset):
        # Include orders, filter orders by price > 20
        subset = dataset.filter_dataset(included_types=["order"], filters={"order": lambda o: o.price > 20})
        orders = subset.order.all()
        assert len(orders) == 1
        assert orders[0].name == "order_2"


def test_filter_equipments_keeps_only_selected():
    cb = ControlBlock(name="cb1")
    ma = MarketArea(name="ma1", control_block=cb)
    node = Node(name="node1", control_block=cb, market_area=ma)
    portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)
    t1 = Thermal(name="plant_1", node=node, portfolio=portfolio)
    t2 = Thermal(name="plant_2", node=node, portfolio=portfolio)
    t3 = Thermal(name="plant_3", node=node, portfolio=portfolio)

    dataset = AtlasDataset(thermal=[t1, t2, t3])

    filtered = dataset.filter_equipments(["plant_1", "plant_3"])

    remaining_names = [e.name for e in filtered.thermal]

    assert set(remaining_names) == {"plant_1", "plant_3"}
    assert "plant_2" not in remaining_names


def test_filter_does_not_modify_original_dataset():
    cb = ControlBlock(name="cb1")
    ma = MarketArea(name="ma1", control_block=cb)
    node = Node(name="node1", control_block=cb, market_area=ma)
    portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)
    t1 = Thermal(name="plant_1", node=node, portfolio=portfolio)
    t2 = Thermal(name="plant_2", node=node, portfolio=portfolio)

    dataset = AtlasDataset(thermal=[t1, t2])

    filtered = dataset.filter_equipments(["plant_1"])

    assert len(dataset.thermal) == 2  # original unchanged
    assert len(filtered.thermal) == 1


class TestFilterZones:
    """Test suite for the filter_zones method covering bug fixes and new features."""

    @pytest.fixture
    def multi_zone_dataset(self):
        """Create a dataset with multiple zones and various interconnected objects."""
        # Control blocks (zones)
        cb_fr = ControlBlock(name="FR")
        cb_de = ControlBlock(name="DE")
        cb_be = ControlBlock(name="BE")

        ma_fr = MarketArea(name="ma_FR", control_block=cb_fr)
        ma_de = MarketArea(name="ma_DE", control_block=cb_de)
        ma_be = MarketArea(name="ma_BE", control_block=cb_be)

        node_fr1 = Node(name="node_FR1", control_block=cb_fr, market_area=ma_fr)
        node_fr2 = Node(name="node_FR2", control_block=cb_fr, market_area=ma_fr)
        node_de = Node(name="node_DE", control_block=cb_de, market_area=ma_de)
        node_be = Node(name="node_BE", control_block=cb_be, market_area=ma_be)

        border_fr_de = MarketBorder(
            name="border_FR_DE",
            uphill_control_block=cb_fr,
            downhill_control_block=cb_de,
            uphill_market_area=ma_fr,
            downhill_market_area=ma_de,
        )
        border_de_be = MarketBorder(
            name="border_DE_BE",
            uphill_control_block=cb_de,
            downhill_control_block=cb_be,
            uphill_market_area=ma_de,
            downhill_market_area=ma_be,
        )
        border_fr_be = MarketBorder(
            name="border_FR_BE",
            uphill_control_block=cb_fr,
            downhill_control_block=cb_be,
            uphill_market_area=ma_fr,
            downhill_market_area=ma_be,
        )

        cb_fr_de = CriticalBranch(
            name="cb_FR_DE",
            uphill_node=node_fr1,
            downhill_node=node_de,
            market_area_ptdf=[],
            node_ptdf=[],
        )
        cb_de_be = CriticalBranch(
            name="cb_DE_BE",
            uphill_node=node_de,
            downhill_node=node_be,
            market_area_ptdf=[],
            node_ptdf=[],
        )

        portfolio_fr = Portfolio(name="portfolio_FR", control_block=cb_fr, market_area=ma_fr)
        portfolio_de = Portfolio(name="portfolio_DE", control_block=cb_de, market_area=ma_de)
        portfolio_be = Portfolio(name="portfolio_BE", control_block=cb_be, market_area=ma_be)

        thermal_fr = Thermal(name="thermal_FR", node=node_fr1, portfolio=portfolio_fr)
        hydro_fr = Hydro(name="hydro_FR", node=node_fr2, portfolio=portfolio_fr)
        thermal_de = Thermal(name="thermal_DE", node=node_de, portfolio=portfolio_de)
        solar_be = Solar(name="solar_BE", node=node_be, portfolio=portfolio_be)

        order_fr = Order(name="order_FR", market_area=ma_fr, portfolio=portfolio_fr, price=50)
        order_de = Order(name="order_DE", market_area=ma_de, portfolio=portfolio_de, price=60)

        coupling_1 = OrderCoupling(
            name="coupling_1",
            orders=[order_fr, order_de],
            coupling_type=CouplingType.COMPLEMENT,
        )

        dataset = AtlasDataset(
            control_block=[cb_fr, cb_de, cb_be],
            market_area=[ma_fr, ma_de, ma_be],
            node=[node_fr1, node_fr2, node_de, node_be],
            market_border=[border_fr_de, border_de_be, border_fr_be],
            critical_branch=[cb_fr_de, cb_de_be],
            portfolio=[portfolio_fr, portfolio_de, portfolio_be],
            thermal=[thermal_fr, thermal_de],
            hydro=[hydro_fr],
            solar=[solar_be],
            order=[order_fr, order_de],
            order_coupling=[coupling_1],
        )

        return dataset

    def test_filter_single_zone_basic(self, multi_zone_dataset):
        """Test filtering to a single zone includes correct objects."""
        filtered = multi_zone_dataset.filter_zones(["FR"])

        # Should include FR control block
        assert len(filtered.control_block) == 1
        assert "FR" in filtered.control_block

        # Should include FR market area
        assert len(filtered.market_area) == 1
        assert "ma_FR" in filtered.market_area

        # Should include FR nodes
        assert len(filtered.node) == 2
        assert "node_FR1" in filtered.node
        assert "node_FR2" in filtered.node

        # Should not include DE or BE nodes
        assert "node_DE" not in filtered.node
        assert "node_BE" not in filtered.node

    def test_filter_zone_equipment_filtering(self, multi_zone_dataset):
        """Test that equipment is correctly filtered based on node's control block."""
        filtered = multi_zone_dataset.filter_zones(["FR"])

        # Should include FR equipment
        assert len(filtered.thermal) == 1
        assert "thermal_FR" in filtered.thermal
        assert len(filtered.hydro) == 1
        assert "hydro_FR" in filtered.hydro

        # Should not include DE or BE equipment
        assert "thermal_DE" not in filtered.thermal
        assert "solar_BE" not in filtered.solar

    def test_filter_zone_portfolios(self, multi_zone_dataset):
        """Test that portfolios are correctly filtered."""
        filtered = multi_zone_dataset.filter_zones(["FR"])

        assert len(filtered.portfolio) == 1
        assert "portfolio_FR" in filtered.portfolio
        assert "portfolio_DE" not in filtered.portfolio

    def test_filter_zone_orders(self, multi_zone_dataset):
        """Test that orders are correctly filtered by market area's control block."""
        filtered = multi_zone_dataset.filter_zones(["FR"])

        assert len(filtered.order) == 1
        assert "order_FR" in filtered.order
        assert "order_DE" not in filtered.order

    def test_filter_zone_order_couplings(self, multi_zone_dataset):
        """Test that order couplings are included if ANY order belongs to filtered zones."""
        filtered = multi_zone_dataset.filter_zones(["FR"])

        # Should include coupling because order_FR is in the coupling
        assert len(filtered.order_coupling) == 1
        assert "coupling_1" in filtered.order_coupling

    def test_filter_zone_borders_default_both_endpoints(self, multi_zone_dataset):
        """Test that borders are only included when BOTH endpoints are in filtered zones (default behavior)."""
        filtered = multi_zone_dataset.filter_zones(["FR"])

        # No borders should be included because no border has both endpoints in FR
        assert len(filtered.market_border) == 0

        # Filter for FR and DE
        filtered_fr_de = multi_zone_dataset.filter_zones(["FR", "DE"])
        assert len(filtered_fr_de.market_border) == 1
        assert "border_FR_DE" in filtered_fr_de.market_border

    def test_filter_zone_borders_include_external(self, multi_zone_dataset):
        """Test that borders are included when ANY endpoint is in filtered zones with include_external_borders=True."""
        filtered = multi_zone_dataset.filter_zones(["FR"], include_external_borders=True)

        # Should include borders where FR is one endpoint
        assert len(filtered.market_border) == 2
        assert "border_FR_DE" in filtered.market_border
        assert "border_FR_BE" in filtered.market_border
        assert "border_DE_BE" not in filtered.market_border

    def test_filter_zone_critical_branches_default(self, multi_zone_dataset):
        """Test that critical branches follow same logic as borders by default."""
        filtered = multi_zone_dataset.filter_zones(["FR"])

        # No critical branches should be included with only FR
        assert len(filtered.critical_branch) == 0

        # Filter for FR and DE
        filtered_fr_de = multi_zone_dataset.filter_zones(["FR", "DE"])
        assert len(filtered_fr_de.critical_branch) == 1
        assert "cb_FR_DE" in filtered_fr_de.critical_branch

    def test_filter_zone_critical_branches_include_external(self, multi_zone_dataset):
        """Test critical branches with include_external_borders=True."""
        filtered = multi_zone_dataset.filter_zones(["FR"], include_external_borders=True)

        # Should include critical branch where FR node is one endpoint
        assert len(filtered.critical_branch) == 1
        assert "cb_FR_DE" in filtered.critical_branch

    def test_filter_zone_validation_nonexistent_zone(self, multi_zone_dataset):
        """Test that ValueError is raised for non-existent control block names."""
        with pytest.raises(ValueError, match="Control blocks not found in dataset"):
            multi_zone_dataset.filter_zones(["NONEXISTENT"])

        with pytest.raises(ValueError, match="Control blocks not found in dataset"):
            multi_zone_dataset.filter_zones(["FR", "INVALID_ZONE"])

    def test_filter_zone_multiple_zones(self, multi_zone_dataset):
        """Test filtering with multiple zones."""
        filtered = multi_zone_dataset.filter_zones(["FR", "DE"])

        assert len(filtered.control_block) == 2
        assert "FR" in filtered.control_block
        assert "DE" in filtered.control_block
        assert "BE" not in filtered.control_block

        assert len(filtered.node) == 3
        assert len(filtered.thermal) == 2
        assert len(filtered.hydro) == 1

    def test_filter_zone_returns_deep_copy(self, multi_zone_dataset):
        """Test that filter_zones returns a deep copy and doesn't modify original."""
        original_cb_count = len(multi_zone_dataset.control_block)
        original_node_count = len(multi_zone_dataset.node)

        filtered = multi_zone_dataset.filter_zones(["FR"])

        # Original should be unchanged
        assert len(multi_zone_dataset.control_block) == original_cb_count
        assert len(multi_zone_dataset.node) == original_node_count

        # Filtered should have fewer items
        assert len(filtered.control_block) < original_cb_count
        assert len(filtered.node) < original_node_count

    def test_filter_zone_empty_list(self):
        """Test filtering with empty control_block_names list."""
        cb = ControlBlock(name="CB1")
        ma = MarketArea(name="ma1", control_block=cb)
        node = Node(name="node1", control_block=cb, market_area=ma)
        dataset = AtlasDataset(control_block=[cb], market_area=[ma], node=[node])

        filtered = dataset.filter_zones([])

        # Should return empty dataset
        assert len(filtered.control_block) == 0
        assert len(filtered.node) == 0

    def test_filter_zone_all_equipment_types(self):
        """Test that all equipment types are correctly filtered."""
        cb_zone1 = ControlBlock(name="ZONE1")
        cb_zone2 = ControlBlock(name="ZONE2")
        ma_zone1 = MarketArea(name="ma_zone1", control_block=cb_zone1)
        ma_zone2 = MarketArea(name="ma_zone2", control_block=cb_zone2)
        node1 = Node(name="node1", control_block=cb_zone1, market_area=ma_zone1)
        node2 = Node(name="node2", control_block=cb_zone2, market_area=ma_zone2)
        portfolio1 = Portfolio(name="portfolio1", control_block=cb_zone1, market_area=ma_zone1)
        portfolio2 = Portfolio(name="portfolio2", control_block=cb_zone2, market_area=ma_zone2)

        # Create one of each equipment type
        thermal = Thermal(name="thermal1", node=node1, portfolio=portfolio1)
        hydro = Hydro(name="hydro1", node=node1, portfolio=portfolio1)
        solar = Solar(name="solar1", node=node1, portfolio=portfolio1)
        wind = Wind(name="wind1", node=node1, portfolio=portfolio1)
        storage = Storage(name="storage1", node=node1, portfolio=portfolio1)
        load = Load(name="load1", node=node1, portfolio=portfolio1)

        thermal2 = Thermal(name="thermal2", node=node2, portfolio=portfolio2)
        wind2 = Wind(name="wind2", node=node2, portfolio=portfolio2)

        dataset = AtlasDataset(
            control_block=[cb_zone1, cb_zone2],
            market_area=[ma_zone1, ma_zone2],
            node=[node1, node2],
            portfolio=[portfolio1, portfolio2],
            thermal=[thermal, thermal2],
            hydro=[hydro],
            solar=[solar],
            wind=[wind, wind2],
            storage=[storage],
            load=[load],
        )

        filtered = dataset.filter_zones(["ZONE1"])

        # Check ZONE1 equipment is included
        assert len(filtered.thermal) == 1
        assert "thermal1" in filtered.thermal
        assert len(filtered.hydro) == 1
        assert len(filtered.solar) == 1
        assert len(filtered.wind) == 1
        assert len(filtered.storage) == 1
        assert len(filtered.load) == 1

        # Check ZONE2 equipment is excluded
        assert "thermal2" not in filtered.thermal
        assert "wind2" not in filtered.wind

    def test_filter_zone_market_area_ptdf(self):
        """Test that market_area_ptdf objects are correctly filtered."""

        cb = ControlBlock(name="CB1")
        cb2 = ControlBlock(name="CB2")
        ma = MarketArea(name="ma1", control_block=cb)
        ma2 = MarketArea(name="ma2", control_block=cb2)

        # Create a critical branch for the PTDFs
        node1 = Node(name="node1", control_block=cb, market_area=ma)
        node2 = Node(name="node2", control_block=cb2, market_area=ma2)
        critical_branch = CriticalBranch(
            name="branch1", uphill_node=node1, downhill_node=node2, market_area_ptdf=[], node_ptdf=[]
        )

        ma_ptdf1 = MarketAreaPtdf(
            name="ma_ptdf1",
            market_area=ma,
            critical_branch=critical_branch,
            ptdf_value=0.5,
        )
        ma_ptdf2 = MarketAreaPtdf(
            name="ma_ptdf2",
            market_area=ma2,
            critical_branch=critical_branch,
            ptdf_value=0.3,
        )

        dataset = AtlasDataset(
            control_block=[cb, cb2],
            market_area=[ma, ma2],
            node=[node1, node2],
            critical_branch=[critical_branch],
            market_area_ptdf=[ma_ptdf1, ma_ptdf2],
        )

        filtered = dataset.filter_zones(["CB1"])

        assert len(filtered.market_area_ptdf) == 1
        assert "ma_ptdf1" in filtered.market_area_ptdf
        assert "ma_ptdf2" not in filtered.market_area_ptdf

    def test_filter_zone_node_ptdf(self):
        """Test that node_ptdf objects are correctly filtered."""

        cb = ControlBlock(name="CB1")
        cb2 = ControlBlock(name="CB2")
        ma = MarketArea(name="ma1", control_block=cb)
        ma2 = MarketArea(name="ma2", control_block=cb2)
        node1 = Node(name="node1", control_block=cb, market_area=ma)
        node2 = Node(name="node2", control_block=cb2, market_area=ma2)

        critical_branch = CriticalBranch(
            name="branch1", uphill_node=node1, downhill_node=node2, market_area_ptdf=[], node_ptdf=[]
        )

        node_ptdf1 = NodePtdf(
            name="node_ptdf1",
            node=node1,
            critical_branch=critical_branch,
            ptdf_value=0.7,
        )
        node_ptdf2 = NodePtdf(
            name="node_ptdf2",
            node=node2,
            critical_branch=critical_branch,
            ptdf_value=0.2,
        )

        dataset = AtlasDataset(
            control_block=[cb, cb2],
            node=[node1, node2],
            critical_branch=[critical_branch],
            node_ptdf=[node_ptdf1, node_ptdf2],
        )

        filtered = dataset.filter_zones(["CB1"])

        assert len(filtered.node_ptdf) == 1
        assert "node_ptdf1" in filtered.node_ptdf
        assert "node_ptdf2" not in filtered.node_ptdf


class TestSetFrequencyAll:
    """Test suite for the set_frequency_all method."""

    def setup_method(self):
        self.cb = ControlBlock(name="cb1")
        self.ma = MarketArea(name="ma1", control_block=self.cb)
        self.node = Node(name="node1", control_block=self.cb, market_area=self.ma)
        self.portfolio = Portfolio(name="portfolio1", control_block=self.cb, market_area=self.ma)

    def test_set_frequency_all_basic_timeseries(self):
        """Test that set_frequency_all changes frequency of basic timeseries."""
        # Create timeseries with 1h frequency
        inflows = Timeseries.from_values(
            start_date="2024-01-01 00:00:00",
            frequency="1h",
            values=[100.0, 200.0, 300.0, 400.0],
            timezone="UTC",
        )

        hydro = Hydro(name="hydro1", inflows=inflows, node=self.node, portfolio=self.portfolio)
        dataset = AtlasDataset(hydro=[hydro])

        # Verify initial frequency is 1h
        assert dataset.hydro.get("hydro1").inflows.timestep == Duration(hours=1)

        # Change to 30 minutes
        dataset.set_frequency_all(Duration(minutes=30), inplace=True)

        # Verify frequency changed to 30m
        assert dataset.hydro.get("hydro1").inflows.timestep == Duration(minutes=30)

    def test_set_frequency_all_forecasting_matrix(self):
        """Test that set_frequency_all works with forecasting matrices."""
        # Create forecasting matrix with 1h frequency
        matrix = ForecastingMatrix(
            pl.DataFrame(
                {
                    "time": pl.datetime_range(
                        start=datetime(2024, 1, 1),
                        end=datetime(2024, 1, 1, 3),
                        interval="1h",
                        eager=True,
                    ),
                    "2024-01-01 00:00:00": [1.0, 2.0, 3.0, 4.0],
                }
            ),
            date_format="YYYY-MM-DD HH:mm:ss",
        )

        hydro = Hydro(name="hydro1", stored_energy=matrix, node=self.node, portfolio=self.portfolio)
        dataset = AtlasDataset(hydro=[hydro])

        # Change frequency to 2h
        dataset.set_frequency_all(Duration(hours=2), inplace=True)

        # Verify the matrix frequency changed
        # The matrix should now have fewer rows (upsampled to 2h)
        updated_matrix = dataset.hydro.get("hydro1").stored_energy
        assert len(updated_matrix.matrix) == 2  # 4 hours / 2h intervals = 2 rows

    def test_set_frequency_all_multiple_equipment_types(self):
        """Test that set_frequency_all works across multiple equipment types."""
        ts1 = Timeseries.from_values(
            start_date="2024-01-01 00:00:00",
            frequency="1h",
            values=[10.0, 20.0, 30.0],
            timezone="UTC",
        )
        ts2 = Timeseries.from_values(
            start_date="2024-01-01 00:00:00",
            frequency="1h",
            values=[100.0, 200.0, 300.0],
            timezone="UTC",
        )

        hydro = Hydro(name="hydro1", inflows=ts1, node=self.node, portfolio=self.portfolio)
        thermal = Thermal(name="thermal1", variable_cost=ts2, node=self.node, portfolio=self.portfolio)

        dataset = AtlasDataset(hydro=[hydro], thermal=[thermal])

        # Change to 15 minutes
        dataset.set_frequency_all(Duration(minutes=15), inplace=True)

        # Verify both equipment types have updated frequencies
        assert dataset.hydro.get("hydro1").inflows.timestep == Duration(minutes=15)
        assert dataset.thermal.get("thermal1").variable_cost.timestep == Duration(minutes=15)

    def test_set_frequency_all_inplace_false(self):
        """Test that set_frequency_all with inplace=False returns a new dataset."""
        inflows = Timeseries.from_values(
            start_date="2024-01-01 00:00:00",
            frequency="1h",
            values=[100.0, 200.0, 300.0],
            timezone="UTC",
        )

        hydro = Hydro(name="hydro1", inflows=inflows, node=self.node, portfolio=self.portfolio)
        original_dataset = AtlasDataset(hydro=[hydro])

        # Create a new dataset with different frequency
        new_dataset = original_dataset.set_frequency_all(Duration(minutes=30), inplace=False)

        # Verify original dataset is unchanged
        assert original_dataset.hydro.get("hydro1").inflows.timestep == Duration(hours=1)

        # Verify new dataset has updated frequency
        assert new_dataset.hydro.get("hydro1").inflows.timestep == Duration(minutes=30)

    def test_set_frequency_all_with_object_types_filter(self):
        """Test that set_frequency_all can filter specific object types."""
        ts_hydro = Timeseries.from_values(
            start_date="2024-01-01 00:00:00",
            frequency="1h",
            values=[10.0, 20.0, 30.0],
            timezone="UTC",
        )
        ts_thermal = Timeseries.from_values(
            start_date="2024-01-01 00:00:00",
            frequency="1h",
            values=[100.0, 200.0, 300.0],
            timezone="UTC",
        )

        hydro = Hydro(name="hydro1", inflows=ts_hydro, node=self.node, portfolio=self.portfolio)
        thermal = Thermal(name="thermal1", maximum_power=ts_thermal, node=self.node, portfolio=self.portfolio)

        dataset = AtlasDataset(hydro=[hydro], thermal=[thermal])

        # Only change frequency for hydro
        dataset.set_frequency_all(Duration(minutes=15), inplace=True, object_types=["hydro"])

        # Verify only hydro frequency changed
        assert dataset.hydro.get("hydro1").inflows.timestep == Duration(minutes=15)
        # Thermal should remain at 1h
        assert dataset.thermal.get("thermal1").maximum_power.timestep == Duration(hours=1)

    def test_set_frequency_all_with_string_frequency(self):
        """Test that set_frequency_all accepts string frequency."""
        inflows = Timeseries.from_values(
            start_date="2024-01-01 00:00:00",
            frequency="1h",
            values=[100.0, 200.0, 300.0],
            timezone="UTC",
        )

        hydro = Hydro(name="hydro1", inflows=inflows, node=self.node, portfolio=self.portfolio)
        dataset = AtlasDataset(hydro=[hydro])

        # Use string frequency
        dataset.set_frequency_all("30m", inplace=True)

        # Verify frequency changed
        assert dataset.hydro.get("hydro1").inflows.timestep == Duration(minutes=30)

    def test_set_frequency_all_empty_dataset(self):
        """Test that set_frequency_all works on empty dataset without errors."""
        dataset = AtlasDataset()

        # Should not raise any error
        dataset.set_frequency_all(Duration(hours=1), inplace=True)

        assert len(dataset) == 0

    def test_set_frequency_all_objects_without_timeseries(self):
        """Test that set_frequency_all handles objects without timeseries gracefully."""
        # Create objects without any timeseries attributes
        dataset = AtlasDataset(node=[self.node], control_block=[self.cb])

        # Should not raise any error
        dataset.set_frequency_all(Duration(hours=1), inplace=True)

        # Objects should still exist
        assert len(dataset.node) == 1
        assert len(dataset.control_block) == 1

    def test_set_frequency_all_mixed_objects(self):
        """Test with mix of objects with and without timeseries."""
        inflows = Timeseries.from_values(
            start_date="2024-01-01 00:00:00",
            frequency="1h",
            values=[100.0, 200.0, 300.0],
            timezone="UTC",
        )

        hydro = Hydro(name="hydro1", inflows=inflows, node=self.node, portfolio=self.portfolio)

        dataset = AtlasDataset(hydro=[hydro], node=[self.node], control_block=[self.cb])

        dataset.set_frequency_all(Duration(minutes=15), inplace=True)

        # Verify only hydro's timeseries changed
        assert dataset.hydro.get("hydro1").inflows.timestep == Duration(minutes=15)
        # Other objects should be unchanged
        assert len(dataset.node) == 1
        assert len(dataset.control_block) == 1

    def test_set_frequency_all_downsampling(self):
        """Test downsampling (reducing frequency - fewer data points)."""
        # Create timeseries with 15min frequency (high frequency)
        inflows = Timeseries.from_values(
            start_date="2024-01-01 00:00:00",
            frequency="15m",
            values=[10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0],
            timezone="UTC",
        )

        hydro = Hydro(name="hydro1", inflows=inflows, node=self.node, portfolio=self.portfolio)
        dataset = AtlasDataset(hydro=[hydro])

        # Store original length before modification
        original_length = len(inflows)

        # Downsample to 1h (lower frequency - fewer points)
        dataset.set_frequency_all(Duration(hours=1), inplace=True)

        updated_inflows = dataset.hydro.get("hydro1").inflows
        assert updated_inflows.timestep == Duration(hours=1)
        # Should have fewer points now (aggregated)
        assert len(updated_inflows) < original_length

    def test_set_frequency_all_upsampling(self):
        """Test upsampling (increasing frequency - more data points)."""
        # Create timeseries with 1h frequency (low frequency)
        inflows = Timeseries.from_values(
            start_date="2024-01-01 00:00:00",
            frequency="1h",
            values=[100.0, 200.0, 300.0],
            timezone="UTC",
        )

        hydro = Hydro(name="hydro1", inflows=inflows, node=self.node, portfolio=self.portfolio)
        dataset = AtlasDataset(hydro=[hydro])

        # Store original length before modification
        original_length = len(inflows)

        # Upsample to 15min (higher frequency - more points)
        dataset.set_frequency_all(Duration(minutes=15), inplace=True)

        updated_inflows = dataset.hydro.get("hydro1").inflows
        assert updated_inflows.timestep == Duration(minutes=15)
        # Should have more points now (interpolated)
        assert len(updated_inflows) > original_length

    def test_set_frequency_all_multiple_attributes_per_object(self):
        """Test object with multiple timeseries attributes."""
        inflows = Timeseries.from_values(
            start_date="2024-01-01 00:00:00",
            frequency="1h",
            values=[100.0, 200.0, 300.0],
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
                    "2024-01-01 00:00:00": [1.0, 2.0, 3.0],
                }
            )
        )

        # Hydro has both inflows (Timeseries) and stored_energy (ForecastingMatrix)
        hydro = Hydro(name="hydro1", inflows=inflows, stored_energy=matrix, node=self.node, portfolio=self.portfolio)
        dataset = AtlasDataset(hydro=[hydro])

        dataset.set_frequency_all(Duration(minutes=30), inplace=True)

        # Verify both attributes changed
        assert dataset.hydro.get("hydro1").inflows.timestep == Duration(minutes=30)
        # Matrix should also be resampled
        updated_matrix = dataset.hydro.get("hydro1").stored_energy
        assert len(updated_matrix.matrix) > 3  # Should have more rows after upsampling

    def test_set_frequency_all_scenario_matrix(self):
        """Test that set_frequency_all works with ScenarioMatrix."""
        # Create a ScenarioMatrix with 1h frequency
        scenario_matrix = ScenarioMatrix(
            pl.DataFrame(
                {
                    "time": pl.datetime_range(
                        start=datetime(2024, 1, 1),
                        end=datetime(2024, 1, 1, 3),
                        interval="1h",
                        eager=True,
                    ),
                    "scenario1": [10.0, 20.0, 30.0, 40.0],
                    "scenario2": [15.0, 25.0, 35.0, 45.0],
                }
            )
        )

        # Use state_sequence which accepts ScenarioMatrix
        thermal = Thermal(name="thermal1", state_sequence=scenario_matrix, node=self.node, portfolio=self.portfolio)
        dataset = AtlasDataset(thermal=[thermal])

        # Verify initial frequency
        original_length = len(scenario_matrix.matrix)
        assert original_length == 4

        # Change to 2h frequency (downsampling)
        dataset.set_frequency_all(Duration(hours=2), inplace=True)

        # Verify the matrix frequency changed
        updated_matrix = dataset.thermal.get("thermal1").state_sequence
        assert len(updated_matrix.matrix) < original_length  # Should have fewer rows

    def test_set_frequency_all_scenario_matrix_upsampling(self):
        """Test upsampling with ScenarioMatrix."""
        # Create a ScenarioMatrix with 1h frequency
        scenario_matrix = ScenarioMatrix(
            pl.DataFrame(
                {
                    "time": pl.datetime_range(
                        start=datetime(2024, 1, 1),
                        end=datetime(2024, 1, 1, 2),
                        interval="1h",
                        eager=True,
                    ),
                    "scenario1": [100.0, 200.0, 300.0],
                    "scenario2": [150.0, 250.0, 350.0],
                }
            )
        )

        thermal = Thermal(name="thermal1", state_sequence=scenario_matrix, node=self.node, portfolio=self.portfolio)
        dataset = AtlasDataset(thermal=[thermal])

        # Store original length
        original_length = len(scenario_matrix.matrix)
        assert original_length == 3

        # Upsample to 30min (higher frequency - more points)
        dataset.set_frequency_all(Duration(minutes=30), inplace=True)

        # Verify the matrix has more rows
        updated_matrix = dataset.thermal.get("thermal1").state_sequence
        assert len(updated_matrix.matrix) > original_length

    def test_set_frequency_all_mixed_timeseries_and_matrices(self):
        """Test with equipment having both timeseries and matrices."""
        # Create timeseries
        inflows = Timeseries.from_values(
            start_date="2024-01-01 00:00:00",
            frequency="1h",
            values=[10.0, 20.0, 30.0, 40.0],
            timezone="UTC",
        )

        # Create ForecastingMatrix
        forecasting_matrix = ForecastingMatrix(
            pl.DataFrame(
                {
                    "time": pl.datetime_range(
                        start=datetime(2024, 1, 1),
                        end=datetime(2024, 1, 1, 3),
                        interval="1h",
                        eager=True,
                    ),
                    "2024-01-01 00:00:00": [1.0, 2.0, 3.0, 4.0],
                }
            )
        )

        # Create ScenarioMatrix
        scenario_matrix = ScenarioMatrix(
            pl.DataFrame(
                {
                    "time": pl.datetime_range(
                        start=datetime(2024, 1, 1),
                        end=datetime(2024, 1, 1, 3),
                        interval="1h",
                        eager=True,
                    ),
                    "scenario1": [100.0, 200.0, 300.0, 400.0],
                }
            )
        )

        # Create thermal with state_sequence (ScenarioMatrix)
        thermal = Thermal(
            name="thermal1",
            state_sequence=scenario_matrix,
            maximum_power=inflows,
            node=self.node,
            portfolio=self.portfolio,
        )

        # Create hydro with inflows (Timeseries) and stored_energy (ForecastingMatrix)
        hydro = Hydro(
            name="hydro1", inflows=inflows, stored_energy=forecasting_matrix, node=self.node, portfolio=self.portfolio
        )

        dataset = AtlasDataset(thermal=[thermal], hydro=[hydro])

        # Change to 30min frequency
        dataset.set_frequency_all(Duration(minutes=30), inplace=True)

        # Verify all three types of math objects changed
        # 1. Timeseries (inflows and maximum_power)
        assert dataset.hydro.get("hydro1").inflows.timestep == Duration(minutes=30)
        assert dataset.thermal.get("thermal1").maximum_power.timestep == Duration(minutes=30)

        # 2. ForecastingMatrix (stored_energy)
        updated_forecasting = dataset.hydro.get("hydro1").stored_energy
        assert len(updated_forecasting.matrix) > 4  # Should have more rows after upsampling

        # 3. ScenarioMatrix (state_sequence)
        updated_scenario = dataset.thermal.get("thermal1").state_sequence
        assert len(updated_scenario.matrix) > 4  # Should have more rows after upsampling

    def test_set_frequency_all_forecasting_matrix_with_multiple_scenarios(self):
        """Test ForecastingMatrix with multiple forecast scenarios."""
        # Create a ForecastingMatrix with multiple forecast dates
        forecasting_matrix = ForecastingMatrix(
            pl.DataFrame(
                {
                    "time": pl.datetime_range(
                        start=datetime(2024, 1, 1),
                        end=datetime(2024, 1, 1, 2),
                        interval="1h",
                        eager=True,
                    ),
                    "2024-01-01 00:00:00": [10.0, 20.0, 30.0],
                    "2024-01-01 06:00:00": [15.0, 25.0, 35.0],
                }
            )
        )

        hydro = Hydro(name="hydro1", stored_energy=forecasting_matrix, node=self.node, portfolio=self.portfolio)
        dataset = AtlasDataset(hydro=[hydro])

        original_length = len(forecasting_matrix.matrix)

        # Downsample to 2h
        dataset.set_frequency_all(Duration(hours=2), inplace=True)

        # Verify the matrix was resampled
        updated_matrix = dataset.hydro.get("hydro1").stored_energy
        assert len(updated_matrix.matrix) < original_length

    def test_set_frequency_all_matrices_with_object_types_filter(self):
        """Test that object_types filter works correctly with matrices."""
        # Create matrices for different equipment types
        matrix_hydro = ForecastingMatrix(
            pl.DataFrame(
                {
                    "time": pl.datetime_range(
                        start=datetime(2024, 1, 1),
                        end=datetime(2024, 1, 1, 2),
                        interval="1h",
                        eager=True,
                    ),
                    "2024-01-01 00:00:00": [10.0, 20.0, 30.0],
                }
            )
        )

        matrix_thermal = ScenarioMatrix(
            pl.DataFrame(
                {
                    "time": pl.datetime_range(
                        start=datetime(2024, 1, 1),
                        end=datetime(2024, 1, 1, 2),
                        interval="1h",
                        eager=True,
                    ),
                    "scenario1": [100.0, 200.0, 300.0],
                }
            )
        )

        hydro = Hydro(name="hydro1", stored_energy=matrix_hydro, node=self.node, portfolio=self.portfolio)
        thermal = Thermal(name="thermal1", state_sequence=matrix_thermal, node=self.node, portfolio=self.portfolio)

        dataset = AtlasDataset(hydro=[hydro], thermal=[thermal])

        # Only change frequency for hydro
        dataset.set_frequency_all(Duration(minutes=30), inplace=True, object_types=["hydro"])

        # Verify only hydro matrix changed (more rows after upsampling)
        assert len(dataset.hydro.get("hydro1").stored_energy.matrix) > 3

        # Thermal should remain at 1h (3 rows)
        assert len(dataset.thermal.get("thermal1").state_sequence.matrix) == 3
