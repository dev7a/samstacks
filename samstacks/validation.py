"""
Validation utilities for samstacks manifests and template expressions.
"""

import re
from typing import Any, Dict, List, Set, Optional
from pathlib import Path

import yaml

from .exceptions import ManifestError


class ValidationError:
    """Represents a single validation error."""

    def __init__(
        self, message: str, context: str = "", line_number: Optional[int] = None
    ):
        self.message = message
        self.context = context
        self.line_number = line_number

    def __str__(self) -> str:
        parts = []
        if self.context:
            parts.append(self.context)

        message = self.message
        if self.line_number is not None:
            message += f" (line {self.line_number})"

        if parts:
            prefix = " | ".join(parts)
            return f"{prefix}: {message}"
        return message


class LineNumberTracker:
    """Tracks line numbers for YAML nodes."""

    def __init__(self, manifest_path: Optional[Path] = None):
        self.manifest_path = manifest_path
        self.node_lines: Dict[int, int] = {}  # Maps object id to line number

    def track_node(self, node: Any, line_number: int) -> None:
        """Track the line number for a YAML node."""
        if hasattr(node, "__dict__") or isinstance(node, (dict, list)):
            self.node_lines[id(node)] = line_number

    def get_line_number(self, obj: Any) -> Optional[int]:
        """Get the line number for an object."""
        return self.node_lines.get(id(obj))

    def parse_yaml_with_line_numbers(
        self, yaml_content: str
    ) -> tuple[Dict[str, Any], "LineNumberTracker"]:
        """Parse YAML and track line numbers for all nodes."""

        class LineNumberLoader(yaml.SafeLoader):
            pass

        def construct_mapping(
            loader: yaml.SafeLoader, node: yaml.MappingNode
        ) -> Dict[str, Any]:
            loader.flatten_mapping(node)
            result: Dict[str, Any] = {}

            # Track line number for the mapping itself
            if hasattr(node, "start_mark") and node.start_mark:
                self.track_node(result, node.start_mark.line + 1)

            for key_node, value_node in node.value:
                key = loader.construct_object(key_node)
                value = loader.construct_object(value_node)

                # Track line numbers for key and value
                if hasattr(key_node, "start_mark") and key_node.start_mark:
                    self.track_node(key, key_node.start_mark.line + 1)
                if hasattr(value_node, "start_mark") and value_node.start_mark:
                    self.track_node(value, value_node.start_mark.line + 1)

                result[key] = value

            return result

        def construct_sequence(
            loader: yaml.SafeLoader, node: yaml.SequenceNode
        ) -> List[Any]:
            result: List[Any] = []

            # Track line number for the sequence itself
            if hasattr(node, "start_mark") and node.start_mark:
                self.track_node(result, node.start_mark.line + 1)

            for item_node in node.value:
                item = loader.construct_object(item_node)
                if hasattr(item_node, "start_mark") and item_node.start_mark:
                    self.track_node(item, item_node.start_mark.line + 1)
                result.append(item)

            return result

        LineNumberLoader.add_constructor(
            yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping
        )
        LineNumberLoader.add_constructor(
            yaml.resolver.BaseResolver.DEFAULT_SEQUENCE_TAG, construct_sequence
        )

        try:
            data = yaml.load(yaml_content, Loader=LineNumberLoader)
            return data, self
        except yaml.YAMLError as e:
            raise ManifestError(f"Failed to parse YAML: {e}")


