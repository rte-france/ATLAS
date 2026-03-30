import unittest
from datetime import datetime
from unittest.mock import Mock

import pendulum
import polars as pl
import pytest

from atlas import ControlBlock, Portfolio
from atlas.enums import LoadType
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.load import Load
from atlas.models.equipment.solar import Solar
from atlas.models.equipment.wind import Wind
from atlas.models.market.market_area import MarketArea
from atlas.modules.price_forecast.input_dataset import PriceForecastInputDataset
from atlas.modules.price_forecast.orchestrator import PriceForecastOrchestrator
from atlas.modules.price_forecast.parameters import PriceForecastParameters


class TestIDForecastInputDataset(unittest.TestCase):
    """Test suite for PriceForecastInputDataset class."""

    @pytest.fixture
    def mock_df(self):
        """Fixture for hourly data with two forecasts."""
        return pl.DataFrame(
            {
                "time": pl.datetime_range(
                    start=datetime(2025, 1, 1, 0, 0, 0),
                    end=datetime(2025, 1, 1, 4, 0, 0),
                    interval="1h",
                    time_unit="us",
                    eager=True,
                ),
                "2025-01-01 00:00:00": [1, 2, 3, 4, 5],
                "2025-01-01 01:00:00": [6, 7, 8, 9, 10],
            }
        )

    @pytest.fixture
    def mock_parameters(self):
        """Create mock parameters for testing."""
        params = Mock(spec=PriceForecastParameters)
        params.start_date = pendulum.datetime(2024, 1, 1)
        params.end_date = pendulum.datetime(2024, 1, 2)
        params.execution_date = (pendulum.datetime(2024, 1, 1),)
        params.time_step = pendulum.duration(hours=1)
        params.intraday_negative_price_cap = -500
        params.intraday_positive_price_cap = 4000
        params.execution_date_day_ahead = pendulum.datetime(2028, 9, 1, 12)
        params.execution_date_scenarios = pendulum.datetime(2028, 7, 1)
        return params

    @pytest.fixture
    def mock_portfolio(self):
        """Create a real Portfolio object."""
        # Create minimal ForecastingMatrix and Timeseries for market area
        price_forecast = ForecastingMatrix()
        da_price = Timeseries.from_index(
            pendulum.datetime(2024, 1, 1), pendulum.duration(hours=1), pendulum.datetime(2024, 1, 2), default_value=50.0
        )

        # Create a real ControlBlock
        control_block = ControlBlock(name="test_control_block")

        # Create a real MarketArea
        market_area = MarketArea(
            name="test_market",
            price_forecast_medium=price_forecast,
            da_price=da_price,
        )

        # Create a real Portfolio
        portfolio = Portfolio(
            name="test_portfolio",
            control_block=control_block,
            market_area=market_area,
        )

        return portfolio

    @pytest.fixture
    def mock_market_area(self, mock_portfolio):
        """Create a real Marker area."""
        market_area = MarketArea(
            name="marker_area_1",
            portfolio=mock_portfolio,
        )
        return market_area

    @pytest.fixture
    def mock_wind_equipment(self, mock_portfolio):
        """Create a real Wind equipment."""
        wind = Wind(
            name="wind_1",
            portfolio=mock_portfolio,
        )
        return wind

    @pytest.fixture
    def mock_solar_equipment(self, mock_portfolio):
        """Create a real Solar equipment."""
        solar = Solar(
            name="solar_1",
            portfolio=mock_portfolio,
        )
        return solar

    @pytest.fixture
    def mock_load(self):
        """Create a real base load equipment."""
        load = Load(
            name="load_base",
            load_type=LoadType.BASE_LOAD,
            portfolio=mock_portfolio,
        )
        return load

    def test_initialization_with_wind_equipment(
        self,
    ):
        """Test that InputDataset initializes correctly with wind equipment."""
        input_data = AtlasDataset(wind=[self.mock_wind_equipment])

        # Create dataset
        dataset = PriceForecastInputDataset(input_data, self.mock_parameters)

        # Assertions
        assert dataset.input_data == input_data
        assert len(dataset.wind) == 1

    def test_initialization_with_solar_equipment(self):
        """Test that InputDataset initializes correctly with solar equipment."""
        # Setup mock

        input_data = AtlasDataset(solar=[self.mock_solar_equipment])

        # Create dataset
        dataset = PriceForecastInputDataset(input_data, self.mock_parameters)

        # Assertions
        assert len(dataset.solar) == 1

    def test_initialization_with_market_area(self):
        """Test that InputDataset initializes correctly market area."""
        # Setup mock
        input_data = AtlasDataset(market_area=[self.mock_market_area])

        # Create dataset
        dataset = PriceForecastInputDataset(input_data, self.mock_parameters)

        # Assertions
        assert len(dataset.market_area) == 1

    def test_initialization_with_load(self):
        """Test that InputDataset initializes correctly load."""
        # Setup mock
        input_data = AtlasDataset(load=[self.mock_load])

        # Create dataset
        dataset = PriceForecastInputDataset(input_data, self.mock_parameters)

        # Assertions
        assert len(dataset.load) == 1

    def test_initialization_with_empty_input_data(self):
        """Test that InputDataset handles empty input data gracefully."""
        input_data = AtlasDataset()
        input_data.from_dict({})

        # Create dataset
        dataset = PriceForecastInputDataset(input_data, self.mock_parameters)

        # Assertions
        assert len(dataset.load) == 0
        assert len(dataset.solar) == 0
        assert len(dataset.wind) == 0
        assert len(dataset.market_area) == 0
