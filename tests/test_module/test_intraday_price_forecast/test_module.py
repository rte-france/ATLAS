import pendulum
import pytest

from atlas import ControlBlock
from atlas.enums import LoadType
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.io_utils.parameters import DateParameters
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.intraday_price_forecast.input_dataset import IntradayPriceForecastInputDataset
from atlas.modules.intraday_price_forecast.input_objects.load import LoadIDPF
from atlas.modules.intraday_price_forecast.input_objects.market_area import MarketAreaIDPF
from atlas.modules.intraday_price_forecast.input_objects.solar import SolarIDPF
from atlas.modules.intraday_price_forecast.input_objects.wind import WindIDPF
from atlas.modules.intraday_price_forecast.module import IntradayPriceForecastModule
from atlas.modules.intraday_price_forecast.output_dataset import IntradayPriceForecastOutputDataset
from atlas.modules.intraday_price_forecast.parameters import IntradayPriceForecastParameters
from atlas.objects.market_operator.portfolio import Portfolio
from atlas.objects.network.node import Node
from atlas.timing import generate_datetimes


@pytest.fixture
def test_parameters():
    """Create test parameters."""
    start_date = pendulum.datetime(2024, 1, 1, 0, 0, 0)
    end_date = pendulum.datetime(2024, 1, 1, 3, 0, 0)
    execution_date = pendulum.datetime(2024, 1, 1, 0, 0, 0)
    timestep = pendulum.duration(hours=1)

    temporal = DateParameters(
        start_date=start_date, end_date=end_date, execution_date=execution_date, timestep=timestep
    )

    params = IntradayPriceForecastParameters(
        temporal=temporal,
        intraday_negative_price_cap=-500,
        intraday_positive_price_cap=4000,
        execution_date_day_ahead=pendulum.datetime(2024, 1, 1, 6, 0, 0),
        execution_date_scenarios=pendulum.datetime(2024, 1, 1, 0, 0, 0),
    )
    return params


@pytest.fixture
def test_market_area(test_parameters):
    """Create a test market area with price forecasts."""
    start_date = test_parameters.temporal.start_date
    end_date = test_parameters.temporal.end_date
    timestep = test_parameters.temporal.timestep

    # Create price forecast matrices
    price_forecast_high = ForecastingMatrix()
    ts_high = Timeseries.from_index(start_date, timestep, end_date, default_value=100.0)
    price_forecast_high.add(ts_high, test_parameters.execution_date_scenarios)

    price_forecast_low = ForecastingMatrix()
    ts_low = Timeseries.from_index(start_date, timestep, end_date, default_value=50.0)
    price_forecast_low.add(ts_low, test_parameters.execution_date_scenarios)

    # Create day-ahead price
    da_price = Timeseries.from_index(start_date, timestep, end_date, default_value=75.0)

    control_block = ControlBlock(name="test_cb")
    market_area = MarketAreaIDPF(
        name="test_market",
        control_block=control_block,
        price_forecast_high=price_forecast_high,
        price_forecast_low=price_forecast_low,
        da_price=da_price,
    )
    return market_area


@pytest.fixture
def test_node(test_market_area):
    """Create a test node."""
    return Node(
        name="test_node",
        control_block=test_market_area.control_block,
        market_area=test_market_area,
    )


@pytest.fixture
def test_load(test_market_area, test_node, test_parameters):
    """Create a test load."""
    start_date = test_parameters.temporal.start_date
    end_date = test_parameters.temporal.end_date
    timestep = test_parameters.temporal.timestep
    exec_date_da = test_parameters.execution_date_day_ahead
    exec_date_id = test_parameters.temporal.execution_date

    portfolio = Portfolio(
        name="test_portfolio", control_block=test_market_area.control_block, market_area=test_market_area
    )

    # Create power forecast matrices
    max_power_forecast = ForecastingMatrix()

    # Day-ahead forecast
    ts_da = Timeseries.from_index(start_date, timestep, end_date, default_value=1000.0)
    max_power_forecast.add(ts_da, exec_date_da)

    # Intraday forecast (different from day-ahead)
    ts_id = Timeseries.from_index(start_date, timestep, end_date, default_value=1100.0)
    max_power_forecast.add(ts_id, exec_date_id)

    # High/low scenarios
    power_forecast_high = Timeseries.from_index(start_date, timestep, end_date, default_value=1200.0)
    power_forecast_low = Timeseries.from_index(start_date, timestep, end_date, default_value=800.0)

    load = LoadIDPF(
        name="test_load",
        load_type=LoadType.BASE_LOAD,
        node=test_node,
        portfolio=portfolio,
        maximum_power_forecast=max_power_forecast,
        power_forecast_high=power_forecast_high,
        power_forecast_low=power_forecast_low,
    )
    return load


