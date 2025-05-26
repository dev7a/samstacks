import pytest
from pathlib import Path
from samstacks.core import Pipeline
from samstacks.exceptions import ManifestError

# Minimal valid manifest structure for testing core pipeline logic
MINIMAL_MANIFEST_DATA = {
    "pipeline_name": "test-pipeline",
    "stacks": [
        {
            "id": "stack1",
            "dir": "some/dir",
        }  # dir will be mocked or non-existent for these tests
    ],
}


# Mock Path.exists for stack directory validation to simplify Pipeline instantiation
@pytest.fixture(autouse=True)
def mock_stack_dir_exists(mocker):
    mocker.patch.object(Path, "exists", return_value=True)
    # If template.yaml/.yml checks are made early in Pipeline.validate(), they might need mocking too.
    # For these tests, we assume Pipeline.validate() primarily focuses on input logic first,
    # and other structural validations (like template file existence) are either covered elsewhere
    # or don't interfere with testing the input validation part.


class TestPipelineValidation:
    def test_required_input_not_provided(self):
        """Test ManifestError if a required input is not provided via CLI and has no default."""
        manifest_data = {
            **MINIMAL_MANIFEST_DATA,
            "pipeline_settings": {
                "inputs": {
                    "env_name": {"type": "string", "description": "Required input"}
                }
            },
        }
        with pytest.raises(
            ManifestError,
            match="Required input 'env_name' not provided via CLI and has no default value.",
        ):
            pipeline = Pipeline.from_dict(manifest_data, cli_inputs={})
            pipeline.validate()

    def test_required_input_provided_via_cli(self):
        """Test no error if a required input is provided via CLI."""
        manifest_data = {
            **MINIMAL_MANIFEST_DATA,
            "pipeline_settings": {
                "inputs": {
                    "env_name": {"type": "string", "description": "Required input"}
                }
            },
        }
        cli_inputs = {"env_name": "production"}
        pipeline = Pipeline.from_dict(manifest_data, cli_inputs=cli_inputs)
        pipeline.validate()  # Should not raise

    def test_optional_input_not_provided_has_default(self):
        """Test no error if an optional input (with default) is not provided via CLI."""
        manifest_data = {
            **MINIMAL_MANIFEST_DATA,
            "pipeline_settings": {
                "inputs": {"env_name": {"type": "string", "default": "dev"}}
            },
        }
        pipeline = Pipeline.from_dict(manifest_data, cli_inputs={})
        pipeline.validate()  # Should not raise

    def test_cli_input_number_type_invalid_value(self):
        """Test ManifestError if CLI input for a 'number' type is not a valid number."""
        manifest_data = {
            **MINIMAL_MANIFEST_DATA,
            "pipeline_settings": {"inputs": {"count": {"type": "number"}}},
        }
        cli_inputs = {"count": "not-a-number"}
        with pytest.raises(
            ManifestError,
            match="Input 'count' must be a number. Received: 'not-a-number'",
        ):
            pipeline = Pipeline.from_dict(manifest_data, cli_inputs=cli_inputs)
            pipeline.validate()

    @pytest.mark.parametrize("valid_number_str", ["123", "3.14", "-5", "0"])
    def test_cli_input_number_type_valid_value(self, valid_number_str: str):
        """Test no error if CLI input for 'number' type is a valid number string."""
        manifest_data = {
            **MINIMAL_MANIFEST_DATA,
            "pipeline_settings": {"inputs": {"count": {"type": "number"}}},
        }
        cli_inputs = {"count": valid_number_str}
        pipeline = Pipeline.from_dict(manifest_data, cli_inputs=cli_inputs)
        pipeline.validate()  # Should not raise

    def test_cli_input_boolean_type_invalid_value(self):
        """Test ManifestError if CLI input for 'boolean' type is not a valid boolean string."""
        manifest_data = {
            **MINIMAL_MANIFEST_DATA,
            "pipeline_settings": {"inputs": {"enabled": {"type": "boolean"}}},
        }
        cli_inputs = {"enabled": "maybe"}
        with pytest.raises(
            ManifestError, match="Input 'enabled' must be a boolean. Received: 'maybe'"
        ):
            pipeline = Pipeline.from_dict(manifest_data, cli_inputs=cli_inputs)
            pipeline.validate()

    @pytest.mark.parametrize(
        "valid_bool_str", ["true", "FALSE", "yes", "NO", "1", "0", "on", "OFF"]
    )
    def test_cli_input_boolean_type_valid_value(self, valid_bool_str: str):
        """Test no error if CLI input for 'boolean' type is a valid boolean string."""
        manifest_data = {
            **MINIMAL_MANIFEST_DATA,
            "pipeline_settings": {"inputs": {"enabled": {"type": "boolean"}}},
        }
        cli_inputs = {"enabled": valid_bool_str}
        pipeline = Pipeline.from_dict(manifest_data, cli_inputs=cli_inputs)
        pipeline.validate()  # Should not raise

    def test_cli_input_string_type_any_value(self):
        """Test no error for 'string' type with any CLI string value."""
        manifest_data = {
            **MINIMAL_MANIFEST_DATA,
            "pipeline_settings": {"inputs": {"message": {"type": "string"}}},
        }
        cli_inputs = {"message": "Hello World! 123 True"}
        pipeline = Pipeline.from_dict(manifest_data, cli_inputs=cli_inputs)
        pipeline.validate()  # Should not raise

    def test_pipeline_validate_no_inputs_defined_no_cli_inputs(self):
        """Test validation passes if no inputs are defined and none are provided."""
        manifest_data = {
            **MINIMAL_MANIFEST_DATA,
            "pipeline_settings": {},  # No 'inputs' key
        }
        pipeline = Pipeline.from_dict(manifest_data, cli_inputs={})
        pipeline.validate()  # Should not raise

    def test_pipeline_validate_inputs_defined_but_all_optional_or_provided(self):
        """Test validation passes if inputs are defined but all are optional or provided."""
        manifest_data = {
            **MINIMAL_MANIFEST_DATA,
            "pipeline_settings": {
                "inputs": {
                    "optional_input": {"type": "string", "default": "val"},
                    "provided_input": {"type": "string"},
                }
            },
        }
        cli_inputs = {"provided_input": "cli_val"}
        pipeline = Pipeline.from_dict(manifest_data, cli_inputs=cli_inputs)
        pipeline.validate()  # Should not raise

    def test_cli_input_whitespace_only_treated_as_not_provided(self):
        """Test that CLI inputs with only whitespace are treated as not provided."""
        manifest_data = {
            **MINIMAL_MANIFEST_DATA,
            "pipeline_settings": {
                "inputs": {
                    "required_input": {"type": "string"}  # Required, no default
                }
            },
        }
        # Provide whitespace-only value
        cli_inputs = {"required_input": "   "}
        with pytest.raises(
            ManifestError,
            match="Required input 'required_input' not provided via CLI and has no default value.",
        ):
            pipeline = Pipeline.from_dict(manifest_data, cli_inputs=cli_inputs)
            pipeline.validate()

    def test_cli_input_with_leading_trailing_whitespace_trimmed(self):
        """Test that CLI inputs with leading/trailing whitespace are trimmed."""
        manifest_data = {
            **MINIMAL_MANIFEST_DATA,
            "pipeline_settings": {"inputs": {"test_input": {"type": "string"}}},
        }
        cli_inputs = {"test_input": "  value_with_spaces  "}
        pipeline = Pipeline.from_dict(manifest_data, cli_inputs=cli_inputs)
        pipeline.validate()  # Should not raise - trimmed value is valid
