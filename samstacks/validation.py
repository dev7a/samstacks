"""
Validation utilities for samstacks manifests and template expressions.
"""

import re
from typing import Any, Dict, List, Set, Optional
from pathlib import Path

import yaml

from .exceptions import ManifestError
from .pipeline_models import (
    PipelineManifestModel,
)  # Import Pydantic models


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
        # Track all types of nodes, not just containers
        self.node_lines[id(node)] = line_number

    def get_line_number(self, obj: Any) -> Optional[int]:
        """Get the line number for an object."""
        # This will be less effective with Pydantic models as new objects are created.
        # We might need to pass specific raw data snippets or values to this if trying to get line numbers
        # for semantic errors related to parts of a Pydantic-validated structure.
        # The line_tracker is primarily for errors found during the initial parse OR if we map Pydantic error paths back to raw data.
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
            if hasattr(node, "start_mark") and node.start_mark:
                self.track_node(result, node.start_mark.line + 1)
            for key_node, value_node in node.value:
                key = loader.construct_object(key_node)
                value = loader.construct_object(value_node)
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
            if not isinstance(data, dict):
                # This check ensures the root of the YAML is a mapping, which Pydantic also expects.
                raise ManifestError(
                    "Manifest content must be a YAML mapping (dictionary) at the root."
                )
            return data, self
        except yaml.YAMLError as e:
            raise ManifestError(f"Failed to parse YAML: {e}")


