"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from datetime import datetime
from typing import cast

from pendulum import DateTime

from atlas.enums import MarketType
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.modules.portfolio_optimisation.input_objects import EquipmentPO
from atlas.modules.portfolio_optimisation.input_objects.hydro import HydroPO
from atlas.modules.portfolio_optimisation.input_objects.load import LoadPO
from atlas.modules.portfolio_optimisation.input_objects.market_area import MarketAreaPO
from atlas.modules.portfolio_optimisation.input_objects.other_non_dispatchable import OtherNonDispatchablePO
from atlas.modules.portfolio_optimisation.input_objects.portfolio_equipments import PortfolioEquipments
from atlas.modules.portfolio_optimisation.input_objects.solar import SolarPO
from atlas.modules.portfolio_optimisation.input_objects.storage import StoragePO
from atlas.modules.portfolio_optimisation.input_objects.thermal.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.input_objects.wind import WindPO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.objects.market_operator.portfolio import Portfolio
from atlas.objects.network_operator.control_block import ControlBlock


class PortfolioPO(Portfolio):
    market_area: MarketAreaPO
    control_block: ControlBlock
    equipments: PortfolioEquipments

    def get_price_forecast(self, time: DateTime, parameters: PortfolioOptimisationParameters) -> float | None:
        """
        Get price forecast for given time based on market type and forecast settings.

        :param time: Current time period
        :type time: DateTime
        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :return: Price forecast value or None if not available
        :rtype: float | None
        """
        execution_date = parameters.temporal.execution_date
        market = parameters.market

        if time not in parameters.target_times:
            return self.market_area.price_forecast_medium.get_forecast(execution_date, time, time).get_value(time)

        if parameters.use_forecast:
            forecast_by_market = {
                MarketType.dayahead: self.market_area.price_forecast_medium,
                MarketType.intraday: self.market_area.id_price_forecast,
            }

            forecast = forecast_by_market.get(market)
            if forecast is None:
                return None

            return (
                cast(ForecastingMatrix | LazyForecastingMatrix, forecast)
                .get_forecast(execution_date, time, time, default_value=0)
                .get_value(time)
            )

        if market == MarketType.dayahead:
            return cast(AbstractTimeseries, self.market_area.da_price).get_value(time)

        if market == MarketType.intraday:
            return (
                cast(ForecastingMatrix | LazyForecastingMatrix, self.market_area.id_price)
                .get_forecast(execution_date, time, time, default_value=0)
                .get_value(time)
            )

        if market == MarketType.rr_activation:
            return cast(AbstractTimeseries, self.market_area.rr_activation_price).get_value(time)

        if market == MarketType.mfrr_activation:
            return cast(AbstractTimeseries, self.market_area.mfrr_activation_price).get_value(time)

        return None

    def _compute_residual_energy(self, time: DateTime, parameters: PortfolioOptimisationParameters) -> float:
        """
        Compute residual energy metrics for all times.

        :param time: Current time period
        :type time: DateTime
        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :return: Residual energy value
        :rtype: float
        """
        residual_energy = 0.0

        forecast_based_equipment: list[LoadPO | OtherNonDispatchablePO] = [
            *self.equipments.non_dispatchable_load,
            *self.equipments.other_non_dispatchable,
        ]

        for equipment in forecast_based_equipment:
            upstream_energy = self._get_upstream_energy(equipment, time, parameters)
            forecast_t = equipment.maximum_power_forecast.get_forecast(
                parameters.temporal.execution_date, time, time, default_value=0
            ).get_value(time)

            residual_energy += upstream_energy - min(forecast_t, upstream_energy)

        other_equipment = [
            *self.equipments.thermal,
            *self.equipments.storage,
            *self.equipments.hydro,
            *self.equipments.wind,
            *self.equipments.solar,
            *self.equipments.dispatchable_load,
        ]

        for equipment in other_equipment:  # type: ignore [assignment]
            residual_energy += self._get_upstream_energy(equipment, time, parameters)  # type:ignore [arg-type]

        return residual_energy

    def _compute_maximum_power(self, time: DateTime, parameters: PortfolioOptimisationParameters) -> float:
        """
        Compute maximum power and energy metrics for all times.

        :param time: Current time period
        :type time: DateTime
        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :return: Maximum power value
        :rtype: float
        """
        return sum(
            abs(self._get_maximum_power(obj, time, parameters.temporal.execution_date))
            for _, equipment_list in self.equipments.get_dispatchable_equipment_types()
            for obj in equipment_list
        )

    def _compute_reserves_time(
        self, time: DateTime, parameters: PortfolioOptimisationParameters
    ) -> tuple[float, float, float, float]:
        """
        Compute reserves and power metrics for a specific time.

        :param time: Current time period
        :type time: DateTime
        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :return: Tuple of (reserves_up, reserves_down, automated_reserves_up, automated_reserves_down)
        :rtype: tuple[float, float, float, float]
        """
        all_reserves = [
            self._get_reserve(obj, time, parameters)
            for _, equipment_list in self.equipments.get_dispatchable_equipment_types()
            for obj in equipment_list
        ]

        return tuple(sum(values) for values in zip(*all_reserves)) if all_reserves else (0.0, 0.0, 0.0, 0.0)  # noqa: B905

    @staticmethod
    def _get_upstream_energy(
        obj: EquipmentPO,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
    ) -> float:
        """
        Get upstream energy (bought or sold) based on market type.

        :param obj: Equipment object
        :type obj: EquipmentPO
        :param time: Current time period
        :type time: DateTime
        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :return: Upstream energy value
        :rtype: float
        """
        if parameters.market == MarketType.rr_activation:
            return obj.rr_activated.get_value(time) if obj.rr_activated is not None else 0
        elif parameters.market == MarketType.mfrr_activation:
            return obj.mfrr_activated.get_value(time) if obj.mfrr_activated is not None else 0
        elif parameters.market == MarketType.dayahead:
            return obj.da_cleared_quantity.get_value(time) if obj.da_cleared_quantity is not None else 0
        else:
            total_id = obj.total_id_cleared_quantity.get_value(time) if obj.total_id_cleared_quantity is not None else 0
            da_cleared = obj.da_cleared_quantity.get_value(time) if obj.da_cleared_quantity is not None else 0
            return total_id + da_cleared

    @staticmethod
    def _get_maximum_power(
        obj: EquipmentPO, time: DateTime, execution_date: datetime | DateTime | str | None = None
    ) -> float:
        if isinstance(obj, HydroPO | StoragePO | ThermalPO):
            return obj.maximum_power.get_value(time)
        elif isinstance(obj, LoadPO | WindPO | SolarPO | OtherNonDispatchablePO):
            if execution_date:
                return obj.maximum_power_forecast.get_forecast(execution_date, time, time, default_value=0).get_value(
                    time
                )
            else:
                raise RuntimeError(
                    "Missing execution date argument for a Load, Wind, Solar or OtherNonDispatchable equipment"
                )
        else:
            raise RuntimeError("Unrecognized Equipment type")

    def _get_reserve(
        self,
        obj: EquipmentPO,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
    ) -> tuple[float, float, float, float]:
        """
        Calculate reserve values for equipment object.

        :param obj: Equipment object
        :type obj: EquipmentPO
        :param time: Current time period
        :type time: DateTime
        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :return: Tuple of (reserves_up, reserves_down, automated_reserves_up, automated_reserves_down)
        :rtype: tuple[float, float, float, float]
        """
        maximum_afrr = obj.maximum_afrr
        maximum_fcr = obj.maximum_fcr

        afrr_up = self.get_reserve_value(obj, time, "afrr_up", parameters)
        afrr_down = self.get_reserve_value(obj, time, "afrr_down", parameters)
        mfrr_up = self.get_reserve_value(obj, time, "mfrr_up", parameters)
        mfrr_down = self.get_reserve_value(obj, time, "mfrr_down", parameters)
        rr_up = self.get_reserve_value(obj, time, "rr_up", parameters)
        rr_down = self.get_reserve_value(obj, time, "rr_down", parameters)
        fcr_up = self.get_reserve_value(obj, time, "fcr_up", parameters)
        fcr_down = self.get_reserve_value(obj, time, "fcr_down", parameters)

        reserves_up = rr_up + mfrr_up
        reserves_down = rr_down + mfrr_down
        automated_reserves_up = min(afrr_up, maximum_afrr or 0) + min(fcr_up, maximum_fcr or 0)
        automated_reserves_down = min(afrr_down, maximum_afrr or 0) + min(fcr_down, maximum_fcr or 0)

        return (
            reserves_up,
            reserves_down,
            automated_reserves_up,
            automated_reserves_down,
        )

    @staticmethod
    def get_reserve_value(
        obj: EquipmentPO, time: DateTime, reserve_type: str, parameters: PortfolioOptimisationParameters
    ) -> float:
        """
        Helper to get reserve value from forecast.

        :param obj: Equipment object
        :type obj: EquipmentPO
        :param time: Current time period
        :type time: DateTime
        :param reserve_type: Type of reserve (e.g., 'afrr_up', 'mfrr_down')
        :type reserve_type: str
        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :return: Reserve value
        :rtype: float
        """
        reserve_attr = getattr(obj, f"{reserve_type}_procured")
        if reserve_attr:
            return (
                cast(ForecastingMatrix | LazyForecastingMatrix, reserve_attr)
                .get_forecast(parameters.temporal.execution_date, time, time)
                .get_value(time)
            )
        else:
            return 0
