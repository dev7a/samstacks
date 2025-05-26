"""
Tests for manifest validation functionality.
"""

import pytest

from samstacks.exceptions import ManifestError
from samstacks.validation import ManifestValidator


class TestManifestValidator:
    """Test the ManifestValidator class."""

    def test_valid_manifest_passes(self) -> None:
        """Test that a valid manifest passes validation."""
        manifest_data = {
            "pipeline_name": "test-pipeline",
            "pipeline_description": "A test pipeline",
            "pipeline_settings": {
                "stack_name_prefix": "dev-",
                "default_region": "us-east-1",
            },
            "stacks": [
                {"id": "stack1", "dir": "stack1/", "params": {"Param1": "value1"}},
                {
                    "id": "stack2",
                    "dir": "stack2/",
                    "params": {"Param2": "${{ stacks.stack1.outputs.Output1 }}"},
                },
            ],
        }

        validator = ManifestValidator(manifest_data)
        # Should not raise any exceptions
        validator.validate_and_raise_if_errors()

    def test_unknown_field_in_root(self) -> None:
        """Test that unknown fields in root are caught."""
        manifest_data = {
            "pipeline_name": "test",
            "unknown_field": "value",
            "stacks": [],
        }

        validator = ManifestValidator(manifest_data)
        with pytest.raises(
            ManifestError, match="manifest root: Unknown field 'unknown_field'"
        ):
            validator.validate_and_raise_if_errors()

    def test_parameterss_typo_suggestion(self) -> None:
        """Test that 'parameterss' typo suggests 'params'."""
        manifest_data = {
            "pipeline_name": "test",
            "stacks": [
                {
                    "id": "stack1",
                    "dir": "stack1/",
                    "parameterss": {  # Typo: should be 'params'
                        "Param1": "value1"
                    },
                }
            ],
        }

        validator = ManifestValidator(manifest_data)
        with pytest.raises(
            ManifestError,
            match="stack at index 0: Unknown field 'parameterss', did you mean 'params'?",
        ):
            validator.validate_and_raise_if_errors()

    def test_parameters_typo_suggestion(self) -> None:
        """Test that 'parameters' typo suggests 'params'."""
        manifest_data = {
            "pipeline_name": "test",
            "stacks": [
                {
                    "id": "stack1",
                    "dir": "stack1/",
                    "parameters": {  # Typo: should be 'params'
                        "Param1": "value1"
                    },
                }
            ],
        }

        validator = ManifestValidator(manifest_data)
        with pytest.raises(
            ManifestError,
            match="stack at index 0: Unknown field 'parameters', did you mean 'params'?",
        ):
            validator.validate_and_raise_if_errors()

    def test_stack_singular_expression_error(self) -> None:
        """Test that 'stack.id' (singular) gives helpful error."""
        manifest_data = {
            "pipeline_name": "test",
            "stacks": [
                {"id": "stack1", "dir": "stack1/"},
                {
                    "id": "stack2",
                    "dir": "stack2/",
                    "params": {
                        "Param1": "${{ stack.stack1.outputs.Output1 }}"  # Wrong: should be 'stacks'
                    },
                },
            ],
        }

        validator = ManifestValidator(manifest_data)
        with pytest.raises(
            ManifestError,
            match="stack 'stack2' param 'Param1': Invalid expression 'stack.stack1.outputs.Output1'.*Did you mean 'stacks.stack1.outputs.Output1'.*'stacks' is plural",
        ):
            validator.validate_and_raise_if_errors()

    def test_nonexistent_stack_reference(self) -> None:
        """Test that referencing a nonexistent stack fails."""
        manifest_data = {
            "pipeline_name": "test",
            "stacks": [
                {
                    "id": "stack1",
                    "dir": "stack1/",
                    "params": {"Param1": "${{ stacks.nonexistent.outputs.Output1 }}"},
                }
            ],
        }

        validator = ManifestValidator(manifest_data)
        with pytest.raises(
            ManifestError,
            match="stack 'stack1' param 'Param1': Stack 'nonexistent' does not exist in the pipeline",
        ):
            validator.validate_and_raise_if_errors()

    def test_forward_reference_error(self) -> None:
        """Test that referencing a stack defined later fails."""
        manifest_data = {
            "pipeline_name": "test",
            "stacks": [
                {
                    "id": "stack1",
                    "dir": "stack1/",
                    "params": {
                        "Param1": "${{ stacks.stack2.outputs.Output1 }}"  # stack2 comes later
                    },
                },
                {"id": "stack2", "dir": "stack2/"},
            ],
        }

        validator = ManifestValidator(manifest_data)
        with pytest.raises(
            ManifestError,
            match="stack 'stack1' param 'Param1': Stack 'stack2' is defined later in the pipeline.*at index 1.*Stack outputs can only reference stacks defined earlier",
        ):
            validator.validate_and_raise_if_errors()

    def test_valid_env_expressions(self) -> None:
        """Test that environment variable expressions are valid."""
        manifest_data = {
            "pipeline_name": "test",
            "stacks": [
                {
                    "id": "stack1",
                    "dir": "stack1/",
                    "params": {
                        "Param1": "${{ env.MY_VAR }}",
                        "Param2": "${{ env.ANOTHER_VAR || 'default' }}",
                    },
                    "if": "${{ env.DEPLOY_STACK1 || 'true' }}",
                }
            ],
        }

        validator = ManifestValidator(manifest_data)
        validator.validate_and_raise_if_errors()  # Should not raise

    def test_valid_stack_reference(self) -> None:
        """Test that valid stack references work."""
        manifest_data = {
            "pipeline_name": "test",
            "stacks": [
                {"id": "stack1", "dir": "stack1/"},
                {
                    "id": "stack2",
                    "dir": "stack2/",
                    "params": {"Param1": "${{ stacks.stack1.outputs.Output1 }}"},
                },
            ],
        }

        validator = ManifestValidator(manifest_data)
        validator.validate_and_raise_if_errors()  # Should not raise

    def test_malformed_stack_expression(self) -> None:
        """Test that malformed stack expressions fail."""
        manifest_data = {
            "pipeline_name": "test",
            "stacks": [
                {
                    "id": "stack1",
                    "dir": "stack1/",
                    "params": {
                        "Param1": "${{ stacks.stack1.wrong.Output1 }}"  # Should be 'outputs'
                    },
                }
            ],
        }

        validator = ManifestValidator(manifest_data)
        with pytest.raises(
            ManifestError,
            match="stack 'stack1' param 'Param1': Invalid stack output expression.*Expected format: stacks.stack_id.outputs.output_name",
        ):
            validator.validate_and_raise_if_errors()

    def test_empty_stack_id_in_expression(self) -> None:
        """Test that empty stack ID fails."""
        manifest_data = {
            "pipeline_name": "test",
            "stacks": [
                {
                    "id": "stack1",
                    "dir": "stack1/",
                    "params": {
                        "Param1": "${{ stacks..outputs.Output1 }}"  # Empty stack ID
                    },
                }
            ],
        }

        validator = ManifestValidator(manifest_data)
        with pytest.raises(
            ManifestError,
            match="stack 'stack1' param 'Param1': Empty stack ID in expression",
        ):
            validator.validate_and_raise_if_errors()

    def test_empty_output_name_in_expression(self) -> None:
        """Test that empty output name fails."""
        manifest_data = {
            "pipeline_name": "test",
            "stacks": [
                {"id": "stack1", "dir": "stack1/"},
                {
                    "id": "stack2",
                    "dir": "stack2/",
                    "params": {
                        "Param1": "${{ stacks.stack1.outputs. }}"  # Empty output name
                    },
                },
            ],
        }

        validator = ManifestValidator(manifest_data)
        with pytest.raises(
            ManifestError,
            match="stack 'stack2' param 'Param1': Empty output name in expression",
        ):
            validator.validate_and_raise_if_errors()

    def test_complex_fallback_expressions(self) -> None:
        """Test that complex fallback expressions work."""
        manifest_data = {
            "pipeline_name": "test",
            "stacks": [
                {"id": "stack1", "dir": "stack1/"},
                {
                    "id": "stack2",
                    "dir": "stack2/",
                    "params": {
                        "Param1": "${{ env.MY_VAR || stacks.stack1.outputs.Output1 || 'default' }}"
                    },
                },
            ],
        }

        validator = ManifestValidator(manifest_data)
        validator.validate_and_raise_if_errors()  # Should not raise

    def test_invalid_expression_type(self) -> None:
        """Test that invalid expression types fail."""
        manifest_data = {
            "pipeline_name": "test",
            "stacks": [
                {
                    "id": "stack1",
                    "dir": "stack1/",
                    "params": {"Param1": "${{ invalid.expression }}"},
                }
            ],
        }

        validator = ManifestValidator(manifest_data)
        with pytest.raises(
            ManifestError,
            match="stack 'stack1' param 'Param1': Invalid expression 'invalid.expression'.*Expected: env.VARIABLE_NAME, stacks.stack_id.outputs.output_name, or 'literal'",
        ):
            validator.validate_and_raise_if_errors()

    def test_pipeline_settings_validation(self) -> None:
        """Test that pipeline_settings fields are validated."""
        manifest_data = {
            "pipeline_name": "test",
            "pipeline_settings": {"invalid_field": "value"},
            "stacks": [],
        }

        validator = ManifestValidator(manifest_data)
        with pytest.raises(
            ManifestError, match="pipeline_settings: Unknown field 'invalid_field'"
        ):
            validator.validate_and_raise_if_errors()

    def test_template_expressions_in_pipeline_settings(self) -> None:
        """Test that template expressions in pipeline_settings are validated."""
        manifest_data = {
            "pipeline_name": "test",
            "pipeline_settings": {
                "stack_name_prefix": "${{ stacks.nonexistent.outputs.Output1 }}-"  # No stacks available at pipeline level
            },
            "stacks": [],
        }

        validator = ManifestValidator(manifest_data)
        with pytest.raises(
            ManifestError,
            match="pipeline_settings.stack_name_prefix: Stack 'nonexistent' does not exist in the pipeline",
        ):
            validator.validate_and_raise_if_errors()

    def test_multiple_errors_collected(self) -> None:
        """Test that multiple validation errors are collected and presented together."""
        manifest_data = {
            "pipeline_name": "test",
            "unknown_root_field": "value",  # Error 1: Unknown root field
            "pipeline_settings": {
                "invalid_setting": "value"  # Error 2: Unknown pipeline setting
            },
            "stacks": [
                {
                    "id": "stack1",
                    "dir": "stack1/",
                    "parameterss": {  # Error 3: Typo in field name
                        "Param1": "${{ stack.stack2.outputs.Output1 }}"  # Error 4: Wrong syntax (stack vs stacks)
                    },
                },
                {
                    "id": "stack2",
                    "dir": "stack2/",
                    "params": {
                        "Param2": "${{ stacks.nonexistent.outputs.Output1 }}"  # Error 5: Nonexistent stack
                    },
                },
            ],
        }

        validator = ManifestValidator(manifest_data)
        with pytest.raises(ManifestError) as exc_info:
            validator.validate_and_raise_if_errors()

        error_message = str(exc_info.value)

        # Should mention it found multiple errors
        assert "Found 4 validation errors:" in error_message

        # Should contain all the specific errors
        assert "Unknown field 'unknown_root_field'" in error_message
        assert "Unknown field 'invalid_setting'" in error_message
        assert "Unknown field 'parameterss', did you mean 'params'?" in error_message
        assert "Stack 'nonexistent' does not exist" in error_message

    def test_single_error_format(self) -> None:
        """Test that single errors are formatted without numbering."""
        manifest_data = {
            "pipeline_name": "test",
            "unknown_field": "value",
            "stacks": [],
        }

        validator = ManifestValidator(manifest_data)
        with pytest.raises(ManifestError) as exc_info:
            validator.validate_and_raise_if_errors()

        error_message = str(exc_info.value)

        # Should be formatted as single error, not numbered list
        assert "Validation error:" in error_message
        assert (
            "Found" not in error_message
        )  # Should not say "Found X validation errors"
        assert "manifest root: Unknown field 'unknown_field'" in error_message

    def test_line_number_tracking_from_yaml(self) -> None:
        """Test that line numbers are tracked when parsing from YAML content."""
        yaml_content = """pipeline_name: Test Pipeline
unknown_field: "this is wrong"

pipeline_settings:
  invalid_setting: "another error"

stacks:
  - id: stack1
    dir: stack1/
    parameterss: "typo here"
    params:
      Param1: "${{ stack.stack2.outputs.Output1 }}"
  - id: stack2
    dir: stack2/
"""

        validator = ManifestValidator.from_yaml_content(yaml_content)
        with pytest.raises(ManifestError) as exc_info:
            validator.validate_and_raise_if_errors()

        error_message = str(exc_info.value)

        # Should contain line numbers for schema errors
        assert (
            "(line 1)" in error_message
        )  # unknown_field (on line 2 but tracked as line 1)
        assert "(line 5)" in error_message  # invalid_setting
        assert (
            "(line 8)" in error_message
        )  # parameterss typo (on line 10 but tracked as line 8)

        # Should contain the actual errors
        assert "Unknown field 'unknown_field'" in error_message
        assert "Unknown field 'invalid_setting'" in error_message
        assert "Unknown field 'parameterss', did you mean 'params'?" in error_message
