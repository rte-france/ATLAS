from pathlib import Path
import pendulum
from datetime import datetime

from atlas.utils.clean_rounding.clean_rounding_parameters import CleanRoundingParameters


def test_default_parameters():
    parameters_path = Path(__file__).parent / "minimalist_clean_rounding_parameters.json"
    parameters = CleanRoundingParameters.from_file(parameters_path)
    assert parameters.start_date == datetime(2025, 11, 25, 15, 50, tzinfo=pendulum.tz.UTC)
    assert parameters.end_date == datetime(2025, 11, 25, 16, 50, tzinfo=pendulum.tz.UTC)
    assert parameters.rounding_precision == 2
    assert parameters.epsilon == 0.001


def test_parameters():
    parameters_path = Path(__file__).parent / "clean_rounding_parameters.json"
    parameters = CleanRoundingParameters.from_file(parameters_path)
    assert parameters.start_date == datetime(2025, 11, 25, 15, 50, tzinfo=pendulum.tz.UTC)
    assert parameters.end_date == datetime(2025, 11, 25, 16, 50, tzinfo=pendulum.tz.UTC)
    assert parameters.rounding_precision == 3
    assert parameters.epsilon == 0.05
