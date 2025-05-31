"""
Template processing for samstacks manifest and configuration files.
"""

import os
import re
from typing import Dict, Any, Optional

from .exceptions import TemplateError

# Import simpleeval for mathematical expressions
try:
    from simpleeval import simple_eval, DEFAULT_OPERATORS, DEFAULT_FUNCTIONS  # type: ignore
except ImportError:
    # Graceful fallback if simpleeval is not available
    simple_eval = None
    DEFAULT_OPERATORS = None
    DEFAULT_FUNCTIONS = None


class TemplateProcessor:
    """Handles template substitution for environment variables and stack outputs."""

    def __init__(
        self,
        defined_inputs: Optional[Dict[str, Any]] = None,
        cli_inputs: Optional[Dict[str, str]] = None,
        # Optional pipeline context for direct use if needed, though typically passed per call
        pipeline_name: Optional[str] = None,
        pipeline_description: Optional[str] = None,
    ) -> None:
        """Initialize the template processor."""
        self.stack_outputs: Dict[str, Dict[str, str]] = {}
        self.defined_inputs: Dict[str, Any] = defined_inputs or {}
        self.cli_inputs: Dict[str, str] = cli_inputs or {}
        # Store initial pipeline context if provided, can be overridden by call-specific context
        self.pipeline_name = pipeline_name
        self.pipeline_description = pipeline_description

    def add_stack_outputs(self, stack_id: str, outputs: Dict[str, str]) -> None:
        """Add outputs from a deployed stack for use in template substitution."""
        self.stack_outputs[stack_id] = outputs

    def process_string(
        self,
        template_string: Optional[str],
        pipeline_name: Optional[str] = None,
        pipeline_description: Optional[str] = None,
    ) -> str:
        """Process a template string, substituting all ${{ ... }} expressions."""
        if not template_string:
            return ""

        # Effective pipeline context for this call
        current_call_context = {
            "pipeline_name": pipeline_name
            if pipeline_name is not None
            else self.pipeline_name,
            "pipeline_description": pipeline_description
            if pipeline_description is not None
            else self.pipeline_description,
        }

        pattern = r"\$\{\{\s*([^}]+)\s*\}\}"

        def replace_expression(match: re.Match[str]) -> str:
            expression_body = match.group(1).strip()
            return self._evaluate_expression_with_fallbacks(
                expression_body, current_call_context
            )

        try:
            return re.sub(pattern, replace_expression, template_string)
        except TemplateError:
            raise
        except Exception as e:
            raise TemplateError(
                f"Failed to process template string '{template_string}': {e}"
            )

    def process_structure(
        self,
        data_structure: Any,
        pipeline_name: Optional[str] = None,
        pipeline_description: Optional[str] = None,
    ) -> Any:
        """
        Recursively processes a data structure (dict or list), applying
        self.process_string() to all string values.
        Passes pipeline_name and pipeline_description for context.
        """
        current_pipeline_name = (
            pipeline_name if pipeline_name is not None else self.pipeline_name
        )
        current_pipeline_description = (
            pipeline_description
            if pipeline_description is not None
            else self.pipeline_description
        )

        if isinstance(data_structure, dict):
            processed_dict = {}
            for key, value in data_structure.items():
                processed_key = (
                    self.process_string(
                        key,
                        pipeline_name=current_pipeline_name,
                        pipeline_description=current_pipeline_description,
                    )
                    if isinstance(key, str)
                    else key
                )

                processed_dict[processed_key] = self.process_structure(
                    value,
                    pipeline_name=current_pipeline_name,
                    pipeline_description=current_pipeline_description,
                )
            return processed_dict
        elif isinstance(data_structure, list):
            return [
                self.process_structure(
                    item,
                    pipeline_name=current_pipeline_name,
                    pipeline_description=current_pipeline_description,
                )
                for item in data_structure
            ]
        elif isinstance(data_structure, str):
            return self.process_string(
                data_structure,
                pipeline_name=current_pipeline_name,
                pipeline_description=current_pipeline_description,
            )
        else:
            return data_structure

    def _evaluate_expression_with_fallbacks(
        self, expression_body: str, call_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Evaluate a template expression, handling || for fallbacks.
        Splits by || ensuring not to split within quoted literals.
        """
        # Split by || for fallback behavior, but be careful about quoted strings
        parts = re.split(
            r"\|\|(?=(?:[^\'\"]|\"[^\"]*\"|\'[^\']*\')*$)", expression_body
        )
        call_context = call_context or {}

        for part_str in parts:
            part_trimmed: str = part_str.strip()
            resolved_value: Optional[str] = self._resolve_single_part(
                part_trimmed, call_context
            )

            if resolved_value is not None and resolved_value != "":
                return resolved_value

        if not parts:
            return ""

        # Re-resolve the last part to ensure we get its actual resolved value (None or "")
        last_part_actual_trimmed: str = parts[-1].strip()
        if not last_part_actual_trimmed:
            return ""

        last_part_resolved_value: Optional[str] = self._resolve_single_part(
            last_part_actual_trimmed, call_context
        )
        return last_part_resolved_value if last_part_resolved_value is not None else ""

    def _resolve_single_part(
        self, part_expression: str, call_context: Dict[str, Any]
    ) -> Optional[str]:
        """Resolve a single part of an expression by first substituting placeholders, then evaluating."""

        # Handle quoted literals first
        if (part_expression.startswith("'") and part_expression.endswith("'")) or (
            part_expression.startswith('"') and part_expression.endswith('"')
        ):
            return part_expression[1:-1]

        # Step 1: Find and resolve all samstacks placeholders in the expression
        resolved_expression = self._substitute_placeholders(
            part_expression, call_context
        )

        # Step 2: If the expression now contains only literals and operators, evaluate it with simpleeval
        if simple_eval is not None and self._contains_operators_or_complex_logic(
            resolved_expression
        ):
            try:
                # Preprocess JavaScript-style operators
                processed_expr = resolved_expression
                # Replace && with and (but not within quotes)
                processed_expr = re.sub(
                    r'(?<!["\'])(\s*)&&(\s*)(?!["\'])', r"\1and\2", processed_expr
                )
                # Replace || with or (but not within quotes)
                processed_expr = re.sub(
                    r'(?<!["\'])(\s*)\|\|(\s*)(?!["\'])', r"\1or\2", processed_expr
                )
                # Replace ! with not (but be careful not to affect != operator)
                processed_expr = re.sub(r"(?<![=!<>])!\s*(?!=)", "not ", processed_expr)

                # Use simpleeval with minimal, safe context (no custom objects)
                result = simple_eval(
                    processed_expr,
                    names={},  # No custom names needed - placeholders already resolved
                    operators=DEFAULT_OPERATORS.copy(),
                    functions=DEFAULT_FUNCTIONS.copy(),
                )

                # Convert result to string for template substitution
                if isinstance(result, bool):
                    return "true" if result else "false"
                elif isinstance(result, (int, float)):
                    # Preserve integer format if it's a whole number
                    if isinstance(result, float) and result.is_integer():
                        return str(int(result))
                    return str(result)
                else:
                    return str(result)

            except Exception:
                # If simpleeval fails, return the resolved expression as-is
                pass

        # Step 3: Return the resolved expression (may be a simple substitution)
        return resolved_expression

    def _substitute_placeholders(
        self, expression: str, call_context: Dict[str, Any]
    ) -> str:
        """Replace all samstacks placeholders (env.X, inputs.Y, etc.) with their actual values."""

        # Find all placeholder patterns and replace them
        import re

        # Check if this is a simple single placeholder (no operators)
        placeholder_pattern = r"\b(?:env|inputs|stacks|pipeline)\.(?:[a-zA-Z_][a-zA-Z0-9_.-]*(?:\.[a-zA-Z_][a-zA-Z0-9_.-]*)*)?"
        placeholders = re.findall(placeholder_pattern, expression)

        # If expression is just a single placeholder with no other content, return raw value
        is_simple_substitution = (
            len(placeholders) == 1 and expression.strip() == placeholders[0]
        )

        def replace_placeholder(match: re.Match[str]) -> str:
            placeholder = match.group(0)

            if placeholder.startswith("env."):
                var_name = placeholder[4:]
                if not var_name:
                    return "None" if not is_simple_substitution else ""
                value = os.environ.get(var_name, "")
                return value if is_simple_substitution else repr(value)

            elif placeholder.startswith("inputs."):
                return self._resolve_input_placeholder(
                    placeholder, is_simple_substitution
                )

            elif placeholder.startswith("stacks."):
                return self._resolve_stack_placeholder(
                    placeholder, is_simple_substitution
                )

            elif placeholder.startswith("pipeline."):
                attr_name = placeholder[len("pipeline.") :]
                if attr_name == "name":
                    value = call_context.get("pipeline_name") or ""
                elif attr_name == "description":
                    value = call_context.get("pipeline_description") or ""
                else:
                    return "None" if not is_simple_substitution else ""
                return value if is_simple_substitution else repr(value)

            # If we can't resolve it, return appropriate default
            return "None" if not is_simple_substitution else ""

        return re.sub(placeholder_pattern, replace_placeholder, expression)

    def _resolve_input_placeholder(
        self, placeholder: str, is_simple_substitution: bool = False
    ) -> str:
        """Resolve an inputs.X placeholder to its actual value."""
        input_name = placeholder[7:]  # Remove "inputs."

        if not input_name:
            # Empty input name should raise an error
            raise TemplateError("Empty input name in expression 'inputs.'")

        cli_value_str = self.cli_inputs.get(input_name)
        input_definition = self.defined_inputs.get(input_name)

        if input_definition is None:
            return "" if is_simple_substitution else "None"

        input_type = input_definition.get("type", "string")
        resolved_value = None

        # Process CLI input using shared utility
        if cli_value_str is not None:
            try:
                from .input_utils import process_cli_input_value
                from .exceptions import ManifestError

                processed_cli_value = process_cli_input_value(
                    input_name, cli_value_str, input_definition
                )
                if processed_cli_value is not None:
                    resolved_value = processed_cli_value
                elif "default" in input_definition:
                    resolved_value = input_definition["default"]
                else:
                    return "" if is_simple_substitution else "None"
            except ManifestError as e:
                # Convert ManifestError to TemplateError for consistency
                raise TemplateError(str(e)) from e
        elif "default" in input_definition:
            resolved_value = input_definition["default"]
        else:
            return "" if is_simple_substitution else "None"

        # Return the value in appropriate format
        if is_simple_substitution:
            # For simple substitution, return the raw value as string
            if input_type == "boolean":
                # Convert Python boolean to lowercase string
                return "true" if resolved_value else "false"
            else:
                return str(resolved_value)
        else:
            # For expressions, return properly formatted for simpleeval
            if input_type == "string":
                return repr(str(resolved_value))  # Quoted string
            elif input_type in ("number", "boolean"):
                return str(resolved_value)  # Unquoted number/boolean
            else:
                return repr(str(resolved_value))  # Default to quoted string

    def _resolve_stack_placeholder(
        self, placeholder: str, is_simple_substitution: bool = False
    ) -> str:
        """Resolve a stacks.X.outputs.Y placeholder to its actual value."""
        parts = placeholder.split(".")

        if len(parts) != 4 or parts[0] != "stacks" or parts[2] != "outputs":
            # Malformed stack expression should raise an error
            raise TemplateError(
                f"Invalid stack output expression format: '{placeholder}'. "
                "Expected format: stacks.stack_id.outputs.output_name"
            )

        stack_id = parts[1]
        output_name = parts[3]

        if not stack_id or not output_name:
            return "" if is_simple_substitution else "None"

        stack_outputs = self.stack_outputs.get(stack_id, {})
        output_value = stack_outputs.get(output_name)

        if output_value is None:
            return "" if is_simple_substitution else "None"

        # For simple substitution, return raw value; for expressions, quote it
        return output_value if is_simple_substitution else repr(output_value)

    def _contains_operators_or_complex_logic(self, expression: str) -> bool:
        """Check if expression contains operators or logic that simpleeval should handle."""
        # Look for mathematical operators, comparisons, boolean logic
        operator_patterns = [
            r"[+\-*/]",  # Math operators
            r"[<>=!]=?",  # Comparison operators
            r"\b(?:and|or|not)\b",  # Boolean operators
            r"[()]",  # Parentheses
        ]

        for pattern in operator_patterns:
            if re.search(pattern, expression):
                return True
        return False
