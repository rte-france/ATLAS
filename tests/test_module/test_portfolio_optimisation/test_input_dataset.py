"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from unittest.mock import Mock, patch

import pendulum
import pytest

from atlas.enums import LoadType, MarketType
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.io_utils.parameters import DateParameters
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.portfolio_optimisation.input_dataset import PortfolioOptimisationInputDataset
from atlas.modules.portfolio_optimisation.models.hydro import HydroPO
from atlas.modules.portfolio_optimisation.models.load import LoadPO
from atlas.modules.portfolio_optimisation.models.solar import SolarPO
from atlas.modules.portfolio_optimisation.models.storage import StoragePO
from atlas.modules.portfolio_optimisation.models.wind import WindPO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.objects.equipment.hydro import Hydro
from atlas.objects.equipment.load import Load
from atlas.objects.equipment.solar import Solar
from atlas.objects.equipment.storage import Storage
from atlas.objects.equipment.wind import Wind
from atlas.objects.market.market_area import MarketArea
from atlas.objects.market_operator.portfolio import Portfolio
from atlas.objects.network.node import Node
from atlas.objects.network_operator.control_block import ControlBlock


def make_date(**kwargs):
    return DateParameters(
        start_date=pendulum.datetime(2024, 1, 1),
        end_date=pendulum.datetime(2024, 1, 2),
        execution_date=pendulum.datetime(2024, 1, 1),
        **kwargs,
    )


