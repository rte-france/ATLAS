"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from unittest.mock import Mock

import pendulum
from pendulum import duration

from atlas.enums import StorageType, ThermalStrategy
from atlas.io_utils.parameters import DateParameters
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


def make_date(**kwargs):
    return DateParameters(
        start_date=pendulum.datetime(2024, 1, 1),
        end_date=pendulum.datetime(2024, 1, 2),
        execution_date=pendulum.datetime(2024, 1, 1),
        **kwargs,
    )


class TestPortfolioOptimisationParametersDurationValidator:
    """Test suite for duration field validator."""

    def test_parse_duration_all_duration_fields(self):
        """Test that all duration fields can be parsed correctly."""
        params = PortfolioOptimisationParameters(
            temporal=make_date(),
            battery_automated_reserve_duration="30m",
            battery_reserve_duration="45m",
            electric_vehicle_automated_reserve_duration="2m",
            electric_vehicle_reserve_duration="5m",
            pumped_hydraulic_automated_reserve_duration="90m",
            pumped_hydraulic_reserve_duration="120m",
        )

        assert params.battery_automated_reserve_duration == duration(minutes=30)
        assert params.battery_reserve_duration == duration(minutes=45)
        assert params.electric_vehicle_automated_reserve_duration == duration(minutes=2)
        assert params.electric_vehicle_reserve_duration == duration(minutes=5)
        assert params.pumped_hydraulic_automated_reserve_duration == duration(minutes=90)
        assert params.pumped_hydraulic_reserve_duration == duration(minutes=120)


class TestPortfolioOptimisationParametersExcludedMarketAreas:
    """Test suite for excluded_market_areas property."""

    def test_excluded_market_areas_none(self):
        """Test excluded_market_areas when None."""
        params = PortfolioOptimisationParameters(
            temporal=make_date(),
            excluded_market_areas=None,
        )

        assert params.excluded_market_areas == []

    def test_excluded_market_areas_none_string(self):
        """Test excluded_market_areas when ['none']."""
        params = PortfolioOptimisationParameters(
            temporal=make_date(),
            excluded_market_areas=["none"],
        )

        assert params.excluded_market_areas == []

    def test_excluded_market_areas_none_string_mixed_case(self):
        """Test excluded_market_areas when ['None']."""
        params = PortfolioOptimisationParameters(
            temporal=make_date(),
            excluded_market_areas=["None"],
        )

        assert params.excluded_market_areas == []

    def test_excluded_market_areas_all(self):
        """Test excluded_market_areas when ['all']."""
        params = PortfolioOptimisationParameters(
            temporal=make_date(),
            excluded_market_areas=["all"],
        )

        assert params.excluded_market_areas == ["all"]

    def test_excluded_market_areas_all_mixed_case(self):
        """Test excluded_market_areas when ['All']."""
        params = PortfolioOptimisationParameters(
            temporal=make_date(),
            excluded_market_areas=["All"],
        )

        assert params.excluded_market_areas == ["all"]

    def test_excluded_market_areas_specific_list(self):
        """Test excluded_market_areas with specific area names."""
        params = PortfolioOptimisationParameters(
            temporal=make_date(),
            excluded_market_areas=["area1", "area2", "area3"],
        )

        assert params.excluded_market_areas == ["area1", "area2", "area3"]


class TestPortfolioOptimisationParametersExcludedTechnologies:
    """Test suite for excluded_technologies property."""

    def test_excluded_technologies_none(self):
        """Test excluded_technologies when None."""
        params = PortfolioOptimisationParameters(
            temporal=make_date(),
            excluded_technologies=None,
        )

        assert params.excluded_technologies == []

    def test_excluded_technologies_none_string(self):
        """Test excluded_technologies when ['none']."""
        params = PortfolioOptimisationParameters(
            temporal=make_date(),
            excluded_technologies=["none"],
        )

        assert params.excluded_technologies == []

    def test_excluded_technologies_all(self):
        """Test excluded_technologies when ['all']."""
        params = PortfolioOptimisationParameters(
            temporal=make_date(),
            excluded_technologies=["all"],
        )

        assert params.excluded_technologies == ["all"]

    def test_excluded_technologies_specific_list(self):
        """Test excluded_technologies with specific technology names."""
        params = PortfolioOptimisationParameters(
            temporal=make_date(),
            excluded_technologies=["wind", "solar", "hydro"],
        )

        assert params.excluded_technologies == ["wind", "solar", "hydro"]


