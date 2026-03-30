from functools import cached_property

import pendulum
from pendulum import DateTime, duration
from pendulum.duration import Duration
from pydantic import Field, field_validator

from atlas.abstract_class.abstract_parameters import AbstractParameters
from atlas.io_utils.section_parameters import DateParameters


class PriceForecastParameters(AbstractParameters):
    temporal: DateParameters

    intraday_negative_price_cap: int = Field(
        -500,
        description="Lower price cap of the Intraday market, -500 €/MWh in 2024.",
        le=0,
    )
    intraday_positive_price_cap: int = Field(
        4000,
        description="Upper price cap of the Intraday market, 4000 €/MWh in 2024.",
        ge=0,
    )
    execution_date_day_ahead: DateTime = Field(
        default_factory=lambda: pendulum.datetime(year=2028, month=9, day=26, hour=12),
        description="Reference date from DayAhead market.",
    )
    execution_date_scenarios: DateTime = Field(
        default_factory=lambda: pendulum.datetime(year=2028, month=7, day=1),
        description="Reference date for the scenarios from price forecast matrix.",
    )

    @cached_property
    def penultimate_date(self) -> DateTime:
        return self.temporal.end_date - self.temporal.timestep
