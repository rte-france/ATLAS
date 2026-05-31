"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from atlas.math.timeseries import Timeseries

if TYPE_CHECKING:
    from pendulum import DateTime, Duration

    from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
    from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO


@dataclass
class ReserveProcurement:
    """Aggregated procured reserve forecasts, grouped by reserve class and direction."""

    automated_up: Timeseries
    automated_down: Timeseries
    manual_up: Timeseries
    manual_down: Timeseries


def load_forecast_or_zero(
    matrix: ForecastingMatrix | LazyForecastingMatrix | None,
    execution_date: DateTime,
    start_date: DateTime,
    end_date: DateTime,
    timestep: Duration,
) -> Timeseries:
    """
    Load a forecast timeseries, or return a zero-valued series if the matrix is missing.

    :param matrix: Source forecasting matrix (or ``None`` if the unit has no procurement for this product).
    :param execution_date: Forecast execution date.
    :param start_date: Inclusive start of the returned series.
    :param end_date: Inclusive end of the returned series.
    :param timestep: Sampling step used when building the zero series fallback.
    """
    if matrix:
        return matrix.get_forecast(execution_date, start_date, end_date)
    return Timeseries.from_index(start_date, timestep, end_date, 0)


def load_reserve_procurement(
    unit: ThermalDAO,
    execution_date: DateTime,
    start_date: DateTime,
    end_date: DateTime,
    timestep: Duration,
) -> ReserveProcurement:
    """
    Load all procured reserve forecasts (afrr+fcr aggregated as automated, mfrr+rr as manual)
    for a thermal unit. Missing matrices fall back to zero series.
    """

    def _fcst(matrix) -> Timeseries:
        return load_forecast_or_zero(matrix, execution_date, start_date, end_date, timestep)

    return ReserveProcurement(
        automated_up=_fcst(unit.afrr_up_procured) + _fcst(unit.fcr_up_procured),
        automated_down=_fcst(unit.afrr_down_procured) + _fcst(unit.fcr_down_procured),
        manual_up=_fcst(unit.mfrr_up_procured) + _fcst(unit.rr_up_procured),
        manual_down=_fcst(unit.mfrr_down_procured) + _fcst(unit.rr_down_procured),
    )


def load_paired_forecasts_or_zero(
    matrix_a: ForecastingMatrix | LazyForecastingMatrix | None,
    matrix_b: ForecastingMatrix | LazyForecastingMatrix | None,
    execution_date: DateTime,
    start_date: DateTime,
    end_date: DateTime,
    timestep: Duration,
) -> Timeseries:
    """
    Sum two paired forecasts (e.g. ``afrr + fcr``). All-or-nothing: if either matrix is missing,
    return a zero series.

    Used by the peak strategy where the two procurement products are treated as a single
    aggregate and only meaningful when both are present.
    """
    if matrix_a and matrix_b:
        return matrix_a.get_forecast(execution_date, start_date, end_date) + matrix_b.get_forecast(
            execution_date, start_date, end_date
        )
    return Timeseries.from_index(start_date, timestep, end_date, 0)
