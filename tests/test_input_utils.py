"""
Tests for the input_utils module.
"""

import pytest
from samstacks.input_utils import process_cli_input_value
from samstacks.exceptions import ManifestError


class TestProcessCliInputValue:
    """Test the process_cli_input_value utility function."""

    def test_string_input_valid(self):
        """Test processing a valid string input."""
        definition = {"type": "string"}
        result = process_cli_input_value("test_input", "hello world", definition)
        assert result == "hello world"

    def test_string_input_with_whitespace_trimmed(self):
        """Test that string input whitespace is trimmed."""
        definition = {"type": "string"}
        result = process_cli_input_value("test_input", "  hello world  ", definition)
        assert result == "hello world"

    def test_whitespace_only_returns_none(self):
        """Test that whitespace-only input returns None."""
        definition = {"type": "string"}
        result = process_cli_input_value("test_input", "   ", definition)
        assert result is None

    def test_empty_string_returns_none(self):
        """Test that empty string returns None."""
        definition = {"type": "string"}
        result = process_cli_input_value("test_input", "", definition)
        assert result is None

    @pytest.mark.parametrize(
        "valid_number_str, expected_value",
        [
            ("123", 123),
            ("3.14", 3.14),
            ("-5", -5),
            ("0", 0),
            ("42.0", 42),  # float 42.0 becomes int 42
        ],
    )
    def test_number_input_valid(self, valid_number_str: str, expected_value: any):
        """Test processing valid number inputs returns coerced numeric types."""
        definition = {"type": "number"}
        result = process_cli_input_value("test_input", valid_number_str, definition)
        assert result == expected_value
        assert isinstance(result, (int, float))

    def test_number_input_invalid(self):
        """Test that invalid number input raises ManifestError."""
        definition = {"type": "number"}
        with pytest.raises(
            ManifestError,
            match=r"CLI must be a number. Received: 'not_a_number'",
        ):
            process_cli_input_value("test_input", "not_a_number", definition)

    @pytest.mark.parametrize(
        "valid_bool_str, expected_value",
        [
            ("true", True),
            ("FALSE", False),
            ("yes", True),
            ("NO", False),
            ("1", True),
            ("0", False),
            ("on", True),
            ("OFF", False),
        ],
    )
    def test_boolean_input_valid(self, valid_bool_str: str, expected_value: bool):
        """Test processing valid boolean inputs returns coerced boolean types."""
        definition = {"type": "boolean"}
        result = process_cli_input_value("test_input", valid_bool_str, definition)
        assert result == expected_value
        assert isinstance(result, bool)

    def test_boolean_input_invalid(self):
        """Test that invalid boolean input raises ManifestError."""
        definition = {"type": "boolean"}
        with pytest.raises(
            ManifestError,
            match=r"CLI must be a boolean. Received: 'maybe'",
        ):
            process_cli_input_value("test_input", "maybe", definition)

    def test_default_type_is_string(self):
        """Test that missing type defaults to string."""
        definition = {}  # No type specified
        result = process_cli_input_value("test_input", "any value", definition)
        assert result == "any value"

    def test_number_with_whitespace_trimmed_and_validated(self):
        """Test that number input is trimmed and then validated."""
        definition = {"type": "number"}
        result = process_cli_input_value("test_input", "  42.5  ", definition)
        assert result == 42.5
        assert isinstance(result, float)

    def test_boolean_with_whitespace_trimmed_and_validated(self):
        """Test that boolean input is trimmed and then validated."""
        definition = {"type": "boolean"}
        result = process_cli_input_value("test_input", "  true  ", definition)
        assert result is True
        assert isinstance(result, bool)
