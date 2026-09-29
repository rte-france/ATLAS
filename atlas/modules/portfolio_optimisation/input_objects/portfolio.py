"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import cast

from pendulum import DateTime

from atlas.enums import MarketType
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.modules.portfolio_optimisation.input_objects import EquipmentPO
from atlas.modules.portfolio_optimisation.input_objects.hydro import HydroPO
from atlas.modules.portfolio_optimisation.input_objects.load import LoadPO
from atlas.modules.portfolio_optimisation.input_objects.market_area import MarketAreaPO
from atlas.modules.portfolio_optimisation.input_objects.other_non_dispatchable import OtherNonDispatchablePO
from atlas.modules.portfolio_optimisation.input_objects.portfolio_equipments import PortfolioEquipments
from atlas.modules.portfolio_optimisation.input_objects.solar import SolarPO
from atlas.modules.portfolio_optimisation.input_objects.storage import StoragePO
from atlas.modules.portfolio_optimisation.input_objects.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.input_objects.wind import WindPO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.objects.market_operator.portfolio import Portfolio
from atlas.objects.network_operator.control_block import ControlBlock

#: Reserve products an equipment may have procured, read from its ``{reserve}_procured`` forecast.
RESERVE_TYPES = ["rr_up", "rr_down", "mfrr_up", "mfrr_down", "afrr_up", "afrr_down", "fcr_up", "fcr_down"]


