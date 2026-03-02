import unittest

import pendulum
from pendulum import duration

from atlas.modules.price_forecast.price_forecast_parameters import PriceForecastParameters


class TestIDPriceForecastParametersDurationValidator(unittest.TestCase):
    """Test suite for duration field validator."""

    def test_parse_duration_with_string(self):
        """Test parsing duration from string format."""
        params = PriceForecastParameters(
            start_date=pendulum.datetime(2024, 1, 1),
            end_date=pendulum.datetime(2024, 1, 2),
            execution_date=pendulum.datetime(2024, 1, 1),
            time_step="2h",
        )

        assert params.time_step == duration(hours=2)

    def test_parse_duration_with_duration_object(self):
        """Test parsing duration when already a Duration object."""
        params = PriceForecastParameters(
            start_date=pendulum.datetime(2024, 1, 1),
            end_date=pendulum.datetime(2024, 1, 2),
            execution_date=pendulum.datetime(2024, 1, 1),
            time_step=duration(minutes=30),
        )

        assert params.time_step == duration(minutes=30)


class TestIDPriceForecastParametersDateTimeValidator(unittest.TestCase):
    """Test suite for datetime field validator."""

    def test_execution_date_day_ahead(self):
        """Test execution_date_day_ahead."""
        params = PriceForecastParameters(
            start_date=pendulum.datetime(2024, 1, 1),
            end_date=pendulum.datetime(2024, 1, 2),
            execution_date=pendulum.datetime(2024, 1, 1),
            execution_date_day_ahead=pendulum.datetime(2025, 1, 1),
        )

        assert params.execution_date_day_ahead == pendulum.datetime(2025, 1, 1)

    def test_execution_date_day_ahead(self):
        """Test execution_date_day_ahead."""
        params = PriceForecastParameters(
            start_date=pendulum.datetime(2024, 1, 1),
            end_date=pendulum.datetime(2024, 1, 2),
            execution_date=pendulum.datetime(2024, 1, 1),
            execution_date_scenarios=pendulum.datetime(2025, 1, 1),
        )

        assert params.execution_date_scenarios == pendulum.datetime(2025, 1, 1)


class TestIDPriceForecastParametersBuiltinData(unittest.TestCase):
    """Test suite for default value in field."""

    def test_debug_field(self):
        """Test execution_date_day_ahead."""
        params = PriceForecastParameters(
            start_date=pendulum.datetime(2024, 1, 1),
            end_date=pendulum.datetime(2024, 1, 2),
            execution_date=pendulum.datetime(2024, 1, 1),
            debug=True,
        )

        assert params.debug is True

    def test_verbose_field(self):
        """Test execution_date_day_ahead."""
        params = PriceForecastParameters(
            start_date=pendulum.datetime(2024, 1, 1),
            end_date=pendulum.datetime(2024, 1, 2),
            execution_date=pendulum.datetime(2024, 1, 1),
            verbose=True,
        )

        assert params.verbose is True

    # FIXME
    #   question: seems logic that lower bound need to be bigger than upper bound
    #   do we add a test that raise a warning when it is not the case? Or even raise an error?
    #   question2: must intraday_negative_price_cap be negative? Hence raise an error when negative?
    #   question3: must intraday_positive_price_cap be positive? Hence raise an error when negative?
    def test_price_cap_field(self):
        """Test execution_date_day_ahead."""
        params = PriceForecastParameters(
            start_date=pendulum.datetime(2024, 1, 1),
            end_date=pendulum.datetime(2024, 1, 2),
            execution_date=pendulum.datetime(2024, 1, 1),
            intraday_negative_price_cap=-1,
            intraday_positive_price_cap=1,
        )

        assert params.intraday_negative_price_cap == -1
        assert params.intraday_positive_price_cap == 1