class TestPortfolioOptimisationInputDataset:
    """Test suite for PortfolioOptimisationInputDataset class."""

    @pytest.fixture
    def mock_parameters(self):
        """Create mock parameters for testing."""
        params = Mock(spec=PortfolioOptimisationParameters)
        params.temporal = make_date()
        params.market = MarketType.dayahead
        params.use_forecast = False
        params.excluded_technologies = []
        params.excluded_thermal_strategies = []
        params.excluded_market_areas = []
        return params

    @pytest.fixture
    def mock_portfolio(self):
        """Create a real Portfolio object."""
        price_forecast = ForecastingMatrix()
        da_price = Timeseries.from_index(
            pendulum.datetime(2024, 1, 1), pendulum.duration(hours=1), pendulum.datetime(2024, 1, 2), default_value=50.0
        )

        control_block = ControlBlock(name="test_control_block")

        market_area = MarketArea(
            name="test_market",
            control_block=control_block,
            price_forecast_medium=price_forecast,
            da_price=da_price,
        )

        portfolio = Portfolio(
            name="test_portfolio",
            control_block=control_block,
            market_area=market_area,
        )

        return portfolio

    @pytest.fixture
    def mock_node(self, mock_portfolio):
        """Create a real Node object."""
        return Node(
            name="test_node",
            control_block=mock_portfolio.control_block,
            market_area=mock_portfolio.market_area,
        )

    @pytest.fixture
    def mock_wind_equipment(self, mock_portfolio, mock_node):
        """Create a real Wind equipment."""
        return Wind(name="wind_1", portfolio=mock_portfolio, node=mock_node)

    @pytest.fixture
    def mock_solar_equipment(self, mock_portfolio, mock_node):
        """Create a real Solar equipment."""
        return Solar(name="solar_1", portfolio=mock_portfolio, node=mock_node)

    @pytest.fixture
    def mock_storage_equipment(self, mock_portfolio, mock_node):
        """Create a real Storage equipment."""
        return Storage(name="storage_1", portfolio=mock_portfolio, node=mock_node)

    @pytest.fixture
    def mock_hydro_equipment(self, mock_portfolio, mock_node):
        """Create a real Hydro equipment."""
        return Hydro(name="hydro_1", portfolio=mock_portfolio, node=mock_node)

    @pytest.fixture
    def mock_dispatchable_load(self, mock_portfolio, mock_node):
        """Create a real dispatchable Load equipment (Power to Gas)."""
        return Load(name="load_dispatchable", load_type=LoadType.POWER_TO_GAS, portfolio=mock_portfolio, node=mock_node)

    @pytest.fixture
    def mock_non_dispatchable_load(self, mock_portfolio, mock_node):
        """Create a real non-dispatchable Load equipment."""
        return Load(name="load_non_dispatchable", load_type=LoadType.BASE_LOAD, portfolio=mock_portfolio, node=mock_node)

    @patch("atlas.modules.portfolio_optimisation.input_dataset.WindPO")
    def test_initialization_with_wind_equipment(self, mock_wind_po_class, mock_parameters, mock_wind_equipment):
        """Test that InputDataset initializes correctly with wind equipment."""
        mock_wind_po_instance = Mock(spec=WindPO)
        mock_wind_po_instance.portfolio = mock_wind_equipment.portfolio
        mock_wind_po_instance.get_optimisation_time_window = Mock(
            return_value=[pendulum.datetime(2024, 1, 1), pendulum.datetime(2024, 1, 2)]
        )
        mock_wind_po_class.return_value = mock_wind_po_instance

        input_data = AtlasDataset(wind=[mock_wind_equipment])
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

        assert dataset.input_data == input_data
        assert dataset.parameters == mock_parameters
        assert len(dataset.equipments.wind) == 1
        mock_wind_po_class.assert_called_once()

    @patch("atlas.modules.portfolio_optimisation.input_dataset.SolarPO")
    def test_initialization_with_solar_equipment(self, mock_solar_po_class, mock_parameters, mock_solar_equipment):
        """Test that InputDataset initializes correctly with solar equipment."""
        mock_solar_po_instance = Mock(spec=SolarPO)
        mock_solar_po_instance.portfolio = mock_solar_equipment.portfolio
        mock_solar_po_instance.get_optimisation_time_window = Mock(
            return_value=[pendulum.datetime(2024, 1, 1), pendulum.datetime(2024, 1, 2)]
        )
        mock_solar_po_class.return_value = mock_solar_po_instance

        input_data = AtlasDataset(solar=[mock_solar_equipment])
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

        assert len(dataset.equipments.solar) == 1
        mock_solar_po_class.assert_called_once()

    @patch("atlas.modules.portfolio_optimisation.input_dataset.StoragePO")
    def test_initialization_with_storage_equipment(
        self, mock_storage_po_class, mock_parameters, mock_storage_equipment
    ):
        """Test that InputDataset initializes correctly with storage equipment."""
        mock_storage_po_instance = Mock(spec=StoragePO)
        mock_storage_po_instance.portfolio = mock_storage_equipment.portfolio
        mock_storage_po_instance.get_optimisation_time_window = Mock(
            return_value=[pendulum.datetime(2024, 1, 1), pendulum.datetime(2024, 1, 2)]
        )
        mock_storage_po_class.return_value = mock_storage_po_instance

        input_data = AtlasDataset(storage=[mock_storage_equipment])
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

        assert len(dataset.equipments.storage) == 1
        mock_storage_po_class.assert_called_once()

    @patch("atlas.modules.portfolio_optimisation.input_dataset.HydroPO")
    def test_initialization_with_hydro_equipment(self, mock_hydro_po_class, mock_parameters, mock_hydro_equipment):
        """Test that InputDataset initializes correctly with hydro equipment."""
        mock_hydro_po_instance = Mock(spec=HydroPO)
        mock_hydro_po_instance.portfolio = mock_hydro_equipment.portfolio
        mock_hydro_po_instance.get_optimisation_time_window = Mock(
            return_value=[pendulum.datetime(2024, 1, 1), pendulum.datetime(2024, 1, 2)]
        )
        mock_hydro_po_class.return_value = mock_hydro_po_instance

        input_data = AtlasDataset(hydro=[mock_hydro_equipment])
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

        assert len(dataset.equipments.hydro) == 1
        mock_hydro_po_class.assert_called_once()

    @patch("atlas.modules.portfolio_optimisation.input_dataset.LoadPO")
    def test_load_classification_dispatchable(self, mock_load_po_class, mock_parameters, mock_dispatchable_load):
        """Test that dispatchable loads (Power to Gas) are correctly classified."""
        mock_load_po_instance = Mock(spec=LoadPO)
        mock_load_po_instance.load_type = LoadType.POWER_TO_GAS
        mock_load_po_instance.portfolio = mock_dispatchable_load.portfolio
        mock_load_po_instance.get_optimisation_time_window = Mock(
            return_value=[pendulum.datetime(2024, 1, 1), pendulum.datetime(2024, 1, 2)]
        )
        mock_load_po_class.return_value = mock_load_po_instance

        input_data = AtlasDataset(load=[mock_dispatchable_load])
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

        assert len(dataset.equipments.dispatchable_load) == 1
        assert len(dataset.equipments.non_dispatchable_load) == 0

    @patch("atlas.modules.portfolio_optimisation.input_dataset.LoadPO")
    def test_load_classification_non_dispatchable(
        self, mock_load_po_class, mock_parameters, mock_non_dispatchable_load
    ):
        """Test that non-dispatchable loads are correctly classified."""
        mock_load_po_instance = Mock(spec=LoadPO)
        mock_load_po_instance.load_type = LoadType.BASE_LOAD
        mock_load_po_instance.portfolio = mock_non_dispatchable_load.portfolio
        mock_load_po_instance.get_optimisation_time_window = Mock(
            return_value=[pendulum.datetime(2024, 1, 1), pendulum.datetime(2024, 1, 2)]
        )
        mock_load_po_class.return_value = mock_load_po_instance

        input_data = AtlasDataset(load=[mock_non_dispatchable_load])
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

        assert len(dataset.equipments.dispatchable_load) == 0
        assert len(dataset.equipments.non_dispatchable_load) == 1

    @patch("atlas.modules.portfolio_optimisation.input_dataset.LoadPO")
    def test_load_classification_mixed(
        self, mock_load_po_class, mock_parameters, mock_dispatchable_load, mock_non_dispatchable_load
    ):
        """Test classification with both dispatchable and non-dispatchable loads."""
        mock_disp_instance = Mock(spec=LoadPO)
        mock_disp_instance.load_type = LoadType.POWER_TO_GAS
        mock_disp_instance.portfolio = mock_dispatchable_load.portfolio
        mock_disp_instance.get_optimisation_time_window = Mock(
            return_value=[pendulum.datetime(2024, 1, 1), pendulum.datetime(2024, 1, 2)]
        )

        mock_non_disp_instance = Mock(spec=LoadPO)
        mock_non_disp_instance.load_type = LoadType.BASE_LOAD
        mock_non_disp_instance.portfolio = mock_non_dispatchable_load.portfolio
        mock_non_disp_instance.get_optimisation_time_window = Mock(
            return_value=[pendulum.datetime(2024, 1, 1), pendulum.datetime(2024, 1, 2)]
        )

        mock_load_po_class.side_effect = [mock_disp_instance, mock_non_disp_instance]

        input_data = AtlasDataset(load=[mock_dispatchable_load, mock_non_dispatchable_load])
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

        assert len(dataset.equipments.dispatchable_load) == 1
        assert len(dataset.equipments.non_dispatchable_load) == 1

    def test_initialization_with_empty_input_data(self, mock_parameters):
        """Test that InputDataset handles empty input data gracefully."""
        input_data = AtlasDataset()
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

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
        mock_wind_po_instance = Mock(spec=WindPO)
        mock_wind_po_instance.portfolio = mock_wind_equipment.portfolio
        mock_wind_po_instance.get_optimisation_time_window = Mock(
            return_value=[pendulum.datetime(2024, 1, 1), pendulum.datetime(2024, 1, 2)]
        )
        mock_wind_po_class.return_value = mock_wind_po_instance
        mock_should_manually_activate.return_value = True
        mock_is_excluded_market.return_value = False

        input_data = AtlasDataset(wind=[mock_wind_equipment])
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

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
        mock_wind_po_instance = Mock(spec=WindPO)
        mock_wind_po_instance.portfolio = mock_wind_equipment.portfolio
        mock_wind_po_instance.get_optimisation_time_window = Mock(
            return_value=[pendulum.datetime(2024, 1, 1), pendulum.datetime(2024, 1, 2)]
        )
        mock_wind_po_class.return_value = mock_wind_po_instance
        mock_should_manually_activate.return_value = False
        mock_is_excluded_market.return_value = True

        input_data = AtlasDataset(wind=[mock_wind_equipment])
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

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
        mock_wind_po_instance = Mock(spec=WindPO)
        mock_wind_po_instance.portfolio = mock_wind_equipment.portfolio
        mock_wind_po_instance.get_optimisation_time_window = Mock(
            return_value=[pendulum.datetime(2024, 1, 1), pendulum.datetime(2024, 1, 2)]
        )
        mock_wind_po_class.return_value = mock_wind_po_instance
        mock_should_manually_activate.return_value = False
        mock_is_excluded_market.return_value = False

        input_data = AtlasDataset(wind=[mock_wind_equipment])
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

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
        mock_wind_po_instance = Mock(spec=WindPO)
        mock_wind_po_instance.portfolio = mock_wind_equipment.portfolio
        mock_wind_po_instance.get_optimisation_time_window = Mock(
            return_value=[pendulum.datetime(2024, 1, 1), pendulum.datetime(2024, 1, 2)]
        )
        mock_wind_po_class.return_value = mock_wind_po_instance

        mock_solar_po_instance = Mock(spec=SolarPO)
        mock_solar_po_instance.portfolio = mock_solar_equipment.portfolio
        mock_solar_po_instance.get_optimisation_time_window = Mock(
            return_value=[pendulum.datetime(2024, 1, 1), pendulum.datetime(2024, 1, 2)]
        )
        mock_solar_po_class.return_value = mock_solar_po_instance

        mock_should_manually_activate.side_effect = [False, True]
        mock_is_excluded_market.return_value = False

        input_data = AtlasDataset(wind=[mock_wind_equipment], solar=[mock_solar_equipment])
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

        assert len(dataset.portfolios) == 1
        assert len(dataset.portfolios_manual_activation) == 1
        assert len(dataset.portfolios[0].equipments.wind) == 1
        assert len(dataset.portfolios_manual_activation[0].equipments.solar) == 1

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
        expected_time_window = [
            pendulum.datetime(2024, 1, 1),
            pendulum.datetime(2024, 1, 1, 12),
            pendulum.datetime(2024, 1, 2),
        ]

        mock_wind_po_instance = Mock(spec=WindPO)
        mock_wind_po_instance.portfolio = mock_wind_equipment.portfolio
        mock_wind_po_instance.get_optimisation_time_window = Mock(return_value=expected_time_window)
        mock_wind_po_class.return_value = mock_wind_po_instance
        mock_should_manually_activate.return_value = False
        mock_is_excluded_market.return_value = False

        input_data = AtlasDataset(wind=[mock_wind_equipment])
        dataset = PortfolioOptimisationInputDataset(input_data, mock_parameters)

        assert "test_portfolio" in dataset.time_windows
        assert dataset.time_windows["test_portfolio"] == expected_time_window
