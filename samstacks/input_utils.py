"""
Utility functions for processing CLI input values.
"""

from typing import Any, Dict, Optional

from .exceptions import ManifestError


def coerce_and_validate_value(
    value: Any,
    input_name: str,
    input_definition: Dict[str, Any],
    value_source: str = "value",
) -> Any:
    """Coerce and validate a given value against the input definition.

    Args:
        value: The value to process (can be str, int, float, bool).
        input_name: Name of the input.
        input_definition: Input definition from manifest.
        value_source: Description of the value's origin (e.g., 'Default value', 'CLI').

    Returns:
        The coerced value matching the input type.

    Raises:
        ManifestError: If the value cannot be coerced to the expected type.
    """
    input_type = input_definition.get("type", "string")

    if input_type == "string":
        return str(value)
    elif input_type == "number":
        try:
            # Attempt to convert to float first, then to int if it's a whole number
            num_value = float(value)
            if num_value.is_integer():
                return int(num_value)
            return num_value
        except (ValueError, TypeError):
            raise ManifestError(
                f"{value_source.upper()} must be a number. Received: '{value}'"
            )
    elif input_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            val_lower = value.lower()
            if val_lower in ("true", "yes", "1", "on"):
                return True
            if val_lower in ("false", "no", "0", "off"):
                return False
        # If it's an int/float, 0 is false, non-zero is true is a common convention, but let's be strict to manifest types.
        # Manifest validator ensures default is bool if type is bool. CLI inputs are strings.
        # This function might receive already coerced bools from defaults.
        raise ManifestError(
            f"{value_source.upper()} must be a boolean. Received: '{value}'"
        )
    else:
        # Should not be reached if manifest validation is correct
        raise ManifestError(f"Unknown type '{input_type}' for input '{input_name}'.")


def process_cli_input_value(
    input_name: str, cli_value: str, input_definition: Dict[str, Any]
) -> Optional[Any]:
    """
    Process and validate a CLI input value string.

    Args:
        input_name: Name of the input
        cli_value: Raw CLI input value string
        input_definition: Input definition from manifest

    Returns:
        Processed and coerced CLI value, or None if value is whitespace-only.

    Raises:
        ManifestError: If the value doesn't match the expected type.
    """
    # Trim whitespace
    trimmed_value = cli_value.strip()

    # Treat whitespace-only as not provided, returning None
    if not trimmed_value:
        return None

    # Coerce and validate the trimmed string value
    return coerce_and_validate_value(
        trimmed_value, input_name, input_definition, value_source="CLI"
    )
