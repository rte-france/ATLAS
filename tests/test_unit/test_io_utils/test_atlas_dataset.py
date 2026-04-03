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
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.control_block import ControlBlock
from atlas.models.equipment.hydro import Hydro
from atlas.models.equipment.load import Load
from atlas.models.equipment.solar import Solar
from atlas.models.equipment.storage import Storage
from atlas.models.equipment.thermal import Thermal
from atlas.models.equipment.wind import Wind
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
        nodes = [Node(name="node1"), Node(name="node2")]
        dataset = AtlasDataset(node=nodes)

        assert len(dataset) == 2
        assert len(dataset.node) == 2
        assert dataset.node.get("node1")
        assert dataset.node.get("node2")
        assert "node1" in dataset

    def test_attribute_access_empty_attribute(self):
        control_blocks = [ControlBlock(name="cb1")]
        nodes = [Node(name="node1")]

        dataset = AtlasDataset(control_block=control_blocks, node=nodes)

        assert dataset.thermal.is_empty()

    def test_contains_operator(self):
        control_blocks = [ControlBlock(name="cb1")]
        nodes = [Node(name="node1"), Node(name="node2")]
        dataset = AtlasDataset(node=nodes, control_block=control_blocks)

        assert "node1" in dataset
        assert "node2" in dataset
        assert "cb1" in dataset

        assert "node3" not in dataset
        assert "nonexistent" not in dataset

        assert Node(name="node1") not in dataset
        assert 123 not in dataset
        assert None not in dataset

    def test_len_operator(self):
        dataset = AtlasDataset(
            node=[Node(name="node1"), Node(name="node2")],
            control_block=[ControlBlock(name="cb1")],
        )
        assert len(dataset) == 3

    def test_repr_and_str(self):
        dataset = AtlasDataset(node=[Node(name="node1")])
        assert "AtlasDataset" in repr(dataset)
        assert "node=1" in repr(dataset)
        assert str(dataset) == repr(dataset)

    def test_iter_operator(self):
        dataset = AtlasDataset(
            node=[Node(name="node1"), Node(name="node2")],
            control_block=[ControlBlock(name="cb1")],
        )

        objects = list(dataset)
        names = {o.name for o in objects}
        assert names == {"node1", "node2", "cb1"}

    def test_iter_operator_empty(self):
        assert list(AtlasDataset()) == []

    def test_iter_operator_multiple_times(self):
        dataset = AtlasDataset(node=[Node(name="node1"), Node(name="node2")])
        assert sum(1 for _ in dataset) == 2
        assert sum(1 for _ in dataset) == 2


class TestAtlasDatasetLookup:
    def test_get_nonexistent_name(self):
        dataset = AtlasDataset(node=[Node(name="node1")])
        assert dataset.get("node", "nope") is None

    def test_get_nonexistent_type(self):
        dataset = AtlasDataset(node=[Node(name="node1")])
        assert dataset.get("thermal", "x") is None

    def test_iter_by_types(self):
        nodes = [Node(name="n1"), Node(name="n2")]
        control_blocks = [ControlBlock(name="cb1")]

        dataset = AtlasDataset(node=nodes, control_block=control_blocks)

        collected = list(dataset.iter_by_types("node", "control_block"))
        assert collected[:2] == list(nodes)
        assert collected[2:] == list(control_blocks)

    def test_iter_by_types_invalid(self):
        with pytest.raises(ValueError):
            list(AtlasDataset().iter_by_types("invalid"))

    def test_duplicate_names_validation(self):
        with pytest.raises(ValueError):
            AtlasDataset(node=[Node(name="dup"), Node(name="dup")])

    def test_iter_by_equipments_empty(self):
        dataset = AtlasDataset()
        equipments = list(dataset.iter_by_equipments())
        assert equipments == []

    def test_iter_by_equipments_single_type(self):
        thermal = Thermal(name="plant1")
        dataset = AtlasDataset(thermal=[thermal])
        equipments = list(dataset.iter_by_equipments())
        assert len(equipments) == 1
        assert equipments[0] == thermal

    def test_iter_by_equipments_multiple_types(self):
        thermal = Thermal(name="plant1")
        solar = Solar(name="solar1")
        wind = Wind(name="wind1")
        hydro = Hydro(name="hydro1")
        load = Load(name="load1")
        storage = Storage(name="storage1")

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
        thermal1 = Thermal(name="plant1")
        thermal2 = Thermal(name="plant2")
        thermal3 = Thermal(name="plant3")
        dataset = AtlasDataset(thermal=[thermal1, thermal2, thermal3])

        equipments = list(dataset.iter_by_equipments())
        assert len(equipments) == 3
        assert equipments[0] == thermal1
        assert equipments[1] == thermal2
        assert equipments[2] == thermal3

    def test_iter_by_equipments_excludes_non_equipment(self):
        thermal = Thermal(name="plant1")
        node = Node(name="node1")
        control_block = ControlBlock(name="cb1")
        market_area = MarketArea(name="ma1")

        dataset = AtlasDataset(
            thermal=[thermal],
            node=[node],
            control_block=[control_block],
            market_area=[market_area],
        )

        equipments = list(dataset.iter_by_equipments())
        assert len(equipments) == 1
        assert equipments[0] == thermal

    def test_iter_by_equipments_multiple_times(self):
        thermal = Thermal(name="plant1")
        solar = Solar(name="solar1")
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
        nodes = [Node(name="node1")]
        control_blocks = [ControlBlock(name="cb1")]

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

        pl.DataFrame([{"name": "node1"}]).write_csv(test_dir / "objects" / "node.csv", separator=";")

        dataset = AtlasDataset.from_directory(test_dir)
        assert len(dataset.node) == 1
        assert dataset.node.get("node1")

    def test_to_directory(self, tmp_path):
        dataset = AtlasDataset(node=[Node(name="node1")])
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


