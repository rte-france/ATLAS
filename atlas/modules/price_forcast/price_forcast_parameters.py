from functools import cached_property

from pendulum import DateTime, duration
from pendulum.duration import Duration
from pydantic import Field, field_validator

from atlas.abstract_class.abstract_parameters import AbstractParameters
from atlas.timing import build_datetime
from atlas.validators import convert_to_duration

import pendulum
from pendulum import duration
from pendulum import Timezone

class PriceForcastParameters(AbstractParameters):
    debug: bool = Field(
        False,
        description="A boolean indicating if the script will run in debug mode.",
    )
    verbose: bool = Field(
        True,
        description="A boolean indicating whether or not the program shall return detailed logs.",
    )
    intraday_negative_price_cap: int = Field(
        -500,
        description="Lower price cap of the Intraday market, -500 €/MWh in 2024.",
    )
    intraday_positive_price_cap: int = Field(
        4000,
        description="Upper price cap of the Intraday market, 4000 €/MWh in 2024.",
    )
    time_step: Duration = Field(
        default_factory=lambda: duration(minutes=60),
        description="Time step (in minutes) of the simulated market.",
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
        return self.end_date - self.time_step

    @field_validator(
        "execution_date_day_ahead",
        "execution_date_scenarios",
        mode="before",
    )
    @classmethod
    def convert_to_datetime(cls, v):
        """Convert various datetime formats to DateTime objects."""
        return build_datetime(v)

    @field_validator(
        "time_step",
        mode="before",
    )
    @classmethod
    def convert_to_duration(cls, v):
        """Convert various duration formats to Duration objects."""
        return convert_to_duration(v)
