
from atlas.timing import build_datetime
from atlas.validators import convert_to_duration
from pendulum import DateTime, duration
from pendulum.duration import Duration
from pydantic import Field, field_validator

from atlas.abstract_class.abstract_parameters import AbstractParameters


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
        "2028/09/01 12:00:00",
        description="Reference date from DayAhead market.",
    )
    execution_date_scenarios: DateTime = Field(
        "2028/07/01 00:00:00",
        description="Reference date for the scenarios from price forecast matrix.",
    )

    # FIXME Should we create a validator in validator.py that convert various type of DateTime,
    #       as we do with Duration using function convert_to_duration?
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
