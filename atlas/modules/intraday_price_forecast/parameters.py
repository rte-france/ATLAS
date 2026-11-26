from functools import cached_property

from pydantic import Field
from pydantic_extra_types.pendulum_dt import DateTime

from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.validators import DurationField


class IntradayPriceForecastParameters(AbstractModuleParameters):
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
    day_ahead_execution_offset: DurationField = Field(
        description="Duration before the start of the delivery day at which the Day-Ahead market is executed "
        "(e.g. '12h' -> D-1 12:00).",
    )
    execution_date_scenarios: DateTime = Field(
        description="Reference date for the scenarios from price forecast matrix.",
    )

    @cached_property
    def penultimate_date(self) -> DateTime:
        return self.temporal.end_date - self.temporal.timestep

    @cached_property
    def execution_date_day_ahead(self) -> DateTime:
        return self.temporal.start_date.start_of("day") - self.day_ahead_execution_offset