class PortfolioPO(Portfolio):
    """
    Portfolio input of the portfolio optimisation.

    Its inputs to the optimisation (upstream and residual energy, maximum power, contracted
    reserves, prices) are computed over the whole portfolio time window at once: each forecast
    is read once per equipment rather than once per timestep.
    """

    market_area: MarketAreaPO
    control_block: ControlBlock
    equipments: PortfolioEquipments

    def price_forecasts(
        self, times: list[DateTime], parameters: PortfolioOptimisationParameters
    ) -> dict[DateTime, float]:
        """
        Get the price forecast at each of *times*, based on market type and forecast settings.

        Times outside the portfolio time window always read ``price_forecast_medium``; inside it, the
        price source depends on the market and on ``use_forecast``. A missing source reads 0.0.

        **Example**

            portfolio.price_forecasts(parameters.portfolio_time_window, parameters)[time]

        :param times: Times to get a price for
        :type times: list[DateTime]
        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :return: Price forecast at each time
        :rtype: dict[DateTime, float]
        """
        execution_date = parameters.temporal.execution_date
        window = set(parameters.portfolio_time_window)
        inside = sorted(time for time in times if time in window)
        outside = sorted(time for time in times if time not in window)
        prices: dict[DateTime, float] = {}

        if outside:
            medium = self.market_area.price_forecast_medium.get_forecast(execution_date, outside[0], outside[-1])
            prices |= zip(outside, medium.get_values(outside), strict=True)

        if inside:
            source = self._window_price_source(parameters, inside[0], inside[-1])
            values = source.reindex(inside, inplace=False).values if source is not None else [0.0] * len(inside)
            prices |= zip(inside, values, strict=True)

        return prices

    def _window_price_source(
        self, parameters: PortfolioOptimisationParameters, start: DateTime, end: DateTime
    ) -> AbstractTimeseries | None:
        """Return the prices read inside the portfolio time window, or None if the market has no source."""
        execution_date = parameters.temporal.execution_date
        market_area = self.market_area

        if parameters.use_forecast:
            forecast = {
                MarketType.dayahead: market_area.price_forecast_medium,
                MarketType.intraday: market_area.id_price_forecast,
            }.get(parameters.market)
            return forecast.get_forecast(execution_date, start, end) if forecast is not None else None

        if parameters.market == MarketType.intraday:
            return cast(ForecastingMatrix | LazyForecastingMatrix, market_area.id_price).get_forecast(
                execution_date, start, end
            )

        return {
            MarketType.dayahead: market_area.da_price,
            MarketType.rr_activation: market_area.rr_activation_price,
            MarketType.mfrr_activation: market_area.mfrr_activation_price,
        }.get(parameters.market)

    def residual_energy(self, parameters: PortfolioOptimisationParameters) -> Timeseries:
        """
        Compute the residual energy over the portfolio time window.

        Non-dispatchable loads and other equipments count the part of their upstream energy their
        forecast cannot cover; every other equipment counts its whole upstream energy.

        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :return: Residual energy at each time of the window
        :rtype: Timeseries
        """
        residual_energy = self._zeros(parameters)

        forecast_based_equipment: list[LoadPO | OtherNonDispatchablePO] = [
            *self.equipments.non_dispatchable_load,
            *self.equipments.other_non_dispatchable,
        ]
        for equipment in forecast_based_equipment:
            upstream_energy = self.upstream_energy(equipment, parameters)
            forecast = self._forecast_on_window(equipment.maximum_power_forecast, parameters)
            residual_energy = residual_energy + (upstream_energy - forecast).clip(lower_bound=0)

        other_equipment: list[EquipmentPO] = [
            *self.equipments.thermal,
            *self.equipments.storage,
            *self.equipments.hydro,
            *self.equipments.wind,
            *self.equipments.solar,
            *self.equipments.dispatchable_load,
        ]
        for other in other_equipment:
            residual_energy = residual_energy + self.upstream_energy(other, parameters)

        return residual_energy

    def maximum_power(self, parameters: PortfolioOptimisationParameters) -> Timeseries:
        """
        Compute the maximum power of the dispatchable equipments over the portfolio time window.

        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :return: Sum of the absolute maximum power of each dispatchable equipment
        :rtype: Timeseries
        """
        return sum(
            (
                self._equipment_maximum_power(obj, parameters).abs(inplace=False)
                for _, equipment_list in self.equipments.get_dispatchable_equipment_types()
                for obj in equipment_list
            ),
            start=self._zeros(parameters),
        )

    def contracted_reserves(
        self, parameters: PortfolioOptimisationParameters
    ) -> tuple[Timeseries, Timeseries, Timeseries, Timeseries]:
        """
        Compute the reserves procured by the dispatchable equipments over the portfolio time window.

        Automated reserves are capped by each equipment's aFRR and FCR capacities.

        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :return: Tuple of (reserves_up, reserves_down, automated_reserves_up, automated_reserves_down)
        :rtype: tuple[Timeseries, Timeseries, Timeseries, Timeseries]
        """
        totals = [self._zeros(parameters)] * 4

        for _, equipment_list in self.equipments.get_dispatchable_equipment_types():
            for obj in equipment_list:
                procured = {
                    reserve: self._forecast_on_window(forecast, parameters)
                    for reserve in RESERVE_TYPES
                    if (forecast := getattr(obj, f"{reserve}_procured"))
                }
                capacity = {"afrr": obj.maximum_afrr or 0, "fcr": obj.maximum_fcr or 0}
                contributions = [
                    [procured[reserve] for reserve in ("rr_up", "mfrr_up") if reserve in procured],
                    [procured[reserve] for reserve in ("rr_down", "mfrr_down") if reserve in procured],
                    [
                        procured[f"{reserve}_up"].clip(upper_bound=capacity[reserve])
                        for reserve in ("afrr", "fcr")
                        if f"{reserve}_up" in procured
                    ],
                    [
                        procured[f"{reserve}_down"].clip(upper_bound=capacity[reserve])
                        for reserve in ("afrr", "fcr")
                        if f"{reserve}_down" in procured
                    ],
                ]
                # absent reserves count as zero, so only the procured ones are added
                totals = [
                    total + sum(parts[1:], start=parts[0]) if parts else total
                    for total, parts in zip(totals, contributions, strict=True)
                ]

        reserves_up, reserves_down, automated_up, automated_down = totals
        return reserves_up, reserves_down, automated_up, automated_down

    @classmethod
    def upstream_energy(cls, obj: EquipmentPO, parameters: PortfolioOptimisationParameters) -> Timeseries:
        """
        Get the upstream energy (bought or sold) of an equipment over the portfolio time window.

        It is the activated reserve on the activation markets, the day-ahead cleared quantity in
        day-ahead, and the day-ahead plus the cumulated intraday cleared quantities in intraday.

        :param obj: Equipment object
        :type obj: EquipmentPO
        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :return: Upstream energy at each time of the window, 0.0 where not cleared
        :rtype: Timeseries
        """
        attributes = {
            MarketType.rr_activation: ["rr_activated"],
            MarketType.mfrr_activation: ["mfrr_activated"],
            MarketType.dayahead: ["da_cleared_quantity"],
        }.get(parameters.market, ["total_id_cleared_quantity", "da_cleared_quantity"])

        cleared = [
            cls._on_window(values, parameters)
            for attribute in attributes
            if (values := getattr(obj, attribute)) is not None
        ]
        return sum(cleared[1:], start=cleared[0]) if cleared else cls._zeros(parameters)

    @classmethod
    def _equipment_maximum_power(cls, obj: EquipmentPO, parameters: PortfolioOptimisationParameters) -> Timeseries:
        """Return the maximum power of an equipment over the portfolio time window."""
        if isinstance(obj, HydroPO | StoragePO | ThermalPO):
            return cls._on_window(obj.maximum_power, parameters)
        if isinstance(obj, LoadPO | WindPO | SolarPO | OtherNonDispatchablePO):
            return cls._forecast_on_window(obj.maximum_power_forecast, parameters)
        raise RuntimeError("Unrecognized Equipment type")

    @classmethod
    def _forecast_on_window(
        cls, forecast: ForecastingMatrix | LazyForecastingMatrix, parameters: PortfolioOptimisationParameters
    ) -> Timeseries:
        """Read *forecast* at the execution date over the portfolio time window, 0.0 where it has no value."""
        window = parameters.portfolio_time_window
        return cls._on_window(
            forecast.get_forecast(parameters.temporal.execution_date, min(window), max(window)), parameters
        )

    @staticmethod
    def _on_window(values: AbstractTimeseries, parameters: PortfolioOptimisationParameters) -> Timeseries:
        """Align *values* on the portfolio time window, 0.0 where it has no value."""
        aligned = values.reindex(parameters.portfolio_time_window, inplace=False)
        return aligned.collect() if isinstance(aligned, LazyTimeseries) else cast(Timeseries, aligned)

    @staticmethod
    def _zeros(parameters: PortfolioOptimisationParameters) -> Timeseries:
        """Return a zero-valued timeseries spanning the portfolio time window."""
        window = parameters.portfolio_time_window
        return Timeseries.from_index(min(window), parameters.temporal.timestep, max(window), default_value=0.0)