class ManifestValidator:
    """Validates samstacks manifest structure and template expressions."""

    # Valid fields for each section
    VALID_PIPELINE_FIELDS = {
        "pipeline_name",
        "pipeline_description",
        "pipeline_settings",
        "stacks",
    }

    VALID_PIPELINE_SETTINGS_FIELDS = {
        "stack_name_prefix",
        "stack_name_suffix",
        "default_region",
        "default_profile",
    }

    VALID_STACK_FIELDS = {
        "id",
        "name",
        "description",
        "dir",
        "params",
        "stack_name_suffix",
        "region",
        "profile",
        "if",
        "run",
    }

    def __init__(
        self,
        manifest_data: Dict[str, Any],
        line_tracker: Optional[LineNumberTracker] = None,
    ):
        """Initialize validator with manifest data."""
        self.manifest_data = manifest_data
        self.line_tracker = line_tracker
        self.stack_ids: List[str] = []
        self.errors: List[ValidationError] = []

    @classmethod
    def from_yaml_content(
        cls, yaml_content: str, manifest_path: Optional[Path] = None
    ) -> "ManifestValidator":
        """Create validator from YAML content with line number tracking."""
        line_tracker = LineNumberTracker(manifest_path)
        manifest_data, line_tracker = line_tracker.parse_yaml_with_line_numbers(
            yaml_content
        )
        return cls(manifest_data, line_tracker)

    def _get_line_number(self, obj: Any) -> Optional[int]:
        """Get line number for an object if line tracker is available."""
        if self.line_tracker:
            return self.line_tracker.get_line_number(obj)
        return None

    def validate_manifest_schema(self) -> None:
        """Validate the overall manifest schema."""
        # Validate top-level fields
        self._validate_fields(
            self.manifest_data,
            self.VALID_PIPELINE_FIELDS,
            "manifest root",
            self._get_line_number(self.manifest_data),
        )

        # Validate pipeline_settings if present
        pipeline_settings = self.manifest_data.get("pipeline_settings", {})
        if pipeline_settings:
            self._validate_fields(
                pipeline_settings,
                self.VALID_PIPELINE_SETTINGS_FIELDS,
                "pipeline_settings",
                self._get_line_number(pipeline_settings),
            )

        # Validate stacks
        stacks = self.manifest_data.get("stacks", [])
        if not isinstance(stacks, list):
            line_num = self._get_line_number(stacks)
            self.errors.append(
                ValidationError("'stacks' must be a list", line_number=line_num)
            )
            return  # Can't continue validation if stacks isn't a list

        for i, stack_data in enumerate(stacks):
            if not isinstance(stack_data, dict):
                line_num = self._get_line_number(stack_data)
                self.errors.append(
                    ValidationError(
                        f"Stack at index {i} must be an object", line_number=line_num
                    )
                )
                continue  # Skip this stack if it's not a dict

            self._validate_fields(
                stack_data,
                self.VALID_STACK_FIELDS,
                f"stack at index {i}",
                self._get_line_number(stack_data),
            )

            # Collect stack IDs for later reference validation
            if "id" in stack_data:
                self.stack_ids.append(stack_data["id"])

    def validate_template_expressions(self) -> None:
        """Validate all template expressions in the manifest."""
        # Validate pipeline_settings expressions
        pipeline_settings = self.manifest_data.get("pipeline_settings", {})
        for field in ["stack_name_prefix", "stack_name_suffix"]:
            if field in pipeline_settings:
                field_value = pipeline_settings[field]
                line_num = self._get_line_number(field_value)
                self._validate_template_expressions_in_value(
                    field_value,
                    f"pipeline_settings.{field}",
                    available_stack_ids=set(),  # No stacks available at pipeline level
                    line_number=line_num,
                )

        # Validate stack expressions
        stacks = self.manifest_data.get("stacks", [])
        for i, stack_data in enumerate(stacks):
            if not isinstance(stack_data, dict):
                continue  # Skip if not a dict (error already recorded)

            stack_id = stack_data.get("id", f"stack_{i}")

            # Available stack IDs are those that come before this stack
            available_stack_ids = set(self.stack_ids[:i])

            # Validate templated fields
            for field in ["stack_name_suffix", "if", "run"]:
                if field in stack_data:
                    field_value = stack_data[field]
                    line_num = self._get_line_number(field_value)
                    self._validate_template_expressions_in_value(
                        field_value,
                        f"stack '{stack_id}' field '{field}'",
                        available_stack_ids,
                        line_number=line_num,
                    )

            # Validate params
            params = stack_data.get("params", {})
            if isinstance(params, dict):
                for param_name, param_value in params.items():
                    line_num = self._get_line_number(param_value)
                    self._validate_template_expressions_in_value(
                        param_value,
                        f"stack '{stack_id}' param '{param_name}'",
                        available_stack_ids,
                        line_number=line_num,
                    )

    def validate_and_raise_if_errors(self) -> None:
        """Run all validations and raise if any errors were found."""
        self.validate_manifest_schema()
        self.validate_template_expressions()

        if self.errors:
            error_messages = [str(error) for error in self.errors]
            error_count = len(error_messages)

            if error_count == 1:
                raise ManifestError(f"Validation error: {error_messages[0]}")
            else:
                formatted_errors = "\n".join(f"  - {msg}" for msg in error_messages)
                raise ManifestError(
                    f"Found {error_count} validation errors:\n{formatted_errors}"
                )

    def _validate_fields(
        self,
        data: Dict[str, Any],
        valid_fields: Set[str],
        context: str,
        line_number: Optional[int] = None,
    ) -> None:
        """Validate that all fields in data are in the valid_fields set."""
        for field_name in data.keys():
            if field_name not in valid_fields:
                # Provide helpful suggestions for common typos
                suggestion = self._suggest_field_name(field_name, valid_fields)
                error_msg = f"Unknown field '{field_name}'"
                if suggestion:
                    error_msg += f", did you mean '{suggestion}'?"
                self.errors.append(ValidationError(error_msg, context, line_number))

    def _suggest_field_name(
        self, invalid_field: str, valid_fields: Set[str]
    ) -> str | None:
        """Suggest a valid field name for common typos."""
        # Simple suggestions for common mistakes
        suggestions = {
            "parameterss": "params",
            "parameters": "params",
            "parameter": "params",
            "stack_id": "id",
            "directory": "dir",
            "folder": "dir",
            "condition": "if",
            "script": "run",
            "command": "run",
        }

        if invalid_field in suggestions:
            return suggestions[invalid_field]

        # Find closest match by edit distance (simple version)
        closest_match = None
        min_distance = float("inf")

        for valid_field in valid_fields:
            distance = self._levenshtein_distance(
                invalid_field.lower(), valid_field.lower()
            )
            if (
                distance < min_distance and distance <= 2
            ):  # Only suggest if close enough
                min_distance = distance
                closest_match = valid_field

        return closest_match

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings."""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def _validate_template_expressions_in_value(
        self,
        value: Any,
        context: str,
        available_stack_ids: Set[str],
        line_number: Optional[int] = None,
    ) -> None:
        """Validate template expressions in a single value."""
        if not isinstance(value, str):
            return  # Only validate string values

        # Find all template expressions
        pattern = r"\$\{\{\s*([^}]+)\s*\}\}"
        matches = re.finditer(pattern, value)

        for match in matches:
            expression_body = match.group(1).strip()
            self._validate_single_expression(
                expression_body, context, available_stack_ids, line_number
            )

    def _validate_single_expression(
        self,
        expression_body: str,
        context: str,
        available_stack_ids: Set[str],
        line_number: Optional[int] = None,
    ) -> None:
        """Validate a single template expression body."""
        # Split by || for fallback expressions
        parts = re.split(
            r"\|\|(?=(?:[^\'\"]|\"[^\"]*\"|\'[^\']*\')*$)", expression_body
        )

        for part_str in parts:
            part_trimmed = part_str.strip()
            self._validate_expression_part(
                part_trimmed, context, available_stack_ids, line_number
            )

    def _validate_expression_part(
        self,
        part_expression: str,
        context: str,
        available_stack_ids: Set[str],
        line_number: Optional[int] = None,
    ) -> None:
        """Validate a single part of an expression."""
        # Skip empty parts
        if not part_expression:
            return

        # Handle literals (quoted strings) - always valid
        if (part_expression.startswith("'") and part_expression.endswith("'")) or (
            part_expression.startswith('"') and part_expression.endswith('"')
        ):
            return

        # Handle environment variables - always valid (we don't check if env var exists)
        if part_expression.startswith("env."):
            var_name = part_expression[4:]
            if not var_name:
                self.errors.append(
                    ValidationError(
                        "Empty environment variable name", context, line_number
                    )
                )
            return

        # Handle stack outputs
        if part_expression.startswith("stacks."):
            self._validate_stack_output_expression(
                part_expression, context, available_stack_ids, line_number
            )
            return

        # Handle the old incorrect syntax
        if part_expression.startswith("stack."):
            error_msg = (
                f"Invalid expression '{part_expression}'. "
                f"Did you mean 'stacks.{part_expression[6:]}'? (note: 'stacks' is plural)"
            )
            self.errors.append(ValidationError(error_msg, context, line_number))
            return

        # Unknown expression type
        error_msg = (
            f"Invalid expression '{part_expression}'. "
            f"Expected: env.VARIABLE_NAME, stacks.stack_id.outputs.output_name, or 'literal'"
        )
        self.errors.append(ValidationError(error_msg, context, line_number))

    def _validate_stack_output_expression(
        self,
        expression: str,
        context: str,
        available_stack_ids: Set[str],
        line_number: Optional[int] = None,
    ) -> None:
        """Validate a stack output expression."""
        parts = expression.split(".")

        if len(parts) != 4 or parts[0] != "stacks" or parts[2] != "outputs":
            error_msg = (
                f"Invalid stack output expression '{expression}'. "
                f"Expected format: stacks.stack_id.outputs.output_name"
            )
            self.errors.append(ValidationError(error_msg, context, line_number))
            return

        stack_id = parts[1]
        output_name = parts[3]

        # Validate stack_id exists and is available
        if not stack_id:
            self.errors.append(
                ValidationError(
                    f"Empty stack ID in expression '{expression}'", context, line_number
                )
            )
            return

        if stack_id not in available_stack_ids:
            if stack_id in self.stack_ids:
                # Stack exists but comes later in the pipeline
                stack_index = self.stack_ids.index(stack_id)
                error_msg = (
                    f"Stack '{stack_id}' is defined later in the pipeline "
                    f"(at index {stack_index}). Stack outputs can only reference stacks defined earlier."
                )
                self.errors.append(ValidationError(error_msg, context, line_number))
            else:
                # Stack doesn't exist at all
                available_list = (
                    sorted(available_stack_ids) if available_stack_ids else "none"
                )
                error_msg = (
                    f"Stack '{stack_id}' does not exist in the pipeline. "
                    f"Available stacks: {available_list}"
                )
                self.errors.append(ValidationError(error_msg, context, line_number))

        # Validate output_name is not empty
        if not output_name:
            self.errors.append(
                ValidationError(
                    f"Empty output name in expression '{expression}'",
                    context,
                    line_number,
                )
            )