@pytest.fixture
def test_solar(test_market_area, test_node, test_parameters):
    """Create a test solar unit."""
    start_date = test_parameters.temporal.start_date
    end_date = test_parameters.temporal.end_date
    timestep = test_parameters.temporal.timestep
    exec_date_da = test_parameters.execution_date_day_ahead
    exec_date_id = test_parameters.temporal.execution_date

    portfolio = Portfolio(
        name="test_portfolio_solar", control_block=test_market_area.control_block, market_area=test_market_area
    )

    max_power_forecast = ForecastingMatrix()
    ts_da = Timeseries.from_index(start_date, timestep, end_date, default_value=-200.0)
    max_power_forecast.add(ts_da, exec_date_da)

    ts_id = Timeseries.from_index(start_date, timestep, end_date, default_value=-180.0)
    max_power_forecast.add(ts_id, exec_date_id)

    solar = SolarIDPF(name="test_solar", node=test_node, portfolio=portfolio, maximum_power_forecast=max_power_forecast)
    return solar


@pytest.fixture
def test_wind(test_market_area, test_node, test_parameters):
    """Create a test wind unit."""
    start_date = test_parameters.temporal.start_date
    end_date = test_parameters.temporal.end_date
    timestep = test_parameters.temporal.timestep
    exec_date_da = test_parameters.execution_date_day_ahead
    exec_date_id = test_parameters.temporal.execution_date

    portfolio = Portfolio(
        name="test_portfolio_wind", control_block=test_market_area.control_block, market_area=test_market_area
    )

    max_power_forecast = ForecastingMatrix()
    ts_da = Timeseries.from_index(start_date, timestep, end_date, default_value=-300.0)
    max_power_forecast.add(ts_da, exec_date_da)

    ts_id = Timeseries.from_index(start_date, timestep, end_date, default_value=-280.0)
    max_power_forecast.add(ts_id, exec_date_id)

    wind = WindIDPF(name="test_wind", node=test_node, portfolio=portfolio, maximum_power_forecast=max_power_forecast)
    return wind


@pytest.fixture
def test_input_dataset(test_parameters, test_market_area, test_load, test_solar, test_wind):
    """Create a test input dataset."""
    atlas_dataset = AtlasDataset(market_area=[test_market_area], load=[test_load], solar=[test_solar], wind=[test_wind])
    return IntradayPriceForecastInputDataset(atlas_dataset, test_parameters)


@pytest.fixture
def module():
    return IntradayPriceForecastModule()


def test_filter_assets_by_market_area(module, test_parameters, test_input_dataset):
    """Test filtering assets by market area."""
    market_area = test_input_dataset.market_area[0]
    loads, solars, winds = module._filter_assets_by_market_area(market_area, test_input_dataset)

    assert len(loads) == 1
    assert len(solars) == 1
    assert len(winds) == 1
    assert loads[0].name == "test_load"
    assert solars[0].name == "test_solar"
    assert winds[0].name == "test_wind"


def test_create_empty_timeseries(module, test_parameters, test_input_dataset):
    """Test creating an empty timeseries."""
    ts = module._create_empty_timeseries(test_parameters)

    assert isinstance(ts, Timeseries)
    assert ts.get_value(test_parameters.temporal.start_date) == 0
    assert test_parameters.temporal.start_date in ts


def test_compute_price_sensitivity_ratio(module, test_parameters, test_input_dataset):
    """Test computing price sensitivity ratio."""
    market_area = test_input_dataset.market_area[0]
    loads, solars, winds = module._filter_assets_by_market_area(market_area, test_input_dataset)

    time_window = generate_datetimes(
        test_parameters.temporal.start_date, test_parameters.penultimate_date, test_parameters.temporal.timestep
    )

    ratio = module._compute_price_sensitivity_ratio(market_area, loads, time_window, test_parameters)

    assert isinstance(ratio, Timeseries)
    # Price diff = 100 - 50 = 50
    # Consumption diff = 800 - 1200 = -400
    # Ratio = 50 / -400 = -0.125
    expected_ratio = -0.125
    assert ratio.get_value(test_parameters.temporal.start_date) == pytest.approx(expected_ratio, abs=0.001)


