"""
Utility functions for processing CLI input values.
"""

from typing import Any, Dict, Optional

from .exceptions import ManifestError


def process_cli_input_value(
    input_name: str, cli_value: str, input_definition: Dict[str, Any]
) -> Optional[str]:
    """
    Process and validate a CLI input value.

    Args:
        input_name: Name of the input
        cli_value: Raw CLI input value
        input_definition: Input definition from manifest

    Returns:
        Processed CLI value (trimmed) or None if value is whitespace-only

    Raises:
        ManifestError: If the value doesn't match the expected type
    """
    # Trim whitespace
    trimmed_value = cli_value.strip()

    # Treat whitespace-only as not provided
    if not trimmed_value:
        return None

    # Validate type
    input_type = input_definition.get("type", "string")

    if input_type == "number":
        try:
            float(trimmed_value)  # Check if convertible to float (int or float)
        except ValueError:
            raise ManifestError(
                f"Input '{input_name}' must be a number. Received: '{trimmed_value}'"
            )
    elif input_type == "boolean":
        if trimmed_value.lower() not in (
            "true",
            "false",
            "yes",
            "no",
            "1",
            "0",
            "on",
            "off",
        ):
            raise ManifestError(
                f"Input '{input_name}' must be a boolean. Received: '{trimmed_value}'"
            )
    # String type needs no specific validation

    return trimmed_value