class TestAtlasDatasetEq:
    def test_two_empty_datasets_are_equal(self):
        assert AtlasDataset() == AtlasDataset()

    def test_same_objects_are_equal(self):
        node_1 = Node(name="node")
        node_2 = Node(name="node")
        ds1 = AtlasDataset(node=[node_1])
        ds2 = AtlasDataset(node=[node_2])
        assert ds1 == ds2

    def test_different_node_names_are_not_equal(self):
        node_1 = Node(name="node1")
        node_2 = Node(name="node2")
        ds1 = AtlasDataset(node=[node_1])
        ds2 = AtlasDataset(node=[node_2])
        assert ds1 != ds2

    def test_different_counts_are_not_equal(self):
        node_1 = Node(name="node1")
        node_2 = Node(name="node2")
        ds1 = AtlasDataset(node=[node_1])
        ds2 = AtlasDataset(node=[node_1, node_2])
        assert ds1 != ds2

    def test_extra_object_type_makes_not_equal(self):
        node = Node(name="node")
        thermal = Node(name="thermal")
        ds1 = AtlasDataset(node=[node])
        ds2 = AtlasDataset(node=[node], thermal=[thermal])
        assert ds1 != ds2

    def test_eq_with_non_atlas_dataset_returns_not_implemented(self):
        ds = AtlasDataset()
        result = ds.__eq__("not a dataset")
        assert result is NotImplemented

    def test_eq_is_symmetric(self):
        node = Node(name="node")
        ds1 = AtlasDataset(node=[node])
        ds2 = AtlasDataset(node=[node])
        assert ds1 == ds2
        assert ds2 == ds1

    def test_eq_with_same_name_different_attributes(self):
        th1 = Thermal(name="th", installed_capacity=100)
        th2 = Thermal(name="th", installed_capacity=990)
        ds1 = AtlasDataset(thermal=[th1])
        ds2 = AtlasDataset(thermal=[th2])
        assert ds1 != ds2

    def test_eq_with_same_name_same_attribute(self):
        th1 = Thermal(name="th", installed_capacity=100)
        th2 = Thermal(name="th", installed_capacity=100)
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
        ds = AtlasDataset(node=[Node(name="node")])
        assert ds.diff(ds) == {}

    def test_object_only_in_self(self):
        ds1 = AtlasDataset(node=[Node(name="node")])
        ds2 = AtlasDataset()
        result = ds1.diff(ds2)
        assert "node" in result["node"]["only_in_self"]
        assert result["node"]["only_in_other"] == []

    def test_object_only_in_other(self):
        ds1 = AtlasDataset()
        ds2 = AtlasDataset(node=[Node(name="node")])
        result = ds1.diff(ds2)
        assert "node" in result["node"]["only_in_other"]
        assert result["node"]["only_in_self"] == []

    def test_modified_scalar_attribute(self):
        th1 = Thermal(name="th", installed_capacity=100)
        th2 = Thermal(name="th", installed_capacity=999)
        result = AtlasDataset(thermal=[th1]).diff(AtlasDataset(thermal=[th2]))
        assert result["thermal"]["modified"]["th"]["installed_capacity"] == {"self": 100, "other": 999}

    def test_modified_timeseries_attribute(self, simple_timeseries):
        ts_other = Timeseries.from_values(
            start_date="2024-01-01 00:00:00", frequency="1h", values=[99.0, 99.0, 99.0], timezone="UTC"
        )
        result = AtlasDataset(hydro=[Hydro(name="h", inflows=simple_timeseries)]).diff(
            AtlasDataset(hydro=[Hydro(name="h", inflows=ts_other)])
        )
        assert "inflows" in result["hydro"]["modified"]["h"]

    def test_modified_enum_field(self):
        th1 = Thermal(name="th", strategy=ThermalStrategy.BASE)
        th2 = Thermal(name="th", strategy=ThermalStrategy.PEAK)
        result = AtlasDataset(thermal=[th1]).diff(AtlasDataset(thermal=[th2]))
        assert "strategy" in result["thermal"]["modified"]["th"]

    def test_modified_duration_field(self):
        th1 = Thermal(name="th", minimum_time_on=Duration(hours=1))
        th2 = Thermal(name="th", minimum_time_on=Duration(hours=6))
        result = AtlasDataset(thermal=[th1]).diff(AtlasDataset(thermal=[th2]))
        assert "minimum_time_on" in result["thermal"]["modified"]["th"]

    def test_multiple_types_reported_simultaneously(self):
        atlas_1 = AtlasDataset(node=[Node(name="n_1")], thermal=[Thermal(name="th", installed_capacity=100)])
        atlas_2 = AtlasDataset(node=[Node(name="n_2")], thermal=[Thermal(name="th", installed_capacity=500)])
        result = atlas_1.diff(atlas_2)
        assert "node" in result
        assert "thermal" in result

    def test_common_unchanged_object_not_in_modified(self):
        n_1 = Node(name="n_1")
        n_2 = Node(name="n_2")
        result = AtlasDataset(node=[n_1, n_2]).diff(AtlasDataset(node=[n_1]))
        assert "n_1" not in result.get("node", {}).get("modified", {})
        assert "n_2" in result["node"]["only_in_self"]