class TestPortfolioOptimisationParametersExcludedThermalStrategies:
    """Test suite for excluded_thermal_strategies property."""

    def test_excluded_thermal_strategies_none(self):
        """Test excluded_thermal_strategies when None."""
        params = PortfolioOptimisationParameters(
            temporal=make_date(),
            excluded_thermal_strategies=None,
        )

        assert params.excluded_thermal_strategies == []

    def test_excluded_thermal_strategies_none_string(self):
        """Test excluded_thermal_strategies when ['none']."""
        params = PortfolioOptimisationParameters(
            temporal=make_date(),
            excluded_thermal_strategies=["none"],
        )

        assert params.excluded_thermal_strategies == []

    def test_excluded_thermal_strategies_all(self):
        """Test excluded_thermal_strategies when ['all']."""
        params = PortfolioOptimisationParameters(
            temporal=make_date(),
            excluded_thermal_strategies=["all"],
        )

        assert params.excluded_thermal_strategies == [
            ThermalStrategy.BASE,
            ThermalStrategy.INTERMEDIATE,
            ThermalStrategy.PEAK,
        ]

    def test_excluded_thermal_strategies_specific_list(self):
        """Test excluded_thermal_strategies with specific strategies."""
        params = PortfolioOptimisationParameters(
            temporal=make_date(),
            excluded_thermal_strategies=["Base", "Peak"],
        )

        assert params.excluded_thermal_strategies == [ThermalStrategy.BASE, ThermalStrategy.PEAK]


class TestPortfolioOptimisationParametersPortfolioTimeWindow:
    """Test suite for portfolio_time_window property."""

    def test_portfolio_time_window_one_hour_timestep(self):
        """Test portfolio_time_window with 1-hour timestep."""
        params = PortfolioOptimisationParameters(
            temporal=DateParameters(
                start_date=pendulum.datetime(2024, 1, 1, 0, 0),
                end_date=pendulum.datetime(2024, 1, 1, 3, 0),
                execution_date=pendulum.datetime(2024, 1, 1),
                timestep=duration(hours=1),
            )
        )

        expected = [
            pendulum.datetime(2024, 1, 1, 0, 0),
            pendulum.datetime(2024, 1, 1, 1, 0),
            pendulum.datetime(2024, 1, 1, 2, 0),
        ]
        assert params.portfolio_time_window == expected

    def test_portfolio_time_window_thirty_minute_timestep(self):
        """Test portfolio_time_window with 30-minute timestep."""
        params = PortfolioOptimisationParameters(
            temporal=DateParameters(
                start_date=pendulum.datetime(2024, 1, 1, 0, 0),
                end_date=pendulum.datetime(2024, 1, 1, 1, 0),
                execution_date=pendulum.datetime(2024, 1, 1),
                timestep=duration(minutes=30),
            )
        )

        expected = [
            pendulum.datetime(2024, 1, 1, 0, 0),
            pendulum.datetime(2024, 1, 1, 0, 30),
        ]
        assert params.portfolio_time_window == expected

    def test_portfolio_time_window_closed_left(self):
        """Test that portfolio_time_window excludes end_date (closed='left')."""
        params = PortfolioOptimisationParameters(
            temporal=DateParameters(
                start_date=pendulum.datetime(2024, 1, 1, 0, 0),
                end_date=pendulum.datetime(2024, 1, 1, 2, 0),
                execution_date=pendulum.datetime(2024, 1, 1),
                timestep=duration(hours=1),
            )
        )

        # Should NOT include the end_date
        assert pendulum.datetime(2024, 1, 1, 2, 0) not in params.portfolio_time_window
        assert len(params.portfolio_time_window) == 2


