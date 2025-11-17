"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import io
from unittest.mock import Mock

import pendulum
import pytest
from loguru import logger

from atlas.solver.model_var import ModelVar


class TestModelVar:
    """Test suite for the ModelVar class."""

    @pytest.fixture
    def mock_getter(self):
        """Create a mock getter function."""
        mock = Mock()
        # By default, raise ValueError to simulate out-of-bounds access
        mock.side_effect = ValueError("DateTime out of model bounds")
        return mock

    @pytest.fixture
    def mock_setter(self):
        """Create a mock setter function."""
        return Mock()

    @pytest.fixture
    def wrapper(self, mock_getter, mock_setter):
        """Create a ModelVar instance with mock getter and setter."""
        return ModelVar(getter=mock_getter, setter=mock_setter)

    @pytest.fixture
    def sample_datetime(self):
        """Create a sample DateTime for testing."""
        return pendulum.datetime(2025, 1, 1, 12, 0, 0)

    @pytest.fixture
    def another_datetime(self):
        """Create another sample DateTime for testing."""
        return pendulum.datetime(2025, 1, 2, 12, 0, 0)

    def test_init(self, mock_getter, mock_setter):
        """Test that ModelVar initializes correctly."""
        wrapper = ModelVar(getter=mock_getter, setter=mock_setter)
        assert wrapper._getter == mock_getter
        assert wrapper._setter == mock_setter
        assert wrapper._extended_frame == {}

    def test_set_extended_stores_value(self, wrapper, sample_datetime):
        """Test that set_extended stores a value in the extended frame."""
        value = 42
        wrapper.set_extended(sample_datetime, value)
        assert sample_datetime in wrapper._extended_frame
        assert wrapper._extended_frame[sample_datetime] == value

    def test_get_extended_value_retrieves_value(self, wrapper, sample_datetime):
        """Test that get_extended_value retrieves a stored value."""
        value = 42
        wrapper.set_extended(sample_datetime, value)
        result = wrapper.get_extended_value(sample_datetime)
        assert result == value

    def test_get_extended_value_raises_keyerror(self, wrapper, sample_datetime):
        """Test that get_extended_value raises KeyError for missing keys."""
        with pytest.raises(KeyError):
            wrapper.get_extended_value(sample_datetime)

    def test_get_model_var_calls_getter(self, wrapper, mock_getter, sample_datetime):
        """Test that get_model_var calls the getter function."""
        expected_value = 100
        mock_getter.side_effect = None
        mock_getter.return_value = expected_value

        result = wrapper.get_model_var(sample_datetime)

        mock_getter.assert_called_once_with(sample_datetime)
        assert result == expected_value

    def test_get_model_var_raises_valueerror(self, wrapper, sample_datetime):
        """Test that get_model_var raises ValueError when getter does."""
        with pytest.raises(ValueError, match="DateTime out of model bounds"):
            wrapper.get_model_var(sample_datetime)

    def test_set_model_var_calls_setter(self, wrapper, mock_setter, sample_datetime):
        """Test that set_model_var calls the setter function."""
        wrapper.set_model_var(sample_datetime)
        mock_setter.assert_called_once_with(sample_datetime)

    def test_get_value_returns_from_extended_frame_first(self, wrapper, mock_getter, sample_datetime):
        """Test that get_value prioritizes extended frame over model."""
        extended_value = 42
        model_value = 100

        # Configure getter to return a different value (for the duplicate check in set_extended)
        mock_getter.side_effect = None
        mock_getter.return_value = model_value

        # Set value in extended frame (this will call getter once for duplicate check)
        wrapper.set_extended(sample_datetime, extended_value)

        # Reset the mock to track calls from get_value only
        mock_getter.reset_mock()

        result = wrapper.get_value(sample_datetime)

        # Should return extended frame value without calling getter
        assert result == extended_value
        mock_getter.assert_not_called()

    def test_get_value_falls_back_to_model(self, wrapper, mock_getter, sample_datetime):
        """Test that get_value falls back to model when not in extended frame."""
        model_value = 100
        mock_getter.side_effect = None
        mock_getter.return_value = model_value

        result = wrapper.get_value(sample_datetime)

        mock_getter.assert_called_once_with(sample_datetime)
        assert result == model_value

    def test_get_value_raises_valueerror_when_not_found(self, wrapper, sample_datetime):
        """Test that get_value raises ValueError when DateTime is nowhere."""
        # Extended frame is empty and getter raises ValueError
        with pytest.raises(ValueError, match="DateTime out of model bounds"):
            wrapper.get_value(sample_datetime)

    def test_set_extended_warns_on_duplicate_in_model(self, wrapper, mock_getter, sample_datetime):
        """Test that set_extended logs warning when DateTime exists in model."""
        model_value = 100
        mock_getter.side_effect = None
        mock_getter.return_value = model_value

        # Capture log output
        log_output = io.StringIO()
        handler_id = logger.add(log_output, format="{level} | {message}", level="WARNING")

        try:
            wrapper.set_extended(sample_datetime, 42)

            # Check that warning was logged
            log_content = log_output.getvalue()
            assert "duplicate" in log_content.lower()
            assert str(sample_datetime) in log_content
        finally:
            logger.remove(handler_id)

    def test_multiple_datetimes_in_extended_frame(self, wrapper, sample_datetime, another_datetime):
        """Test storing and retrieving multiple DateTimes in extended frame."""
        value1 = 42
        value2 = 100

        wrapper.set_extended(sample_datetime, value1)
        wrapper.set_extended(another_datetime, value2)

        assert wrapper.get_extended_value(sample_datetime) == value1
        assert wrapper.get_extended_value(another_datetime) == value2

    def test_extended_frame_is_empty_on_init(self, wrapper):
        """Test that extended frame is empty on initialization."""
        assert len(wrapper._extended_frame) == 0
