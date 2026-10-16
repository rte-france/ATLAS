import pendulum

from atlas.enums import StorageType
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.io_utils.prometheus_transformer import PrometheusToAtlasDataParser
from atlas.objects.equipment.storage import Storage
from atlas.objects.market.market_area import MarketArea
from atlas.objects.market_operator.portfolio import Portfolio
from atlas.objects.network.node import Node
from atlas.objects.network_operator.control_block import ControlBlock


def _make_parser(tmp_path) -> PrometheusToAtlasDataParser:
    return PrometheusToAtlasDataParser(
        timeseries_path=tmp_path / "timeseries",
        hdf5_path=tmp_path / "data.hdf5",
        output_dir=tmp_path / "output",
        default_value=False,
    )


def test_read_and_parse_csv_infers_sparse_numeric_columns_across_full_file(tmp_path):
    # A forecasting matrix column whose first non-null value only appears after
    # row 100 must still be inferred as numeric, not silently typed as String
    # by polars' default 100-row schema inference sample.
    start = pendulum.datetime(2028, 1, 1)
    lines = ["TimeStep;01/07/2028 00:00:00;26/09/2028 15:00:00"]
    for i in range(150):
        timestep = start.add(hours=i).format("DD_MM_YYYY_HH_mm_ss")
        value = "-14739.57" if i == 149 else ""
        lines.append(f"{timestep};1.0;{value}")

    csv_file = tmp_path / "MaximumPowerForecast.csv"
    csv_file.write_text("\r\n".join(lines) + "\r\n")

    parser = _make_parser(tmp_path)
    df = parser._read_and_parse_csv(str(csv_file))

    assert df["26/09/2028 15:00:00"].dtype.is_numeric()
    assert df["26/09/2028 15:00:00"].drop_nulls().to_list() == [-14739.57]


def _make_storage_dataset(**storage_kwargs) -> AtlasDataset:
    cb = ControlBlock(name="cb1")
    ma = MarketArea(name="ma1", control_block=cb)
    node = Node(name="node1", control_block=cb, market_area=ma)
    portfolio = Portfolio(name="portfolio1", control_block=cb, market_area=ma)
    storage = Storage(name="storage1", node=node, portfolio=portfolio, **storage_kwargs)
    return AtlasDataset(storage=[storage])


def test_add_default_value_fills_missing_storage_reserve_durations():
    dataset = _make_storage_dataset(storage_type=StorageType.BATTERY)

    PrometheusToAtlasDataParser.add_default_value(dataset)

    storage = dataset.storage.get("storage1")
    assert storage.automated_reserve_duration == pendulum.duration(hours=1)
    assert storage.manual_reserve_duration == pendulum.duration(hours=1)


def test_add_default_value_keeps_defined_storage_reserve_durations():
    dataset = _make_storage_dataset(
        storage_type=StorageType.ELECTRIC_VEHICLE,
        automated_reserve_duration="PT15M",
        manual_reserve_duration="PT2H",
    )

    PrometheusToAtlasDataParser.add_default_value(dataset)

    storage = dataset.storage.get("storage1")
    assert storage.automated_reserve_duration == pendulum.duration(minutes=15)
    assert storage.manual_reserve_duration == pendulum.duration(hours=2)
