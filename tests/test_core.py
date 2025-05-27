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
            match=r"Cli for input 'count' must be a number. Received: 'not-a-number'",
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
            ManifestError,
            match=r"Cli for input 'enabled' must be a boolean. Received: 'maybe'",
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

    def test_unknown_cli_input_keys_rejected(self):
        """Test that CLI inputs not defined in pipeline_settings.inputs are rejected."""
        manifest_data = {
            **MINIMAL_MANIFEST_DATA,
            "pipeline_settings": {"inputs": {"valid_input": {"type": "string"}}},
        }
        # Provide both valid and invalid CLI inputs
        cli_inputs = {
            "valid_input": "correct",
            "typo_input": "oops",  # Not defined in manifest
            "another_unknown": "also_wrong",  # Also not defined
        }
        with pytest.raises(
            ManifestError,
            match="Unknown CLI input keys provided: another_unknown, typo_input",
        ):
            pipeline = Pipeline.from_dict(manifest_data, cli_inputs=cli_inputs)
            pipeline.validate()

    def test_no_inputs_defined_but_cli_inputs_provided(self):
        """Test that CLI inputs are rejected when no inputs are defined in manifest."""
        manifest_data = {
            **MINIMAL_MANIFEST_DATA,
            "pipeline_settings": {},  # No inputs defined
        }
        cli_inputs = {"unexpected_input": "value"}
        with pytest.raises(
            ManifestError,
            match="Unknown CLI input keys provided: unexpected_input",
        ):
            pipeline = Pipeline.from_dict(manifest_data, cli_inputs=cli_inputs)
            pipeline.validate()

    # --- Tests for Templated Default Values ---
    def test_templated_default_env_var_exists(self, monkeypatch):
        """Test that a templated default resolves from an existing environment variable."""
        monkeypatch.setenv("TEST_VAR_EXISTS", "env_value_for_default")
        manifest_data = {
            **MINIMAL_MANIFEST_DATA,
            "pipeline_settings": {
                "inputs": {
                    "my_input": {
                        "type": "string",
                        "default": "${{ env.TEST_VAR_EXISTS || 'fallback_literal' }}",
                    }
                }
            },
        }
        pipeline = Pipeline.from_dict(
            manifest_data
        )  # Initialization processes defaults
        assert pipeline.defined_inputs["my_input"]["default"] == "env_value_for_default"

    def test_templated_default_env_var_missing_uses_fallback(self, monkeypatch):
        """Test that a templated default uses fallback when env var is missing."""
        monkeypatch.delenv("TEST_VAR_MISSING_FOR_FALLBACK", raising=False)
        manifest_data = {
            **MINIMAL_MANIFEST_DATA,
            "pipeline_settings": {
                "inputs": {
                    "my_input": {
                        "type": "string",
                        "default": "${{ env.TEST_VAR_MISSING_FOR_FALLBACK || 'actual_fallback' }}",
                    }
                }
            },
        }
        pipeline = Pipeline.from_dict(manifest_data)
        assert pipeline.defined_inputs["my_input"]["default"] == "actual_fallback"

    @pytest.mark.parametrize(
        "env_value, expected_coerced_value",
        [
            ("456", 456),
            ("7.89", 7.89),
            (None, 123),
        ],  # None means env var not set, use literal fallback
    )
    def test_templated_default_resolves_to_correct_type_number(
        self, monkeypatch, env_value, expected_coerced_value
    ):
        """Test templated default for 'number' type resolves and coerces correctly."""
        input_name = "num_input"
        env_var_name = "TEST_DEFAULT_NUM"
        if env_value is not None:
            monkeypatch.setenv(env_var_name, str(env_value))
        else:
            monkeypatch.delenv(env_var_name, raising=False)

        manifest_data = {
            **MINIMAL_MANIFEST_DATA,
            "pipeline_settings": {
                "inputs": {
                    input_name: {
                        "type": "number",
                        "default": f"${{{{ env.{env_var_name} || '123' }}}}",  # Default fallback literal is '123'
                    }
                }
            },
        }
        pipeline = Pipeline.from_dict(manifest_data)
        assert pipeline.defined_inputs[input_name]["default"] == expected_coerced_value
        assert isinstance(pipeline.defined_inputs[input_name]["default"], (int, float))

    @pytest.mark.parametrize(
        "env_value, expected_coerced_value",
        [
            ("false", False),
            ("on", True),
            (None, True),
        ],  # None means env var not set, use literal fallback 'true'
    )
    def test_templated_default_resolves_to_correct_type_boolean(
        self, monkeypatch, env_value, expected_coerced_value
    ):
        """Test templated default for 'boolean' type resolves and coerces correctly."""
        input_name = "bool_input"
        env_var_name = "TEST_DEFAULT_BOOL"
        if env_value is not None:
            monkeypatch.setenv(env_var_name, str(env_value))
        else:
            monkeypatch.delenv(env_var_name, raising=False)

        manifest_data = {
            **MINIMAL_MANIFEST_DATA,
            "pipeline_settings": {
                "inputs": {
                    input_name: {
                        "type": "boolean",
                        "default": f"${{{{ env.{env_var_name} || 'true' }}}}",  # Default fallback literal is 'true'
                    }
                }
            },
        }
        pipeline = Pipeline.from_dict(manifest_data)
        assert pipeline.defined_inputs[input_name]["default"] == expected_coerced_value
        assert isinstance(pipeline.defined_inputs[input_name]["default"], bool)

    def test_templated_default_type_mismatch_number(self, monkeypatch):
        """Test ManifestError for templated default resolving to non-number for type 'number'."""
        monkeypatch.setenv("BAD_NUM_DEFAULT", "not_a_number_string")
        manifest_data = {
            **MINIMAL_MANIFEST_DATA,
            "pipeline_settings": {
                "inputs": {
                    "bad_num_input": {
                        "type": "number",
                        "default": "${{ env.BAD_NUM_DEFAULT || '123' }}",
                    }
                }
            },
        }
        with pytest.raises(
            ManifestError,
            match=r"Default value for input 'bad_num_input'.*must be a number. Received: 'not_a_number_string'",
        ):
            Pipeline.from_dict(manifest_data)

    def test_templated_default_type_mismatch_boolean(self, monkeypatch):
        """Test ManifestError for templated default resolving to non-boolean for type 'boolean'."""
        monkeypatch.setenv("BAD_BOOL_DEFAULT", "not_a_valid_boolean_string")
        manifest_data = {
            **MINIMAL_MANIFEST_DATA,
            "pipeline_settings": {
                "inputs": {
                    "bad_bool_input": {
                        "type": "boolean",
                        "default": "${{ env.BAD_BOOL_DEFAULT || 'true' }}",
                    }
                }
            },
        }
        with pytest.raises(
            ManifestError,
            match=r"Default value for input 'bad_bool_input'.*must be a boolean. Received: 'not_a_valid_boolean_string'",
        ):
            Pipeline.from_dict(manifest_data)

    def test_templated_default_malformed_template_string(self):
        """Test ManifestError if the default template string itself is malformed."""
        manifest_data = {
            **MINIMAL_MANIFEST_DATA,
            "pipeline_settings": {
                "inputs": {
                    "malformed_default_input": {
                        "type": "string",
                        "default": "${{ env.MISSING_BRACES ",  # Malformed
                    }
                }
            },
        }
        # This error originates from TemplateProcessor.process_string -> TemplateError,
        # which Pipeline.__init__ catches and re-raises as a ManifestError.
        with pytest.raises(
            ManifestError,
            match=r"Error processing templated default for input 'malformed_default_input'.*Malformed template expression in default: \$\{\{ env.MISSING_BRACES",
        ):
            Pipeline.from_dict(manifest_data)