class TestPortfolioOptimisationParametersEquipmentTimeWindow:
    """Test suite for equipment_time_window method."""

    def test_equipment_time_window_extends_portfolio_time_window_by_additional_hours(self):
        """Test that the window extends beyond portfolio_time_window by the equipment's additional_hours."""
        params = PortfolioOptimisationParameters(
            temporal=DateParameters(
                start_date=pendulum.datetime(2024, 1, 1, 0, 0),
                end_date=pendulum.datetime(2024, 1, 1, 3, 0),
                execution_date=pendulum.datetime(2024, 1, 1),
                timestep=duration(hours=1),
            )
        )
        equipment = Mock(additional_hours=duration(hours=2))

        window = params.equipment_time_window(equipment)

        expected = [
            pendulum.datetime(2024, 1, 1, 0, 0),
            pendulum.datetime(2024, 1, 1, 1, 0),
            pendulum.datetime(2024, 1, 1, 2, 0),
            pendulum.datetime(2024, 1, 1, 3, 0),
            pendulum.datetime(2024, 1, 1, 4, 0),
        ]
        assert window == expected

    def test_equipment_time_window_zero_additional_hours_matches_portfolio_time_window(self):
        """Test that a zero lookahead reproduces portfolio_time_window exactly."""
        params = PortfolioOptimisationParameters(
            temporal=DateParameters(
                start_date=pendulum.datetime(2024, 1, 1, 0, 0),
                end_date=pendulum.datetime(2024, 1, 1, 2, 0),
                execution_date=pendulum.datetime(2024, 1, 1),
                timestep=duration(hours=1),
            )
        )
        equipment = Mock(additional_hours=duration(hours=0))

        assert params.equipment_time_window(equipment) == params.portfolio_time_window

    def test_equipment_time_window_is_cached_per_equipment(self):
        """Test that repeated calls for the same equipment reuse the cached result."""
        params = PortfolioOptimisationParameters(temporal=make_date())
        equipment = Mock(additional_hours=duration(hours=0))

        first = params.equipment_time_window(equipment)
        second = params.equipment_time_window(equipment)

        assert first is second


class TestPortfolioOptimisationParametersInitBatteryTime:
    """Test suite for init_battery_time property."""

    def test_init_battery_time_one_hour_timestep(self):
        """Test init_battery_time with 1-hour timestep."""
        params = PortfolioOptimisationParameters(
            temporal=DateParameters(
                start_date=pendulum.datetime(2024, 1, 1, 10, 0),
                end_date=pendulum.datetime(2024, 1, 1, 12, 0),
                execution_date=pendulum.datetime(2024, 1, 1),
                timestep=duration(hours=1),
            )
        )

        assert params.init_battery_time == pendulum.datetime(2024, 1, 1, 9, 0)

    def test_init_battery_time_thirty_minute_timestep(self):
        """Test init_battery_time with 30-minute timestep."""
        params = PortfolioOptimisationParameters(
            temporal=DateParameters(
                start_date=pendulum.datetime(2024, 1, 1, 10, 0),
                end_date=pendulum.datetime(2024, 1, 1, 12, 0),
                execution_date=pendulum.datetime(2024, 1, 1),
                timestep=duration(minutes=30),
            )
        )

        assert params.init_battery_time == pendulum.datetime(2024, 1, 1, 9, 30)

    def test_init_battery_time_fifteen_minute_timestep(self):
        """Test init_battery_time with 15-minute timestep."""
        params = PortfolioOptimisationParameters(
            temporal=DateParameters(
                start_date=pendulum.datetime(2024, 1, 1, 10, 0),
                end_date=pendulum.datetime(2024, 1, 1, 12, 0),
                execution_date=pendulum.datetime(2024, 1, 1),
                timestep=duration(minutes=15),
            )
        )

        assert params.init_battery_time == pendulum.datetime(2024, 1, 1, 9, 45)


