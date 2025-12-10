from datetime import datetime

from pydantic import Field, model_validator
from pydantic_extra_types.pendulum_dt import DateTime

from atlas.utils.api.abc_prototype_parameters import ABCPrototypeParameters


class CleanRoundingParameters(ABCPrototypeParameters):
    """
    :param start_date: Start date of the rounding time frame, default value is 2028/09/26 00:00:00
    :type start_date: datetime
    :param end_date: End date of the rounding time frame, default value is 2028/09/26 00:00:00
    :type end_date: datetime
    :param time_step: Time step of the timeseries in the input marker, in minutes, default value is 60
    :type time_step: int
    :param rounding_precision: Number of decimals allowed during rounding processes. NB: certain values are by default rounded to the nearest integer, default value is 2
    :type rounding_precision: int
    :param epsilon: Precision parameters, below which two values are considered equal when performing verifications, default value is 0.001
    :type epsilon: float
    """

    start_date: DateTime = Field(default=datetime(2028, 9, 26), description="Start date of the rounding time frame.")
    end_date: DateTime = Field(default=datetime(2028, 9, 26), description="End date of the rounding time frame.")
    time_step: int = Field(default=60, description="Time step of the timeseries in the input marker, in minutes.")
    rounding_precision: int = Field(
        default=2,
        description="Number of decimals allowed during rounding processes. NB: certain values are by default rounded to the nearest integer.",
    )
    epsilon: float = Field(
        default=0.001,
        description="Precision parameters, below which two values are considered equal when performing verifications.",
    )

    @model_validator(mode="after")
    def check_dates(self) -> "CleanRoundingParameters":
        """Validation of start, end and execution date

        :raises ValueError: If the start, end and execution date are not coherent
        :return: The CleanRoundingParameters if dates are validate
        :rtype: CleanRoundingParameters
        """
        if self.end_date < self.start_date:
            raise ValueError(
                f"Start date '{self.start_date.to_datetime_string()}' must be inferior "
                f"to end date '{self.end_date.to_datetime_string()}'"
            )
        return self
