"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.st_storage import STStorage
from loguru import logger
from pendulum import duration

from atlas.core.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def get_power_bounds(
    storage: STStorage,
    scenario: int | None,
    parameters: AntaresToAtlasParameters,
) -> tuple[Timeseries, Timeseries]:
    """Return (maximum_injection_power_ts, maximum_withdrawal_power_ts).

    Uses scenario-specific pmax timeseries scaled by nominal capacity when available,
    falls back to constant nominal capacities.
    """
    props = storage.properties

    if scenario is not None:
        try:
            inj_col = storage.get_pmax_injection()[scenario - 1]
            wdr_col = storage.get_pmax_withdrawal()[scenario - 1]
            return (
                Timeseries.from_values(
                    start_date=parameters.start_date,
                    frequency="1h",
                    values=(inj_col * props.injection_nominal_capacity),
                ),
                Timeseries.from_values(
                    start_date=parameters.start_date,
                    frequency="1h",
                    values=(wdr_col * props.withdrawal_nominal_capacity),
                ),
            )
        except Exception as e:
            logger.warning(f"Could not get pmax timeseries for {storage.id}: {e}, falling back to nominal capacity")

    end_date = parameters.start_date + duration(years=1)
    days_in_year = (end_date - parameters.start_date).days
    return (
        Timeseries.from_index(
            start_date=parameters.start_date,
            frequency=f"{days_in_year}d",
            end_date=end_date,
            default_value=props.injection_nominal_capacity,
        ),
        Timeseries.from_index(
            start_date=parameters.start_date,
            frequency=f"{days_in_year}d",
            end_date=end_date,
            default_value=props.withdrawal_nominal_capacity,
        ),
    )


def get_minimum_soc(
    storage: STStorage,
    scenario: int | None,
    parameters: AntaresToAtlasParameters,
) -> Timeseries:
    """Return minimum state of charge timeseries from the lower rule curve.

    Falls back to a constant zero timeseries if the scenario is unavailable or
    the matrix cannot be read.
    """
    if scenario is not None:
        try:
            lower_curve_col = storage.get_lower_rule_curve()[scenario - 1]
            return Timeseries.from_values(
                start_date=parameters.start_date,
                frequency="1h",
                values=lower_curve_col,
            )
        except Exception as e:
            logger.warning(f"Could not get lower rule curve for {storage.id}: {e}, defaulting to 0")

    end_date = parameters.start_date + duration(years=1)
    days_in_year = (end_date - parameters.start_date).days
    return Timeseries.from_index(
        start_date=parameters.start_date,
        frequency=f"{days_in_year}d",
        end_date=end_date,
        default_value=0.0,
    )
