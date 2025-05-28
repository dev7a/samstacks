"""
Template processing for samstacks manifest and configuration files.
"""

import os
import re
from typing import Dict, List, Any, Optional

from .exceptions import TemplateError, ManifestError
from .input_utils import process_cli_input_value


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
        template_string: str | None,
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
        parts = re.split(
            r"\|\|(?=(?:[^\'\"]|\"[^\"]*\"|\'[^\']*\')*$)", expression_body
        )
        call_context = call_context or {}

        for part_str in parts:
            part_trimmed: str = part_str.strip()
            resolved_value: str | None = self._resolve_single_part(
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

        last_part_resolved_value: str | None = self._resolve_single_part(
            last_part_actual_trimmed, call_context
        )
        return last_part_resolved_value if last_part_resolved_value is not None else ""

    def _resolve_single_part(
        self, part_expression: str, call_context: Dict[str, Any]
    ) -> str | None:
        """Resolve a single part of an expression (e.g., env.VAR, stacks.ID.outputs.NAME, or 'literal')."""
        if part_expression.startswith("env."):
            var_name: str = part_expression[4:]
            return os.environ.get(var_name)

        if part_expression.startswith("inputs."):
            return self._evaluate_pipeline_input(part_expression)

        if part_expression.startswith("stacks."):
            return self._evaluate_stack_output(part_expression)

        if part_expression.startswith("pipeline."):
            attr_name = part_expression[len("pipeline.") :]
            if attr_name == "name":
                return call_context.get("pipeline_name")
            elif attr_name == "description":
                return call_context.get("pipeline_description")
            return None

        if (part_expression.startswith("'") and part_expression.endswith("'")) or (
            part_expression.startswith('"') and part_expression.endswith('"')
        ):
            return part_expression[1:-1]

        return part_expression

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

    def _evaluate_pipeline_input(self, expression: str) -> str | None:
        """Evaluate a pipeline input expression: inputs.input_name.
        Returns None if the input is not resolved, to allow fallbacks.
        """
        input_name: str = expression[7:]  # len("inputs.") == 7

        if not input_name:  # e.g. ${{ inputs. }}
            raise TemplateError(f"Empty input name in expression '{expression}'.")

        cli_value_str: Optional[str] = self.cli_inputs.get(input_name)
        input_definition: Optional[Dict[str, Any]] = self.defined_inputs.get(input_name)

        if input_definition is None:
            # Input not defined in manifest, treat as unresolvable for templating
            return None

        input_type: str = input_definition.get(
            "type", "string"
        )  # Default to string if somehow type is missing

        resolved_value: Any = None
        value_source: str = "none"

        # Process CLI input using shared utility
        if cli_value_str is not None:
            try:
                processed_cli_value = process_cli_input_value(
                    input_name, cli_value_str, input_definition
                )
                if processed_cli_value is not None:
                    resolved_value = processed_cli_value
                    value_source = "cli"
                elif "default" in input_definition:
                    # CLI value was whitespace-only, fall back to default
                    resolved_value = input_definition["default"]
                    value_source = "default"
                else:
                    # CLI value was whitespace-only and no default
                    return None
            except ManifestError as e:
                # Convert ManifestError to TemplateError for consistency in templating context
                raise TemplateError(str(e)) from e
        elif "default" in input_definition:
            resolved_value = input_definition["default"]
            value_source = "default"
        else:
            # No CLI value and no default, should be caught by Pipeline.validate() if required
            # For templating, this means the input is not available from primary sources.
            return None

        # Type conversion
        try:
            if input_type == "string":
                return str(resolved_value)
            elif input_type == "number":
                # Convert to float for validation/standardization, then check if it's a whole number.
                try:
                    num_value = float(
                        resolved_value
                    )  # Works for defaults (int/float) and CLI strings
                except ValueError as e:
                    # This should ideally be caught by Pipeline.validate() for CLI inputs
                    raise TemplateError(
                        f"Invalid number value for input '{input_name}': '{resolved_value}'"
                    ) from e

                if num_value.is_integer():
                    return str(int(num_value))
                else:
                    return str(num_value)
            elif input_type == "boolean":
                if value_source == "cli":
                    val_lower = str(resolved_value).lower()
                    if val_lower in ("true", "1", "yes", "on"):
                        return "true"  # Return string "true"
                    elif val_lower in ("false", "0", "no", "off"):
                        return "false"  # Return string "false"
                    else:
                        # This case should be caught by Pipeline.validate()
                        raise TemplateError(
                            f"Invalid boolean string for input '{input_name}': '{resolved_value}'"
                        )
                else:  # Default boolean value
                    return "true" if resolved_value else "false"
            else:
                # Should not happen due to manifest validation
                raise TemplateError(
                    f"Unknown input type '{input_type}' for input '{input_name}'."
                )
        except ValueError as e:
            # Handles float conversion error for number type from CLI
            raise TemplateError(
                f"Type conversion error for input '{input_name}' ('{input_type}') with value '{resolved_value}': {e}"
            )
