"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from unittest.mock import MagicMock, Mock, patch

import pendulum
import pytest

from atlas import Portfolio
from atlas.enum import LoadType, MarketType, ThermalStrategy
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.control_block import ControlBlock
from atlas.models.equipment.hydro import Hydro
from atlas.models.equipment.load import Load
from atlas.models.equipment.solar import Solar
from atlas.models.equipment.storage import Storage
from atlas.models.equipment.wind import Wind
from atlas.models.market.market_area import MarketArea
from atlas.modules.portfolio_optimisation.input_dataset import PortfolioOptimisationInputDataset
from atlas.modules.portfolio_optimisation.models.hydro import HydroPO
from atlas.modules.portfolio_optimisation.models.load import LoadPO
from atlas.modules.portfolio_optimisation.models.solar import SolarPO
from atlas.modules.portfolio_optimisation.models.storage import StoragePO
from atlas.modules.portfolio_optimisation.models.wind import WindPO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class TestPortfolioOptimisationInputDataset:
    """Test suite for PortfolioOptimisationInputDataset class."""

    @pytest.fixture
    def mock_parameters(self):
        """Create mock parameters for testing."""
        params = Mock(spec=PortfolioOptimisationParameters)
        params.start_date = pendulum.datetime(2024, 1, 1)
        params.end_date = pendulum.datetime(2024, 1, 2)
        params.timestep = pendulum.duration(hours=1)
        params.market = MarketType.dayahead
        params.use_forecast = False
        params.excluded_technologies = []
        params.excluded_thermal_strategies = []
        params.excluded_market_areas = []
        return params

    @pytest.fixture
    def mock_portfolio(self):
        """Create a mock Portfolio object."""
        portfolio = Mock(spec=Portfolio)
        portfolio.name = "test_portfolio"

        # Create a mock MarketArea
        market_area = Mock(spec=MarketArea)
        market_area.name = "test_market"
        market_area.set_market_context = Mock(return_value=market_area)
        portfolio.market_area = market_area

        # Create minimal ForecastingMatrix and Timeseries for market area
        price_forecast = ForecastingMatrix()
        da_price = Timeseries.from_index(
            pendulum.datetime(2024, 1, 1), pendulum.duration(hours=1), pendulum.datetime(2024, 1, 2), default_value=50.0
        )

        # Create minimal valid dictionaries for Pydantic validation
        portfolio.model_dump.return_value = {
            "name": "test_portfolio",
            "control_block": {
                "name": "test_control_block",
            },
            "market_area": {
                "name": "test_market",
                "price_forecast_medium": price_forecast,
                "da_price": da_price,
            },
        }

        return portfolio

    @pytest.fixture
    def mock_wind_equipment(self, mock_portfolio):
        """Create a mock Wind equipment."""
        wind = Mock(spec=Wind)
        wind.name = "wind_1"
        wind.portfolio = mock_portfolio
        wind.model_dump.return_value = {
            "name": "wind_1",
            "portfolio": mock_portfolio.model_dump(),
        }
        wind.get_optimisation_time_window = Mock(
            return_value=[
                pendulum.datetime(2024, 1, 1),
                pendulum.datetime(2024, 1, 2),
            ]
        )
        return wind

    @pytest.fixture
    def mock_solar_equipment(self, mock_portfolio):
        """Create a mock Solar equipment."""
        solar = Mock(spec=Solar)
        solar.name = "solar_1"
        solar.portfolio = mock_portfolio
        solar.model_dump.return_value = {
            "name": "solar_1",
            "portfolio": mock_portfolio.model_dump(),
        }
        solar.get_optimisation_time_window = Mock(
            return_value=[
                pendulum.datetime(2024, 1, 1),
                pendulum.datetime(2024, 1, 2),
            ]
        )
        return solar

    @pytest.fixture
    def mock_storage_equipment(self, mock_portfolio):
        """Create a mock Storage equipment."""
        storage = Mock(spec=Storage)
        storage.name = "storage_1"
        storage.portfolio = mock_portfolio
        storage.model_dump.return_value = {
            "name": "storage_1",
            "portfolio": mock_portfolio.model_dump(),
        }
        storage.get_optimisation_time_window = Mock(
            return_value=[
                pendulum.datetime(2024, 1, 1),
                pendulum.datetime(2024, 1, 2),
            ]
        )
        return storage

    @pytest.fixture
    def mock_hydro_equipment(self, mock_portfolio):
        """Create a mock Hydro equipment."""
        hydro = Mock(spec=Hydro)
        hydro.name = "hydro_1"
        hydro.portfolio = mock_portfolio
        hydro.model_dump.return_value = {
            "name": "hydro_1",
            "portfolio": mock_portfolio.model_dump(),
        }
        hydro.get_optimisation_time_window = Mock(
            return_value=[
                pendulum.datetime(2024, 1, 1),
                pendulum.datetime(2024, 1, 2),
            ]
        )
        return hydro

    @pytest.fixture
    def mock_dispatchable_load(self, mock_portfolio):
        """Create a mock dispatchable Load equipment (Power to Gas)."""
        load = Mock(spec=Load)
        load.name = "load_dispatchable"
        load.portfolio = mock_portfolio
        load.load_type = LoadType.POWER_TO_GAS
        load.model_dump.return_value = {
            "name": "load_dispatchable",
            "load_type": LoadType.POWER_TO_GAS,
            "portfolio": mock_portfolio.model_dump(),
        }
        load.get_optimisation_time_window = Mock(
            return_value=[
                pendulum.datetime(2024, 1, 1),
                pendulum.datetime(2024, 1, 2),
            ]
        )
        return load

    @pytest.fixture
    def mock_non_dispatchable_load(self, mock_portfolio):
        """Create a mock non-dispatchable Load equipment."""
        load = Mock(spec=Load)
        load.name = "load_non_dispatchable"
        load.portfolio = mock_portfolio
        load.load_type = LoadType.BASE_LOAD
        load.model_dump.return_value = {
            "name": "load_non_dispatchable",
            "load_type": LoadType.BASE_LOAD,
            "portfolio": mock_portfolio.model_dump(),
        }
        load.get_optimisation_time_window = Mock(
            return_value=[
                pendulum.datetime(2024, 1, 1),
                pendulum.datetime(2024, 1, 2),
            ]
        )
        return load

    @patch("atlas.modules.portfolio_optimisation.input_dataset.WindPO")
    def test_initialization_with_wind_equipment(self, mock_wind_po_class, mock_parameters, mock_wind_equipment):
        """Test that InputDataset initializes correctly with wind equipment."""
        # Setup mock
        mock_wind_po_instance = Mock(spec=WindPO)
        mock_wind_po_instance.portfolio = mock_wind_equipment.portfolio
        mock_wind_po_instance.get_optimisation_time_window = Mock(
            return_value=[
                pendulum.datetime(2024, 1, 1),
                pendulum.datetime(2024, 1, 2),
            ]
        )
        mock_wind_po_class.model_validate.return_value = mock_wind_po_instance

        input_data = {"wind": [mock_wind_equipment]}

        # Create dataset
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

        # Assertions
        assert dataset.input_data == input_data
        assert dataset.parameters == mock_parameters
        assert len(dataset.equipments.wind) == 1
        mock_wind_po_class.model_validate.assert_called_once()

    @patch("atlas.modules.portfolio_optimisation.input_dataset.SolarPO")
    def test_initialization_with_solar_equipment(self, mock_solar_po_class, mock_parameters, mock_solar_equipment):
        """Test that InputDataset initializes correctly with solar equipment."""
        # Setup mock
        mock_solar_po_instance = Mock(spec=SolarPO)
        mock_solar_po_instance.portfolio = mock_solar_equipment.portfolio
        mock_solar_po_instance.get_optimisation_time_window = Mock(
            return_value=[
                pendulum.datetime(2024, 1, 1),
                pendulum.datetime(2024, 1, 2),
            ]
        )
        mock_solar_po_class.model_validate.return_value = mock_solar_po_instance

        input_data = {"solar": [mock_solar_equipment]}

        # Create dataset
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

        # Assertions
        assert len(dataset.equipments.solar) == 1
        mock_solar_po_class.model_validate.assert_called_once()

    @patch("atlas.modules.portfolio_optimisation.input_dataset.StoragePO")
    def test_initialization_with_storage_equipment(
        self, mock_storage_po_class, mock_parameters, mock_storage_equipment
    ):
        """Test that InputDataset initializes correctly with storage equipment."""
        # Setup mock
        mock_storage_po_instance = Mock(spec=StoragePO)
        mock_storage_po_instance.portfolio = mock_storage_equipment.portfolio
        mock_storage_po_instance.get_optimisation_time_window = Mock(
            return_value=[
                pendulum.datetime(2024, 1, 1),
                pendulum.datetime(2024, 1, 2),
            ]
        )
        mock_storage_po_class.model_validate.return_value = mock_storage_po_instance

        input_data = {"storage": [mock_storage_equipment]}

        # Create dataset
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

        # Assertions
        assert len(dataset.equipments.storage) == 1
        mock_storage_po_class.model_validate.assert_called_once()

    @patch("atlas.modules.portfolio_optimisation.input_dataset.HydroPO")
    def test_initialization_with_hydro_equipment(self, mock_hydro_po_class, mock_parameters, mock_hydro_equipment):
        """Test that InputDataset initializes correctly with hydro equipment."""
        # Setup mock
        mock_hydro_po_instance = Mock(spec=HydroPO)
        mock_hydro_po_instance.portfolio = mock_hydro_equipment.portfolio
        mock_hydro_po_instance.get_optimisation_time_window = Mock(
            return_value=[
                pendulum.datetime(2024, 1, 1),
                pendulum.datetime(2024, 1, 2),
            ]
        )
        mock_hydro_po_class.model_validate.return_value = mock_hydro_po_instance

        input_data = {"hydro": [mock_hydro_equipment]}

        # Create dataset
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

        # Assertions
        assert len(dataset.equipments.hydro) == 1
        mock_hydro_po_class.model_validate.assert_called_once()

    @patch("atlas.modules.portfolio_optimisation.input_dataset.LoadPO")
    def test_load_classification_dispatchable(self, mock_load_po_class, mock_parameters, mock_dispatchable_load):
        """Test that dispatchable loads (Power to Gas) are correctly classified."""
        # Setup mock
        mock_load_po_instance = Mock(spec=LoadPO)
        mock_load_po_instance.load_type = LoadType.POWER_TO_GAS
        mock_load_po_instance.portfolio = mock_dispatchable_load.portfolio
        mock_load_po_instance.get_optimisation_time_window = Mock(
            return_value=[
                pendulum.datetime(2024, 1, 1),
                pendulum.datetime(2024, 1, 2),
            ]
        )
        mock_load_po_class.model_validate.return_value = mock_load_po_instance

        input_data = {"load": [mock_dispatchable_load]}

        # Create dataset
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

        # Assertions
        assert len(dataset.equipments.dispatchable_load) == 1
        assert len(dataset.equipments.non_dispatchable_load) == 0

    @patch("atlas.modules.portfolio_optimisation.input_dataset.LoadPO")
    def test_load_classification_non_dispatchable(
        self, mock_load_po_class, mock_parameters, mock_non_dispatchable_load
    ):
        """Test that non-dispatchable loads are correctly classified."""
        # Setup mock
        mock_load_po_instance = Mock(spec=LoadPO)
        mock_load_po_instance.load_type = LoadType.BASE_LOAD
        mock_load_po_instance.portfolio = mock_non_dispatchable_load.portfolio
        mock_load_po_instance.get_optimisation_time_window = Mock(
            return_value=[
                pendulum.datetime(2024, 1, 1),
                pendulum.datetime(2024, 1, 2),
            ]
        )
        mock_load_po_class.model_validate.return_value = mock_load_po_instance

        input_data = {"load": [mock_non_dispatchable_load]}

        # Create dataset
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

        # Assertions
        assert len(dataset.equipments.dispatchable_load) == 0
        assert len(dataset.equipments.non_dispatchable_load) == 1

    @patch("atlas.modules.portfolio_optimisation.input_dataset.LoadPO")
    def test_load_classification_mixed(
        self, mock_load_po_class, mock_parameters, mock_dispatchable_load, mock_non_dispatchable_load
    ):
        """Test classification with both dispatchable and non-dispatchable loads."""
        # Setup mocks
        mock_disp_instance = Mock(spec=LoadPO)
        mock_disp_instance.load_type = LoadType.POWER_TO_GAS
        mock_disp_instance.portfolio = mock_dispatchable_load.portfolio
        mock_disp_instance.get_optimisation_time_window = Mock(
            return_value=[
                pendulum.datetime(2024, 1, 1),
                pendulum.datetime(2024, 1, 2),
            ]
        )

        mock_non_disp_instance = Mock(spec=LoadPO)
        mock_non_disp_instance.load_type = LoadType.BASE_LOAD
        mock_non_disp_instance.portfolio = mock_non_dispatchable_load.portfolio
        mock_non_disp_instance.get_optimisation_time_window = Mock(
            return_value=[
                pendulum.datetime(2024, 1, 1),
                pendulum.datetime(2024, 1, 2),
            ]
        )

        mock_load_po_class.model_validate.side_effect = [mock_disp_instance, mock_non_disp_instance]

        input_data = {"load": [mock_dispatchable_load, mock_non_dispatchable_load]}

        # Create dataset
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

        # Assertions
        assert len(dataset.equipments.dispatchable_load) == 1
        assert len(dataset.equipments.non_dispatchable_load) == 1

    def test_initialization_with_empty_input_data(self, mock_parameters):
        """Test that InputDataset handles empty input data gracefully."""
        input_data = {}

        # Create dataset
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

        # Assertions
        assert len(dataset.equipments.get_all_equipment()) == 0
        assert dataset.portfolios == []
        assert dataset.portfolios_manual_activation == []

    @patch("atlas.modules.portfolio_optimisation.input_dataset.should_manually_activate")
    @patch("atlas.modules.portfolio_optimisation.input_dataset.is_excluded_market_area")
    @patch("atlas.modules.portfolio_optimisation.input_dataset.WindPO")
    def test_portfolio_creation_with_excluded_technology(
        self,
        mock_wind_po_class,
        mock_is_excluded_market,
        mock_should_manually_activate,
        mock_parameters,
        mock_wind_equipment,
    ):
        """Test that equipment excluded by technology is placed in manual activation portfolio."""
        # Setup mocks
        mock_wind_po_instance = Mock(spec=WindPO)
        mock_wind_po_instance.portfolio = mock_wind_equipment.portfolio
        mock_wind_po_instance.get_optimisation_time_window = Mock(
            return_value=[
                pendulum.datetime(2024, 1, 1),
                pendulum.datetime(2024, 1, 2),
            ]
        )
        mock_wind_po_class.model_validate.return_value = mock_wind_po_instance

        mock_should_manually_activate.return_value = True
        mock_is_excluded_market.return_value = False

        input_data = {"wind": [mock_wind_equipment]}

        # Create dataset
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

        # Assertions
        assert len(dataset.portfolios) == 0
        assert len(dataset.portfolios_manual_activation) == 1
        assert len(dataset.portfolios_manual_activation[0].equipments.wind) == 1

    @patch("atlas.modules.portfolio_optimisation.input_dataset.should_manually_activate")
    @patch("atlas.modules.portfolio_optimisation.input_dataset.is_excluded_market_area")
    @patch("atlas.modules.portfolio_optimisation.input_dataset.WindPO")
    def test_portfolio_creation_with_excluded_market_area(
        self,
        mock_wind_po_class,
        mock_is_excluded_market,
        mock_should_manually_activate,
        mock_parameters,
        mock_wind_equipment,
    ):
        """Test that equipment in excluded market area is placed in manual activation portfolio."""
        # Setup mocks
        mock_wind_po_instance = Mock(spec=WindPO)
        mock_wind_po_instance.portfolio = mock_wind_equipment.portfolio
        mock_wind_po_instance.get_optimisation_time_window = Mock(
            return_value=[
                pendulum.datetime(2024, 1, 1),
                pendulum.datetime(2024, 1, 2),
            ]
        )
        mock_wind_po_class.model_validate.return_value = mock_wind_po_instance

        mock_should_manually_activate.return_value = False
        mock_is_excluded_market.return_value = True

        input_data = {"wind": [mock_wind_equipment]}

        # Create dataset
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

        # Assertions
        assert len(dataset.portfolios) == 0
        assert len(dataset.portfolios_manual_activation) == 1

    @patch("atlas.modules.portfolio_optimisation.input_dataset.should_manually_activate")
    @patch("atlas.modules.portfolio_optimisation.input_dataset.is_excluded_market_area")
    @patch("atlas.modules.portfolio_optimisation.input_dataset.WindPO")
    def test_portfolio_creation_with_included_equipment(
        self,
        mock_wind_po_class,
        mock_is_excluded_market,
        mock_should_manually_activate,
        mock_parameters,
        mock_wind_equipment,
    ):
        """Test that non-excluded equipment is placed in normal optimization portfolio."""
        # Setup mocks
        mock_wind_po_instance = Mock(spec=WindPO)
        mock_wind_po_instance.portfolio = mock_wind_equipment.portfolio
        mock_wind_po_instance.get_optimisation_time_window = Mock(
            return_value=[
                pendulum.datetime(2024, 1, 1),
                pendulum.datetime(2024, 1, 2),
            ]
        )
        mock_wind_po_class.model_validate.return_value = mock_wind_po_instance

        mock_should_manually_activate.return_value = False
        mock_is_excluded_market.return_value = False

        input_data = {"wind": [mock_wind_equipment]}

        # Create dataset
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

        # Assertions
        assert len(dataset.portfolios) == 1
        assert len(dataset.portfolios_manual_activation) == 0
        assert len(dataset.portfolios[0].equipments.wind) == 1

    @patch("atlas.modules.portfolio_optimisation.input_dataset.should_manually_activate")
    @patch("atlas.modules.portfolio_optimisation.input_dataset.is_excluded_market_area")
    @patch("atlas.modules.portfolio_optimisation.input_dataset.WindPO")
    @patch("atlas.modules.portfolio_optimisation.input_dataset.SolarPO")
    def test_portfolio_creation_mixed_equipment(
        self,
        mock_solar_po_class,
        mock_wind_po_class,
        mock_is_excluded_market,
        mock_should_manually_activate,
        mock_parameters,
        mock_wind_equipment,
        mock_solar_equipment,
    ):
        """Test portfolio creation with mixed included and excluded equipment."""
        # Setup mocks - wind is included, solar is excluded
        mock_wind_po_instance = Mock(spec=WindPO)
        mock_wind_po_instance.portfolio = mock_wind_equipment.portfolio
        mock_wind_po_instance.get_optimisation_time_window = Mock(
            return_value=[
                pendulum.datetime(2024, 1, 1),
                pendulum.datetime(2024, 1, 2),
            ]
        )
        mock_wind_po_class.model_validate.return_value = mock_wind_po_instance

        mock_solar_po_instance = Mock(spec=SolarPO)
        mock_solar_po_instance.portfolio = mock_solar_equipment.portfolio
        mock_solar_po_instance.get_optimisation_time_window = Mock(
            return_value=[
                pendulum.datetime(2024, 1, 1),
                pendulum.datetime(2024, 1, 2),
            ]
        )
        mock_solar_po_class.model_validate.return_value = mock_solar_po_instance

        # Wind is included, solar is manually activated
        mock_should_manually_activate.side_effect = [False, True]
        mock_is_excluded_market.return_value = False

        input_data = {"wind": [mock_wind_equipment], "solar": [mock_solar_equipment]}

        # Create dataset
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

        # Assertions
        assert len(dataset.portfolios) == 1
        assert len(dataset.portfolios_manual_activation) == 1
        assert len(dataset.portfolios[0].equipments.wind) == 1
        assert len(dataset.portfolios_manual_activation[0].equipments.solar) == 1

    def test_get_business_model_class_used(self, mock_parameters):
        """Test that get_business_model_class_used returns expected business model classes."""
        input_data = {}
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

        result = dataset.get_business_model_class_used()

        # Check that all expected classes are present
        from atlas.models.equipment.hydro import Hydro
        from atlas.models.equipment.load import Load
        from atlas.models.equipment.other_non_dispatchable import OtherNonDispatchable
        from atlas.models.equipment.solar import Solar
        from atlas.models.equipment.storage import Storage
        from atlas.models.equipment.thermal import Thermal
        from atlas.models.equipment.wind import Wind

        assert Thermal in result
        assert Load in result
        assert Hydro in result
        assert Storage in result
        assert Wind in result
        assert Solar in result
        assert OtherNonDispatchable in result

    @patch("atlas.modules.portfolio_optimisation.input_dataset.should_manually_activate")
    @patch("atlas.modules.portfolio_optimisation.input_dataset.is_excluded_market_area")
    @patch("atlas.modules.portfolio_optimisation.input_dataset.WindPO")
    def test_time_window_calculation(
        self,
        mock_wind_po_class,
        mock_is_excluded_market,
        mock_should_manually_activate,
        mock_parameters,
        mock_wind_equipment,
    ):
        """Test that time windows are correctly calculated for portfolios."""
        # Setup mocks
        expected_time_window = [
            pendulum.datetime(2024, 1, 1),
            pendulum.datetime(2024, 1, 1, 12),
            pendulum.datetime(2024, 1, 2),
        ]

        mock_wind_po_instance = Mock(spec=WindPO)
        mock_wind_po_instance.portfolio = mock_wind_equipment.portfolio
        mock_wind_po_instance.get_optimisation_time_window = Mock(return_value=expected_time_window)
        mock_wind_po_class.model_validate.return_value = mock_wind_po_instance

        mock_should_manually_activate.return_value = False
        mock_is_excluded_market.return_value = False

        input_data = {"wind": [mock_wind_equipment]}

        # Create dataset
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

        # Assertions
        assert "test_portfolio" in dataset.time_windows
        assert dataset.time_windows["test_portfolio"] == expected_time_window