def test_compute_consumption_delta(module, test_parameters, test_input_dataset):
    """Test computing consumption delta."""
    market_area = test_input_dataset.market_area[0]
    loads, solars, winds = module._filter_assets_by_market_area(market_area, test_input_dataset)

    time_window = generate_datetimes(
        test_parameters.temporal.start_date, test_parameters.penultimate_date, test_parameters.temporal.timestep
    )

    delta = module._compute_consumption_delta(loads, solars, winds, test_parameters)

    assert isinstance(delta, Timeseries)
    # Intraday residual: -(1100 - 180 - 280) = -640
    # Day-ahead residual: -(1000 - 200 - 300) = -500
    # Delta = -640 - (-500) = -140
    expected_delta = -140.0
    assert delta.get_value(test_parameters.temporal.start_date) == pytest.approx(expected_delta, abs=0.001)


def test_get_baseline_price_da_price(module, test_parameters, test_input_dataset):
    """Test getting baseline price when only day-ahead price is available."""
    market_area = test_input_dataset.market_area[0]
    baseline_price, label = module._get_baseline_price(market_area, test_parameters)

    assert isinstance(baseline_price, Timeseries)
    assert label == "Day Ahead price"
    assert baseline_price.get_value(test_parameters.temporal.start_date) == 75.0


def test_apply_price_caps_upper(module, test_parameters, test_input_dataset):
    """Test applying upper price cap."""
    time_window = generate_datetimes(
        test_parameters.temporal.start_date, test_parameters.penultimate_date, test_parameters.temporal.timestep
    )

    ts = Timeseries.from_index(
        test_parameters.temporal.start_date, test_parameters.temporal.timestep, test_parameters.temporal.end_date
    )
    ts.set_value(test_parameters.temporal.start_date, 5000.0)  # Exceeds cap of 4000
    ts.set_value(test_parameters.temporal.start_date + test_parameters.temporal.timestep, 5000.0)

    market_area = test_input_dataset.market_area[0]
    result = module._apply_price_caps(ts, market_area, time_window, test_parameters)

    # All values should be scaled down proportionally
    assert result.get_value(test_parameters.temporal.start_date) <= 4000.0
    assert result.get_value(test_parameters.temporal.start_date + test_parameters.temporal.timestep) <= 4000.0


def test_apply_price_caps_lower(module, test_parameters, test_input_dataset):
    """Test applying lower price cap."""
    time_window = generate_datetimes(
        test_parameters.temporal.start_date, test_parameters.penultimate_date, test_parameters.temporal.timestep
    )

    # Create timeseries with values below lower cap
    ts = Timeseries.from_index(
        test_parameters.temporal.start_date, test_parameters.temporal.timestep, test_parameters.temporal.end_date
    )
    ts.set_value(test_parameters.temporal.start_date, -600.0)  # Below cap of -500
    ts.set_value(test_parameters.temporal.start_date + test_parameters.temporal.timestep, -600.0)

    market_area = test_input_dataset.market_area[0]
    result = module._apply_price_caps(ts, market_area, time_window, test_parameters)

    # All values should be scaled up proportionally
    assert result.get_value(test_parameters.temporal.start_date) >= -500.0
    assert result.get_value(test_parameters.temporal.start_date + test_parameters.temporal.timestep) >= -500.0


def test_execute(module, test_parameters, test_input_dataset):
    """Test full execution of the module."""
    output_dataset = module.execute(test_parameters, test_input_dataset)

    assert isinstance(output_dataset, IntradayPriceForecastOutputDataset)
    assert len(output_dataset.market_area) == 1

    market_area = output_dataset.market_area[0]
    assert market_area.id_price_forecast is not None
    assert test_parameters.temporal.execution_date in market_area.id_price_forecast


def test_save_price_forecast(module, test_parameters, test_input_dataset):
    """Test saving price forecast to market area."""
    output_dataset = IntradayPriceForecastOutputDataset(test_parameters, test_input_dataset)
    market_area = output_dataset.market_area[0]

    price_forecast = Timeseries.from_index(
        test_parameters.temporal.start_date,
        test_parameters.temporal.timestep,
        test_parameters.temporal.end_date,
        default_value=100.0,
    )

    module._save_price_forecast(market_area, price_forecast, test_parameters)

    assert market_area.id_price_forecast is not None
    assert test_parameters.temporal.execution_date in market_area.id_price_forecast
