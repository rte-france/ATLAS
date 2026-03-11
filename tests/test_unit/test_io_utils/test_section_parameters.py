from datetime import datetime

from atlas.io_utils.section_parameters import DateParameters


def test_valid_dates():
    params = DateParameters(
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        execution_date=datetime(2024, 6, 1),
    )
    assert params.start_date < params.end_date


def test_invalid_end_before_start():
    try:
        DateParameters(
            start_date=datetime(2024, 12, 31), end_date=datetime(2024, 1, 1), execution_date=datetime(2024, 12, 31)
        )
        assert False, "Expected ValueError for end_date before start_date"
    except ValueError as e:
        assert "Start date" in str(e)


def test_equal_start_end_dates():
    """Test that equal start and end dates are valid"""
    same_date = datetime(2024, 6, 1)
    params = DateParameters(
        start_date=same_date,
        end_date=same_date,
        execution_date=same_date,
    )
    assert params.start_date == params.end_date


def test_date_validation_boundary():
    """Test date validation at boundary conditions"""
    # Test with dates one second apart
    start = datetime(2024, 6, 1, 12, 0, 0)
    end = datetime(2024, 6, 1, 12, 0, 1)

    params = DateParameters(
        start_date=start,
        end_date=end,
        execution_date=start,
    )
    assert params.start_date < params.end_date
