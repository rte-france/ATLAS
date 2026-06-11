import pendulum
import pytest
from pydantic import ValidationError

from atlas.core.io_utils.parameters import DateParameters
from atlas.modules.intraday_price_forecast.parameters import IntradayPriceForecastParameters


@pytest.fixture
def valid_parameters_dict():
    """Create a valid parameters dictionary."""
    return {
        "temporal": {
            "start_date": "2024-01-01T00:00:00+00:00",
            "end_date": "2024-01-02T00:00:00+00:00",
            "execution_date": "2024-01-01T12:00:00+00:00",
            "timestep": "1h",
        },
        "intraday_negative_price_cap": -500,
        "intraday_positive_price_cap": 4000,
        "execution_date_day_ahead": "2024-01-01T10:00:00+00:00",
        "execution_date_scenarios": "2024-01-01T08:00:00+00:00",
    }


def test_parameters_initialization(valid_parameters_dict):
    """Test that parameters can be initialized with valid data."""
    params = IntradayPriceForecastParameters(**valid_parameters_dict)

    assert params.intraday_negative_price_cap == -500
    assert params.intraday_positive_price_cap == 4000
    assert isinstance(params.temporal, DateParameters)
    assert isinstance(params.execution_date_day_ahead, pendulum.DateTime)
    assert isinstance(params.execution_date_scenarios, pendulum.DateTime)


def test_penultimate_date_property(valid_parameters_dict):
    """Test that penultimate_date is calculated correctly."""
    params = IntradayPriceForecastParameters(**valid_parameters_dict)

    expected_penultimate = params.temporal.end_date - params.temporal.timestep
    assert params.penultimate_date == expected_penultimate


def test_negative_price_cap_validation():
    """Test that negative price cap must be non-positive."""
    params_dict = {
        "temporal": {
            "start_date": "2024-01-01T00:00:00+00:00",
            "end_date": "2024-01-02T00:00:00+00:00",
            "execution_date": "2024-01-01T12:00:00+00:00",
            "timestep": "1h",
        },
        "intraday_negative_price_cap": 100,  # Invalid: should be negative
        "intraday_positive_price_cap": 4000,
        "execution_date_day_ahead": "2024-01-01T10:00:00+00:00",
        "execution_date_scenarios": "2024-01-01T08:00:00+00:00",
    }

    with pytest.raises(ValidationError):
        IntradayPriceForecastParameters(**params_dict)


def test_positive_price_cap_validation():
    """Test that positive price cap must be non-negative."""
    params_dict = {
        "temporal": {
            "start_date": "2024-01-01T00:00:00+00:00",
            "end_date": "2024-01-02T00:00:00+00:00",
            "execution_date": "2024-01-01T12:00:00+00:00",
            "timestep": "1h",
        },
        "intraday_negative_price_cap": -500,
        "intraday_positive_price_cap": -1000,  # Invalid: should be positive
        "execution_date_day_ahead": "2024-01-01T10:00:00+00:00",
        "execution_date_scenarios": "2024-01-01T08:00:00+00:00",
    }

    with pytest.raises(ValidationError):
        IntradayPriceForecastParameters(**params_dict)


def test_default_price_caps(valid_parameters_dict):
    """Test that default price caps are applied when not specified."""
    # Remove price caps from dict
    params_dict = valid_parameters_dict.copy()
    params_dict.pop("intraday_negative_price_cap", None)
    params_dict.pop("intraday_positive_price_cap", None)

    params = IntradayPriceForecastParameters(**params_dict)

    assert params.intraday_negative_price_cap == -500
    assert params.intraday_positive_price_cap == 4000


def test_penultimate_date_cached_property(valid_parameters_dict):
    """Test that penultimate_date is cached."""
    params = IntradayPriceForecastParameters(**valid_parameters_dict)

    # Access penultimate_date twice
    first_access = params.penultimate_date
    second_access = params.penultimate_date

    # Both should be the same object (cached)
    assert first_access is second_access