class TestDiffBusinessModel:
    def test_identical_objects_return_empty_dict(self):
        node = Node(name="node")
        assert AtlasDataset.diff_business_model(node, node) == {}

    def test_scalar_field_difference_detected(self):
        th1 = Thermal(name="th", installed_capacity=100)
        th2 = Thermal(name="th", installed_capacity=500)
        result = AtlasDataset.diff_business_model(th1, th2)
        assert result["installed_capacity"] == {"self": 100, "other": 500}

    def test_nested_business_model_difference(self):
        th1 = Thermal(name="th", node=Node(name="node_1"))
        th2 = Thermal(name="th", node=Node(name="node_2"))
        result = AtlasDataset.diff_business_model(th1, th2)
        assert result["node"]["type"] == "nested"
        assert result["node"]["object_name"] in ("node_1", "node_2")

    def test_circular_reference_does_not_loop(self):
        node = Node(name="node")
        visited: set[tuple[int, int]] = {(id(node), id(node))}
        assert AtlasDataset.diff_business_model(node, node, _visited=visited) == {}

    def test_timeseries_field_difference_detected(self, simple_timeseries):
        ts_other = Timeseries.from_values(
            start_date="2024-01-01 00:00:00", frequency="1h", values=[0.0, 0.0, 0.0], timezone="UTC"
        )
        result = AtlasDataset.diff_business_model(
            Hydro(name="h", inflows=simple_timeseries),
            Hydro(name="h", inflows=ts_other),
        )
        assert "inflows" in result

    def test_only_differing_fields_are_returned(self):
        th1 = Thermal(name="th", installed_capacity=100, outage_probability=0.05)
        th2 = Thermal(name="th", installed_capacity=999, outage_probability=0.05)
        result = AtlasDataset.diff_business_model(th1, th2)
        assert "installed_capacity" in result
        assert "outage_probability" not in result


