"""
Template processing for samstacks manifest and configuration files.
"""

import os
import re
from typing import Dict, List

from .exceptions import TemplateError


class TemplateProcessor:
    """Handles template substitution for environment variables and stack outputs."""

    def __init__(self) -> None:
        """Initialize the template processor."""
        self.stack_outputs: Dict[str, Dict[str, str]] = {}

    def add_stack_outputs(self, stack_id: str, outputs: Dict[str, str]) -> None:
        """Add outputs from a deployed stack for use in template substitution."""
        self.stack_outputs[stack_id] = outputs

    def process_string(self, template_string: str | None) -> str:
        """Process a template string, substituting all ${{ ... }} expressions."""
        if not template_string:
            return ""

        # Pattern to match ${{ ... }} expressions
        pattern = r"\$\{\{\s*([^}]+)\s*\}\}"

        def replace_expression(match: re.Match[str]) -> str:
            expression_body = match.group(1).strip()
            # Pass the full expression for better error reporting if needed later
            return self._evaluate_expression_with_fallbacks(expression_body)

        try:
            return re.sub(pattern, replace_expression, template_string)
        except TemplateError:  # Propagate TemplateError directly
            raise
        except Exception as e:
            raise TemplateError(
                f"Failed to process template string '{template_string}': {e}"
            )

    def _evaluate_expression_with_fallbacks(self, expression_body: str) -> str:
        """Evaluate a template expression, handling || for fallbacks.
        Splits by || ensuring not to split within quoted literals.
        """
        parts = re.split(
            r"\|\|(?=(?:[^\'\"]|\"[^\"]*\"|\'[^\']*\')*$)", expression_body
        )

        for part_str in parts:
            part_trimmed: str = part_str.strip()
            resolved_value: str | None = self._resolve_single_part(part_trimmed)

            if (
                resolved_value is not None and resolved_value != ""
            ):  # Found a truthy, non-empty value
                return resolved_value
            # If resolved_value is "" (empty string), it's falsy, so we continue to the next part.
            # If resolved_value is None (genuinely not found/unresolved), it's also falsy, continue.

        # If loop finishes, all parts were falsy (None or empty string).
        # The value of the expression is the value of the last part.
        # If the last part was unresolvable (None), the result is empty string.
        # If the last part was a resolvable empty string (e.g. env.EMPTY or literal ''), result is empty string.
        if not parts:  # Should not happen with a non-empty expression_body
            return ""

        # Re-resolve the last part to ensure we get its actual resolved value (None or "")
        # This handles the case where all parts were None, or the last part was explicitly an empty string.
        last_actual_part_trimmed: str = parts[-1].strip()
        if not last_actual_part_trimmed:
            # Expression like ${{ env.FOO || }}
            return ""  # Fallback to empty if last part is effectively empty due to stripping

        last_part_resolved_value: str | None = self._resolve_single_part(
            last_actual_part_trimmed
        )

        return last_part_resolved_value if last_part_resolved_value is not None else ""

    def _resolve_single_part(self, part_expression: str) -> str | None:
        """Resolve a single part of an expression (e.g., env.VAR, stacks.ID.outputs.NAME, or 'literal')."""
        # Handle environment variables: env.VARIABLE_NAME
        if part_expression.startswith("env."):
            var_name: str = part_expression[4:]
            return os.environ.get(var_name)  # Returns None if not found

        # Handle stack outputs: stacks.stack_id.outputs.output_name
        if part_expression.startswith("stacks."):
            return self._evaluate_stack_output(
                part_expression
            )  # Returns None if output not found

        # Handle literals (single or double quoted strings)
        if (part_expression.startswith("'") and part_expression.endswith("'")) or (
            part_expression.startswith('"') and part_expression.endswith('"')
        ):
            return part_expression[1:-1]  # Strip quotes

        # If not env, stacks, or literal, it's an unknown type for now
        # For it to be part of a fallback chain like ${{ VAR1 || VAR2 }}, VAR1 must resolve.
        # An unquoted string that is not env. or stacks. is effectively an undefined variable.
        # Let's treat it as None to allow fallback. If it's the only item, it will become "".
        return None

    def _evaluate_stack_output(self, expression: str) -> str | None:
        """Evaluate a stack output expression: stacks.stack_id.outputs.output_name.
        Returns None if the stack or output is not found, to allow fallbacks.
        """
        parts: List[str] = expression.split(".")

        if len(parts) != 4 or parts[0] != "stacks" or parts[2] != "outputs":
            # This is a malformed expression, not just a missing output.
            raise TemplateError(
                f"Invalid stack output expression format: '{expression}'. "
                "Expected: stacks.stack_id.outputs.output_name"
            )

        stack_id: str = parts[1]
        output_name: str = parts[3]

        stack_outputs_for_id: Dict[str, str] | None = self.stack_outputs.get(stack_id)
        if stack_outputs_for_id is None:
            # Stack itself not found in outputs, could be a legitimate fallback case.
            # Or an error if the user expects the stack to exist.
            # For || behavior, we return None to allow fallback.
            # If strict checking of stack_id presence is needed elsewhere, it can be done.
            return None

        return stack_outputs_for_id.get(
            output_name
        )  # Returns None if output_name not in dict
