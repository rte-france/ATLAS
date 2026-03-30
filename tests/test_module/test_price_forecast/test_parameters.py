import unittest

import pendulum
from pendulum import duration

from atlas.io_utils.section_parameters import DateParameters
from atlas.modules.intraday_price_forecast.parameters import IntradayPriceForecastParameters


class TestIDPriceForecastParametersDurationValidator(unittest.TestCase):
    """Test suite for duration field validator."""

    def test_parse_duration_with_string(self):
        """Test parsing duration from string format."""
        temporal = DateParameters(
            start_date=pendulum.datetime(2024, 1, 1),
            end_date=pendulum.datetime(2024, 1, 2),
            execution_date=pendulum.datetime(2024, 1, 1),
            timestep="2h",
        )
        params = IntradayPriceForecastParameters(
            temporal=temporal,
        )

        assert params.temporal.timestep == duration(hours=2)

    def test_parse_duration_with_duration_object(self):
        """Test parsing duration when already a Duration object."""
        temporal = DateParameters(
            start_date=pendulum.datetime(2024, 1, 1),
            end_date=pendulum.datetime(2024, 1, 2),
            execution_date=pendulum.datetime(2024, 1, 1),
            timestep=duration(minutes=30),
        )
        params = IntradayPriceForecastParameters(
            temporal=temporal,
        )

        assert params.temporal.timestep == duration(minutes=30)


class TestIDPriceForecastParametersDateTimeValidator(unittest.TestCase):
    """Test suite for datetime field validator."""

    def test_execution_date_day_ahead(self):
        """Test execution_date_day_ahead."""
        temporal = DateParameters(
            start_date=pendulum.datetime(2024, 1, 1),
            end_date=pendulum.datetime(2024, 1, 2),
            execution_date=pendulum.datetime(2024, 1, 1),
        )
        params = IntradayPriceForecastParameters(
            temporal=temporal,
            execution_date_day_ahead=pendulum.datetime(2025, 1, 1),
        )

        assert params.execution_date_day_ahead == pendulum.datetime(2025, 1, 1)

    def test_execution_date_scenarios(self):
        """Test execution_date_scenarios."""
        temporal = DateParameters(
            start_date=pendulum.datetime(2024, 1, 1),
            end_date=pendulum.datetime(2024, 1, 2),
            execution_date=pendulum.datetime(2024, 1, 1),
        )
        params = IntradayPriceForecastParameters(
            temporal=temporal,
            execution_date_scenarios=pendulum.datetime(2025, 1, 1),
        )

        assert params.execution_date_scenarios == pendulum.datetime(2025, 1, 1)


class TestIDPriceForecastParametersBuiltinData(unittest.TestCase):
    """Test suite for default value in field."""

    # FIXME
    #   question: seems logic that lower bound need to be bigger than upper bound
    #   do we add a test that raise a warning when it is not the case? Or even raise an error?
    #   question2: must intraday_negative_price_cap be negative? Hence raise an error when negative?
    #   question3: must intraday_positive_price_cap be positive? Hence raise an error when negative?
    def test_price_cap_field(self):
        """Test price cap fields."""
        temporal = DateParameters(
            start_date=pendulum.datetime(2024, 1, 1),
            end_date=pendulum.datetime(2024, 1, 2),
            execution_date=pendulum.datetime(2024, 1, 1),
        )
        params = IntradayPriceForecastParameters(
            temporal=temporal,
            intraday_negative_price_cap=-1,
            intraday_positive_price_cap=1,
        )

        assert params.intraday_negative_price_cap == -1
        assert params.intraday_positive_price_cap == 1