class TestDiffOnOtherThanBusinessModel:
    def test_equal_scalar_returns_none(self):
        assert AtlasDataset.diff_on_other_than_business_model(42, 42) is None

    def test_different_int_returns_diff(self):
        assert AtlasDataset.diff_on_other_than_business_model(1, 2) == {"self": 1, "other": 2}

    def test_different_str_returns_diff(self):
        assert AtlasDataset.diff_on_other_than_business_model("a", "b") == {"self": "a", "other": "b"}

    def test_different_bool_returns_diff(self):
        assert AtlasDataset.diff_on_other_than_business_model(True, False) == {"self": True, "other": False}

    def test_different_lists_delegates_to_diff_lists(self):
        result = AtlasDataset.diff_on_other_than_business_model([1, 2], [1, 99])
        assert "1" in result

    def test_equal_timeseries_returns_none(self, simple_timeseries):
        assert AtlasDataset.diff_on_other_than_business_model(simple_timeseries, simple_timeseries) is None

    def test_different_timeseries_returns_changed(self):
        ts1 = Timeseries.from_values(
            start_date="2024-01-01 00:00:00", frequency="1h", values=[1.0, 2.0], timezone="UTC"
        )
        ts2 = Timeseries.from_values(
            start_date="2024-01-01 00:00:00", frequency="1h", values=[9.0, 2.0], timezone="UTC"
        )
        assert "changed" in AtlasDataset.diff_on_other_than_business_model(ts1, ts2)

    def test_different_custom_object_returns_changed(self):
        class MyObj:
            def __init__(self, v):
                self.v = v

            def __eq__(self, other):
                return self.v == other.v

        assert AtlasDataset.diff_on_other_than_business_model(MyObj(1), MyObj(2)) == {"changed": "not-serializable yet"}

    def test_exception_in_eq_returns_error(self):
        class Broken:
            def __eq__(self, other):
                raise RuntimeError("broken")

        assert AtlasDataset.diff_on_other_than_business_model(Broken(), Broken()) == {"error": "Couldn't check diff"}

    def test_none_vs_value_returns_changed(self):
        assert AtlasDataset.diff_on_other_than_business_model(None, 42) is not None


class TestDiffLists:
    def test_different_lengths_returns_list_length_diff(self):
        result = AtlasDataset.diff_lists([1, 2, 3], [1, 2])
        assert result == {"type": "list_length", "self": 3, "other": 2}

    def test_equal_lists_returns_none(self):
        assert AtlasDataset.diff_lists([1, 2, 3], [1, 2, 3]) is None

    def test_single_differing_element(self):
        result = AtlasDataset.diff_lists([1, 2, 3], [1, 99, 3])
        assert result["1"] == {"self": 2, "other": 99}
        assert "0" not in result
        assert "2" not in result

    def test_business_model_elements_identical_returns_none(self):
        node = Node(name="node")
        assert AtlasDataset.diff_lists([node], [node]) is None

    def test_business_model_elements_different_detected(self):
        result = AtlasDataset.diff_lists([Node(name="node_1")], [Node(name="node_2")])
        assert result["0"]["type"] == "nested"

    def test_only_differing_element_reported(self):
        node = Node(name="node")
        result = AtlasDataset.diff_lists([node, Node(name="node_1")], [node, Node(name="node_2")])
        assert "0" not in result
        assert "1" in result


@pytest.fixture
def dataset():
    ds = AtlasDataset()
    ds.order.add(Order(name="order_1", price=10))
    ds.order.add(Order(name="order_2", price=50))
    ds.market_area.add(MarketArea(name="ma1"))
    ds.market_area.add(MarketArea(name="ma2"))
    ds.node.add(Node(name="NodeA"))
    ds.node.add(Node(name="NodeB"))
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
    t1 = Thermal(name="plant_1")
    t2 = Thermal(name="plant_2")
    t3 = Thermal(name="plant_3")

    dataset = AtlasDataset(thermal=[t1, t2, t3])

    filtered = dataset.filter_equipments(["plant_1", "plant_3"])

    remaining_names = [e.name for e in filtered.thermal]

    assert set(remaining_names) == {"plant_1", "plant_3"}
    assert "plant_2" not in remaining_names


def test_filter_does_not_modify_original_dataset():
    t1 = Thermal(name="plant_1")
    t2 = Thermal(name="plant_2")

    dataset = AtlasDataset(thermal=[t1, t2])

    filtered = dataset.filter_equipments(["plant_1"])

    assert len(dataset.thermal) == 2  # original unchanged
    assert len(filtered.thermal) == 1