class TestPortfolioOptimisationParametersStorageMapping:
    """Test suite for storage_mapping property."""

    def test_storage_mapping_default_values(self):
        """Test storage_mapping with default parameter values."""
        params = PortfolioOptimisationParameters(
            temporal=DateParameters(
                start_date=pendulum.datetime(2024, 1, 1),
                end_date=pendulum.datetime(2024, 1, 2),
                execution_date=pendulum.datetime(2024, 1, 1),
            )
        )

        storage_mapping = params.storage_mapping

        # Test battery mapping
        assert StorageType.BATTERY in storage_mapping
        assert storage_mapping[StorageType.BATTERY]["nb_fragment"] == 3
        assert storage_mapping[StorageType.BATTERY]["smoothing_factor"] == 0.2

        # Test pumped hydraulic mapping
        assert StorageType.PUMPED_HYDRAULIC_STORAGE in storage_mapping
        assert storage_mapping[StorageType.PUMPED_HYDRAULIC_STORAGE]["nb_fragment"] == 3
        assert storage_mapping[StorageType.PUMPED_HYDRAULIC_STORAGE]["smoothing_factor"] == 0.2

        # Test electric vehicle mapping
        assert StorageType.ELECTRIC_VEHICLE in storage_mapping
        assert storage_mapping[StorageType.ELECTRIC_VEHICLE]["nb_fragment"] == 3
        assert storage_mapping[StorageType.ELECTRIC_VEHICLE]["smoothing_factor"] == 0.2

    def test_storage_mapping_custom_values(self):
        """Test storage_mapping with custom parameter values."""
        params = PortfolioOptimisationParameters(
            temporal=DateParameters(
                start_date=pendulum.datetime(2024, 1, 1),
                end_date=pendulum.datetime(2024, 1, 2),
                execution_date=pendulum.datetime(2024, 1, 1),
            ),
            battery_nb_fragments=5,
            battery_smoothing_factor=0.3,
            pumped_hydraulic_nb_fragments=4,
            pumped_hydraulic_smoothing_factor=0.25,
            electric_vehicle_nb_fragments=6,
            electric_vehicle_smoothing_factor=0.15,
        )

        storage_mapping = params.storage_mapping

        # Test battery mapping
        assert storage_mapping[StorageType.BATTERY]["nb_fragment"] == 5
        assert storage_mapping[StorageType.BATTERY]["smoothing_factor"] == 0.3

        # Test pumped hydraulic mapping
        assert storage_mapping[StorageType.PUMPED_HYDRAULIC_STORAGE]["nb_fragment"] == 4
        assert storage_mapping[StorageType.PUMPED_HYDRAULIC_STORAGE]["smoothing_factor"] == 0.25

        # Test electric vehicle mapping
        assert storage_mapping[StorageType.ELECTRIC_VEHICLE]["nb_fragment"] == 6
        assert storage_mapping[StorageType.ELECTRIC_VEHICLE]["smoothing_factor"] == 0.15

    def test_storage_mapping_has_all_storage_types(self):
        """Test that storage_mapping contains all expected storage types."""
        params = PortfolioOptimisationParameters(
            temporal=DateParameters(
                start_date=pendulum.datetime(2024, 1, 1),
                end_date=pendulum.datetime(2024, 1, 2),
                execution_date=pendulum.datetime(2024, 1, 1),
            )
        )

        storage_mapping = params.storage_mapping

        assert len(storage_mapping) == 3
        assert StorageType.BATTERY in storage_mapping
        assert StorageType.PUMPED_HYDRAULIC_STORAGE in storage_mapping
        assert StorageType.ELECTRIC_VEHICLE in storage_mapping