class ManifestValidator:
    """Validates samstacks manifest structure and template expressions, post-Pydantic parsing."""

    def __init__(
        self,
        pipeline_model: PipelineManifestModel,  # Now takes the Pydantic model
        line_tracker: Optional[
            LineNumberTracker
        ] = None,  # Still useful for template expression errors
        manifest_base_dir: Optional[
            Path
        ] = None,  # For resolving stack.dir if not already absolute
    ):
        """Initialize validator with the parsed Pydantic pipeline model."""
        self.pipeline_model = pipeline_model
        self.line_tracker = line_tracker
        self.manifest_base_dir = (
            manifest_base_dir if manifest_base_dir else Path(".").resolve()
        )
        self.errors: List[ValidationError] = []
        # stack_ids are now easily accessible from self.pipeline_model.stacks
        # and uniqueness is checked by Pydantic validator on PipelineManifestModel.

    # Removed from_yaml_content as parsing and Pydantic validation now happens in core.Pipeline.from_file

    def _get_line_number_for_value(
        self, value_object: Any, context_object: Any
    ) -> Optional[int]:
        """Attempt to get line number for a specific value if line tracker is available.
        Context object is the Pydantic model or dict containing the value.
        This is a heuristic because Pydantic creates new objects.
        It's most reliable if 'value_object' itself was part of the raw parse tree tracked.
        """
        if self.line_tracker:
            # Try direct lookup of the value object itself
            line = self.line_tracker.get_line_number(value_object)
            if line is not None:
                return line
            # Fallback: try line of the containing Pydantic model/dict if value is simple type.
            # This is less precise for specific expressions within a string.
            if isinstance(value_object, (str, int, float, bool)):
                return self.line_tracker.get_line_number(context_object)
        return None

    # Removed validate_manifest_schema and its helpers (_validate_fields, _suggest_field_name, _levenshtein_distance)
    # This is now handled by Pydantic models.

    def validate_semantic_rules_and_raise_if_errors(self) -> None:
        """Run all semantic validations and raise if any errors were found."""
        self.errors = []  # Reset errors for this validation run

        self._validate_stack_directories_and_templates()
        self._validate_pipeline_input_definitions()  # Focus on what Pydantic doesn't cover for inputs
        self.validate_template_expressions()  # Major remaining responsibility

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

    def _validate_stack_directories_and_templates(self) -> None:
        """Validate that stack directories exist and contain a SAM template."""
        if not self.pipeline_model.stacks:
            # Pydantic might allow empty stacks list if default_factory is used and no stacks provided.
            # Depending on requirements, could add a check here or via Pydantic validator.
            # For now, if no stacks, this validation passes.
            return

        for stack_model in self.pipeline_model.stacks:
            # stack_model.dir is already a Path object from Pydantic.
            # It needs to be resolved relative to manifest_base_dir.
            resolved_stack_dir = (self.manifest_base_dir / stack_model.dir).resolve()

            if not resolved_stack_dir.exists():
                # Try to get line number of the stack_model.dir field if possible
                # This is tricky as stack_model.dir is a Path object, not the raw string from YAML
                # We might need to pass the raw stack_data dict to line_tracker if we need this precision.
                # For now, associate error with the stack id.
                self.errors.append(
                    ValidationError(
                        f"Stack directory does not exist: {resolved_stack_dir}",
                        context=f"stack '{stack_model.id}' field 'dir'",
                    )
                )
                continue  # Don't check for template if dir doesn't exist

            if not resolved_stack_dir.is_dir():
                self.errors.append(
                    ValidationError(
                        f"Stack path is not a directory: {resolved_stack_dir}",
                        context=f"stack '{stack_model.id}' field 'dir'",
                    )
                )
                continue

            template_file_yaml = resolved_stack_dir / "template.yaml"
            template_file_yml = resolved_stack_dir / "template.yml"
            if not template_file_yaml.exists() and not template_file_yml.exists():
                self.errors.append(
                    ValidationError(
                        f"No template.yaml or template.yml found in {resolved_stack_dir}",
                        context=f"stack '{stack_model.id}'",
                    )
                )

    def _validate_pipeline_input_definitions(self) -> None:
        """Validate aspects of pipeline inputs not covered by Pydantic type checks.
        (e.g., complex rules for templated defaults if any)."""
        # Pydantic's PipelineInputItem and its field_validator for 'type' handle most schema aspects.
        # This method is a placeholder if more complex semantic validation for inputs is needed.
        # For example, if default values could be templates that need specific validation.
        # The current logic in Pipeline.__init__ for processing templated defaults and then
        # coercing them might live there or parts of its validation logic could move here.

        # For now, assume Pydantic models + core.Pipeline.__init__ default processing handles input validation.
        pass  # No specific extra validation for now beyond Pydantic models.

    def validate_template_expressions(self) -> None:
        """Validate all template expressions in the manifest using Pydantic models."""
        pipeline_settings = self.pipeline_model.pipeline_settings
        available_input_ids = (
            set(pipeline_settings.inputs.keys()) if pipeline_settings.inputs else set()
        )

        # Validate pipeline_settings expressions
        for field_name in ["stack_name_prefix", "stack_name_suffix"]:
            field_value = getattr(pipeline_settings, field_name, None)
            if field_value is not None:
                # Line number for expressions in pipeline_settings is harder to get accurately
                # without deeper integration with Pydantic error context or raw data mapping.
                # We can associate it with the pipeline_settings object itself for now.
                self._validate_template_expressions_in_value(
                    field_value,
                    f"pipeline_settings.{field_name}",
                    available_stack_ids=set(),  # No stacks available at pipeline_settings level
                    available_input_ids=available_input_ids,
                    context_object=pipeline_settings,  # Pass the Pydantic model for context
                    original_value_for_line_tracking=str(
                        field_value
                    ),  # Pass original string for line tracking if possible
                )

        # Validate stack expressions
        # Get all stack IDs first for forward reference checks
        all_stack_ids = [s.id for s in self.pipeline_model.stacks]

        for i, stack_model in enumerate(self.pipeline_model.stacks):
            pre_deploy_available_stack_ids = set(all_stack_ids[:i])
            run_script_available_stack_ids = set(all_stack_ids[: i + 1])

            # Validate templated fields used BEFORE or DURING stack deployment
            for field_name in ["stack_name_suffix", "if_condition"]:
                field_value = getattr(stack_model, field_name, None)
                if field_value is not None:
                    self._validate_template_expressions_in_value(
                        field_value,
                        f"stack '{stack_model.id}' field '{field_name if field_name != 'if_condition' else 'if'}'",
                        pre_deploy_available_stack_ids,
                        available_input_ids,
                        context_object=stack_model,
                        original_value_for_line_tracking=str(field_value),
                    )

            # Validate 'run_script' (used AFTER stack deployment)
            if stack_model.run_script is not None:
                self._validate_template_expressions_in_value(
                    stack_model.run_script,
                    f"stack '{stack_model.id}' field 'run'",
                    run_script_available_stack_ids,
                    available_input_ids,
                    context_object=stack_model,
                    original_value_for_line_tracking=stack_model.run_script,
                )

            # Validate params (used DURING stack deployment)
            if stack_model.params:
                for param_name, param_value in stack_model.params.items():
                    self._validate_template_expressions_in_value(
                        param_value,
                        f"stack '{stack_model.id}' param '{param_name}'",
                        pre_deploy_available_stack_ids,
                        available_input_ids,
                        context_object=stack_model.params,  # Context is the params dict
                        original_value_for_line_tracking=str(param_value),
                    )

    def _is_string_template(self, value: Any) -> bool:
        """Check if a value is a string containing one or more template patterns '${{...}}'."""
        if not isinstance(value, str):
            return False
        # Use shared template pattern - check for presence, not if entire string is a template
        return bool(re.search(r"\$\{\{\s*([^}]+)\s*\}\}", value))

    def _validate_template_expressions_in_value(
        self,
        value: Any,
        context_str: str,  # Renamed from 'context' to avoid clash with kwarg
        available_stack_ids: Set[str],
        available_input_ids: Set[str],
        context_object: Any,  # The Pydantic model or dict holding this value
        original_value_for_line_tracking: Optional[
            str
        ] = None,  # Pass the original string value if available
    ) -> None:
        """Validate template expressions in a single value."""
        if not isinstance(value, str):
            return

        # Find all template expressions
        pattern = r"\$\{\{\s*([^}]+)\s*\}\}"
        matches = re.finditer(pattern, value)
        # Try to get a general line number for the whole string value containing the expression(s)
        # This is an approximation. LineNumberTracker is best with raw YAML nodes.
        line_num_for_value = self._get_line_number_for_value(
            original_value_for_line_tracking or value, context_object
        )

        for match in matches:
            expression_body = match.group(1).strip()
            # TODO: Try to get more precise line numbers for individual expressions if possible,
            # e.g. by searching for expression_body in original_value_for_line_tracking
            # and calculating offset if line_num_for_value is known.
            self._validate_single_expression(
                expression_body,
                context_str,  # Use the passed context string
                available_stack_ids,
                available_input_ids,
                line_num_for_value,  # Use the general line number for the containing string
            )

    def _validate_single_expression(
        self,
        expression_body: str,
        context_str: str,  # Renamed
        available_stack_ids: Set[str],
        available_input_ids: Set[str],
        line_number: Optional[int] = None,
    ) -> None:
        """Validate a single template expression body."""
        parts = re.split(
            r"\|\|(?=(?:[^\'\"]|\"[^\"]*\"|\'[^\']*\')*$)", expression_body
        )
        for part_str in parts:
            part_trimmed = part_str.strip()
            self._validate_expression_part(
                part_trimmed,
                context_str,  # Use the passed context string
                available_stack_ids,
                available_input_ids,
                line_number,
            )

    def _validate_expression_part(
        self,
        part_expression: str,
        context_str: str,  # Renamed
        available_stack_ids: Set[str],
        available_input_ids: Set[str],
        line_number: Optional[int] = None,
    ) -> None:
        """Validate a single part of an expression using simple pattern validation."""
        if not part_expression:
            return

        # Handle quoted literals - these are always valid
        if (part_expression.startswith("'") and part_expression.endswith("'")) or (
            part_expression.startswith('"') and part_expression.endswith('"')
        ):
            return

        # Use basic pattern validation instead of simpleeval
        self._validate_expression_part_basic(
            part_expression,
            context_str,
            available_stack_ids,
            available_input_ids,
            line_number,
        )

    def _validate_expression_part_basic(
        self,
        part_expression: str,
        context_str: str,
        available_stack_ids: Set[str],
        available_input_ids: Set[str],
        line_number: Optional[int] = None,
    ) -> None:
        """Basic validation without simpleeval - focus on placeholder syntax."""

        # Check for expressions containing operators/math first (before simple placeholders)
        if self._contains_operators_or_math(part_expression):
            # Check for potential env variable math warnings
            self._check_for_env_math_warning(part_expression, context_str, line_number)
            return

        # Now check for simple placeholder patterns
        if part_expression.startswith("env."):
            env_var_name = part_expression[4:]
            if not env_var_name:
                self.errors.append(
                    ValidationError(
                        "Empty environment variable name", context_str, line_number
                    )
                )
            return

        if part_expression.startswith("inputs."):
            self._validate_pipeline_input_expression(
                part_expression,
                context_str,
                available_input_ids,
                line_number,
                all_stack_ids=[s.id for s in self.pipeline_model.stacks],
            )
            return

        if part_expression.startswith("stacks."):
            self._validate_stack_output_expression(
                part_expression,
                context_str,
                available_stack_ids,
                line_number,
                all_stack_ids=[s.id for s in self.pipeline_model.stacks],
            )
            return

        if part_expression.startswith("stack."):
            error_msg = (
                f"Invalid expression '{part_expression}'. "
                f"Did you mean 'stacks.{part_expression[6:]}'? (note: 'stacks' is plural)"
            )
            self.errors.append(ValidationError(error_msg, context_str, line_number))
            return

        # Check for pipeline context access
        if part_expression.startswith("pipeline."):
            valid_pipeline_attrs = {"name", "description"}
            attr_name = part_expression[len("pipeline.") :]
            if not attr_name:
                self.errors.append(
                    ValidationError(
                        "Empty pipeline attribute name", context_str, line_number
                    )
                )
            elif attr_name not in valid_pipeline_attrs:
                self.errors.append(
                    ValidationError(
                        f"Invalid pipeline attribute '{attr_name}'. Valid attributes: {valid_pipeline_attrs}",
                        context_str,
                        line_number,
                    )
                )
            return

        # For other simple expressions, check if they might be typos
        if "." in part_expression:
            # Looks like it might be a placeholder attempt
            prefix = part_expression.split(".")[0]
            if prefix not in ["env", "inputs", "stacks", "pipeline"]:
                error_msg = f"Unrecognized expression '{part_expression}'. Expected patterns: env.VAR, inputs.NAME, stacks.ID.outputs.NAME, pipeline.ATTR"
                self.errors.append(ValidationError(error_msg, context_str, line_number))

    def _contains_operators_or_math(self, expression: str) -> bool:
        """Check if expression contains operators or math that should be accepted."""

        # Look for mathematical operators, comparisons, boolean logic, numbers
        operator_patterns = [
            r"[+\-*/]",  # Math operators
            r"[<>=!]=?",  # Comparison operators
            r"\b(?:and|or|not|&&|\|\||!)\b",  # Boolean operators
            r"[()]",  # Parentheses
            r"\b\d+\b",  # Numbers
        ]

        for pattern in operator_patterns:
            if re.search(pattern, expression):
                return True

        return False

    def _check_for_env_math_warning(
        self, expression: str, context_str: str, line_number: Optional[int] = None
    ) -> None:
        """Check if expression uses env variables in mathematical context and warn about explicit conversion."""

        # Look for env.VAR in expressions that contain math operators
        if re.search(r"env\.\w+", expression) and re.search(r"[+\-*/]", expression):
            # Check if the env var looks like it could be numeric
            env_matches = re.findall(r"env\.(\w+)", expression)
            for env_var in env_matches:
                # This is a heuristic - we can't check the actual value during validation
                # but we can suggest the pattern
                import os

                env_value = os.environ.get(env_var, "")
                if env_value and self._looks_like_number(env_value):
                    suggestion = expression.replace(
                        f"env.{env_var}", f"int(env.{env_var})"
                    )
                    warning_msg = (
                        f"Environment variable '{env_var}' contains '{env_value}' which looks numeric. "
                        f"For mathematical operations, consider using explicit conversion: '{suggestion}'"
                    )
                    # We could add this as a warning rather than an error
                    # For now, let's make it a validation error to help users
                    self.errors.append(
                        ValidationError(
                            f"Suggestion: {warning_msg}", context_str, line_number
                        )
                    )

    def _looks_like_number(self, value: str) -> bool:
        """Check if a string value looks like it could be a number."""
        try:
            float(value)
            return True
        except ValueError:
            return False

    def _validate_stack_output_expression(
        self,
        expression: str,
        context_str: str,  # Renamed
        available_stack_ids: Set[str],
        line_number: Optional[int] = None,
        all_stack_ids: Optional[List[str]] = None,  # Now passed in
    ) -> None:
        """Validate a stack output expression."""
        all_stack_ids = (
            all_stack_ids
            if all_stack_ids is not None
            else [s.id for s in self.pipeline_model.stacks]
        )
        parts = expression.split(".")
        if len(parts) != 4 or parts[0] != "stacks" or parts[2] != "outputs":
            error_msg = (
                f"Invalid stack output expression '{expression}'. "
                f"Expected format: stacks.stack_id.outputs.output_name"
            )
            self.errors.append(ValidationError(error_msg, context_str, line_number))
            return

        stack_id = parts[1]
        output_name = parts[3]
        if not stack_id:
            self.errors.append(
                ValidationError(
                    f"Empty stack ID in expression '{expression}'",
                    context_str,
                    line_number,
                )
            )
            return
        if stack_id not in available_stack_ids:
            if stack_id in all_stack_ids:
                stack_index = all_stack_ids.index(stack_id)
                error_msg = (
                    f"Stack '{stack_id}' is defined later in the pipeline "
                    f"(at index {stack_index}). Stack outputs can only reference stacks defined earlier."
                )
            else:
                # Show all stacks in the pipeline, not just available ones
                available_list = sorted(all_stack_ids) if all_stack_ids else "none"
                error_msg = (
                    f"Stack '{stack_id}' does not exist in the pipeline. "
                    f"Available stacks: {available_list}"
                )
            self.errors.append(ValidationError(error_msg, context_str, line_number))
        if not output_name:
            self.errors.append(
                ValidationError(
                    f"Empty output name in expression '{expression}'",
                    context_str,
                    line_number,
                )
            )

    def _validate_pipeline_input_expression(
        self,
        expression: str,
        context_str: str,  # Renamed
        available_input_ids: Set[str],
        line_number: Optional[int] = None,
        # Added all_stack_ids to maintain signature consistency, though not used here
        all_stack_ids: Optional[List[str]] = None,
    ) -> None:
        """Validate a pipeline input expression: inputs.input_name."""
        input_name = expression[len("inputs.") :]
        if not input_name:
            self.errors.append(
                ValidationError(
                    f"Empty input name in expression '{expression}'",
                    context_str,
                    line_number,
                )
            )
            return
        if input_name not in available_input_ids:
            available_list_str = (
                ", ".join(sorted(available_input_ids))
                if available_input_ids
                else "none defined"
            )
            self.errors.append(
                ValidationError(
                    f"Input '{input_name}' is not defined in pipeline_settings.inputs. "
                    f"Available inputs: {available_list_str}",
                    context_str,
                    line_number,
                )
            )

    # Removed _validate_pipeline_inputs and _validate_default_field as Pydantic models now handle this type of validation.
