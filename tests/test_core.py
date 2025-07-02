import pytest
from pathlib import Path
from samstacks.core import Pipeline
from samstacks.exceptions import ManifestError
from samstacks.pipeline_models import PipelineManifestModel

# Minimal valid manifest structure for testing core pipeline logic
# Adjusted to be Pydantic-valid for PipelineManifestModel by default
MINIMAL_MANIFEST_DICT = {
    "pipeline_name": "test-pipeline",
    "stacks": [
        {
            "id": "stack1",
            "dir": "./mock_stack1_dir/",  # Path will be string for dict, Pydantic converts to Path
        }
    ],
}


# Autouse fixture to mock Path.exists and template file existence for core tests
# Focuses tests on Pipeline logic rather than filesystem or full manifest validation details
@pytest.fixture(autouse=True)
def mock_core_paths(mocker):
    # Mock stack directory and template file to always exist for these core tests
    mocker.patch.object(Path, "exists", return_value=True)
    mocker.patch.object(Path, "is_dir", return_value=True)
    # If Pipeline.validate checks for template file, this might be needed too.
    # For now, assuming these tests focus on aspects before deep file validation by ManifestValidator.


class TestPipelineInputLogic:
    """Tests focused on Pipeline's input processing and validation logic."""

    def test_required_input_not_provided(self):
        manifest_dict = {
            **MINIMAL_MANIFEST_DICT,
            "pipeline_settings": {
                "inputs": {
                    "env_name": {"type": "string", "description": "Required input"}
                }
            },
        }
        # The validation now happens during pipeline.validate(), not during from_dict
        pipeline = Pipeline.from_dict(
            manifest_dict, cli_inputs={}, manifest_base_dir=Path(".")
        )
        with pytest.raises(
            ManifestError,
            match="Required input 'env_name' not provided via CLI and has no default value.",
        ):
            pipeline.validate()

    def test_required_input_provided_via_cli(self):
        manifest_dict = {
            **MINIMAL_MANIFEST_DICT,
            "pipeline_settings": {
                "inputs": {
                    "env_name": {"type": "string", "description": "Required input"}
                }
            },
        }
        cli_inputs = {"env_name": "production"}
        pipeline = Pipeline.from_dict(
            manifest_dict, cli_inputs=cli_inputs, manifest_base_dir=Path(".")
        )
        pipeline.validate()  # Should not raise

    def test_optional_input_not_provided_has_default(self):
        manifest_dict = {
            **MINIMAL_MANIFEST_DICT,
            "pipeline_settings": {
                "inputs": {"env_name": {"type": "string", "default": "dev"}}
            },
        }
        pipeline = Pipeline.from_dict(
            manifest_dict, cli_inputs={}, manifest_base_dir=Path(".")
        )
        pipeline.validate()  # Should not raise

    def test_cli_input_number_type_invalid_value(self):
        manifest_dict = {
            **MINIMAL_MANIFEST_DICT,
            "pipeline_settings": {"inputs": {"count": {"type": "number"}}},
        }
        cli_inputs = {"count": "not-a-number"}
        pipeline = Pipeline.from_dict(
            manifest_dict, cli_inputs=cli_inputs, manifest_base_dir=Path(".")
        )
        with pytest.raises(
            ManifestError,
            match=r"CLI must be a number. Received: 'not-a-number'",
        ):
            pipeline.validate()

    @pytest.mark.parametrize("valid_number_str", ["123", "3.14", "-5", "0"])
    def test_cli_input_number_type_valid_value(self, valid_number_str: str):
        manifest_dict = {
            **MINIMAL_MANIFEST_DICT,
            "pipeline_settings": {"inputs": {"count": {"type": "number"}}},
        }
        cli_inputs = {"count": valid_number_str}
        pipeline = Pipeline.from_dict(
            manifest_dict, cli_inputs=cli_inputs, manifest_base_dir=Path(".")
        )
        pipeline.validate()

    def test_cli_input_boolean_type_invalid_value(self):
        manifest_dict = {
            **MINIMAL_MANIFEST_DICT,
            "pipeline_settings": {"inputs": {"enabled": {"type": "boolean"}}},
        }
        cli_inputs = {"enabled": "maybe"}
        pipeline = Pipeline.from_dict(
            manifest_dict, cli_inputs=cli_inputs, manifest_base_dir=Path(".")
        )
        with pytest.raises(
            ManifestError,
            match=r"CLI must be a boolean. Received: 'maybe'",
        ):
            pipeline.validate()

    @pytest.mark.parametrize(
        "valid_bool_str", ["true", "FALSE", "yes", "NO", "1", "0", "on", "OFF"]
    )
    def test_cli_input_boolean_type_valid_value(self, valid_bool_str: str):
        manifest_dict = {
            **MINIMAL_MANIFEST_DICT,
            "pipeline_settings": {"inputs": {"enabled": {"type": "boolean"}}},
        }
        cli_inputs = {"enabled": valid_bool_str}
        pipeline = Pipeline.from_dict(
            manifest_dict, cli_inputs=cli_inputs, manifest_base_dir=Path(".")
        )
        pipeline.validate()

    def test_unknown_cli_input_keys_rejected(self):
        manifest_dict = {
            **MINIMAL_MANIFEST_DICT,
            "pipeline_settings": {"inputs": {"valid_input": {"type": "string"}}},
        }
        cli_inputs = {"valid_input": "correct", "typo_input": "oops"}
        with pytest.raises(
            ManifestError, match="Unknown CLI input keys provided: typo_input"
        ):
            pipeline = Pipeline.from_dict(
                manifest_dict, cli_inputs=cli_inputs, manifest_base_dir=Path(".")
            )
            pipeline.validate()

    # --- Tests for Templated Default Values (processed in Pipeline.__init__) ---
    def test_templated_default_env_var_exists(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR_EXISTS", "env_value_for_default")
        manifest_dict = {
            **MINIMAL_MANIFEST_DICT,
            "pipeline_settings": {
                "inputs": {
                    "my_input": {
                        "type": "string",
                        "default": "${{ env.TEST_VAR_EXISTS || 'fallback_literal' }}",
                    }
                }
            },
        }
        pipeline = Pipeline.from_dict(manifest_dict, manifest_base_dir=Path("."))
        assert pipeline.defined_inputs["my_input"]["default"] == "env_value_for_default"

    def test_templated_default_type_mismatch_number(self, monkeypatch):
        monkeypatch.setenv("BAD_NUM_DEFAULT", "not_a_number_string")
        manifest_dict = {
            **MINIMAL_MANIFEST_DICT,
            "pipeline_settings": {
                "inputs": {
                    "bad_num_input": {
                        "type": "number",
                        "default": "${{ env.BAD_NUM_DEFAULT || '123' }}",  # Fallback '123' is valid if env var used
                    }
                }
            },
        }
        with pytest.raises(
            ManifestError,
            match=r"DEFAULT VALUE must be a number. Received: 'not_a_number_string'",
        ):
            Pipeline.from_dict(manifest_dict, manifest_base_dir=Path("."))

    def test_templated_default_malformed_template_string(self):
        manifest_dict = {
            **MINIMAL_MANIFEST_DICT,
            "pipeline_settings": {
                "inputs": {
                    "malformed_default_input": {
                        "type": "string",
                        "default": "${{ env.MISSING_BRACES ",
                    }
                }
            },
        }
        with pytest.raises(
            ManifestError,
            match=r"Error processing templated default for input 'malformed_default_input'.*Malformed template expression in default",
        ):
            Pipeline.from_dict(manifest_dict, manifest_base_dir=Path("."))


class TestPipelineStorageOfPydanticModelsAndSamConfig:
    """Tests that Pydantic models and SAM config fields are stored correctly."""

    def test_pydantic_model_stored_on_pipeline(self):
        manifest_dict = {
            "pipeline_name": "PipeWithPydantic",
            "pipeline_settings": {"default_region": "eu-west-1"},
            "stacks": [{"id": "s1", "dir": "./s1dir/"}],
        }
        pipeline = Pipeline.from_dict(manifest_dict, manifest_base_dir=Path("."))
        assert hasattr(pipeline, "pydantic_model")
        assert isinstance(pipeline.pydantic_model, PipelineManifestModel)
        assert pipeline.pydantic_model.pipeline_name == "PipeWithPydantic"
        assert pipeline.pydantic_model.pipeline_settings.default_region == "eu-west-1"

    def test_default_sam_config_stored(self):
        sam_config_content = {
            "version": 0.1,
            "default": {"deploy": {"parameters": {"Foo": "Bar"}}},
        }
        manifest_dict = {
            "pipeline_name": "PipeWithSamConfig",
            "pipeline_settings": {"default_sam_config": sam_config_content},
            "stacks": [{"id": "s1", "dir": "./s1dir/"}],
        }
        pipeline = Pipeline.from_dict(manifest_dict, manifest_base_dir=Path("."))
        assert (
            pipeline.pipeline_settings.get("default_sam_config") == sam_config_content
        )

    def test_stack_sam_config_overrides_stored(self):
        override_content = {"default": {"deploy": {"parameters": {"Memory": 1024}}}}
        manifest_dict = {
            "pipeline_name": "PipeWithStackOverrides",
            "stacks": [
                {
                    "id": "s1",
                    "dir": "./s1dir/",
                    "sam_config_overrides": override_content,
                }
            ],
        }
        pipeline = Pipeline.from_dict(manifest_dict, manifest_base_dir=Path("."))
        assert len(pipeline.stacks) == 1
        assert pipeline.stacks[0].sam_config_overrides == override_content

    def test_from_file_stores_pydantic_model_and_sam_configs(self, tmp_path: Path):
        manifest_content = """
pipeline_name: MyFilePipeline
pipeline_settings:
  default_sam_config:
    version: 0.1
    global:
      parameters:
        tracing: active
stacks:
  - id: file_stack
    dir: ./fstack/
    sam_config_overrides:
      default:
        deploy:
          parameters:
            ImageUri: myimageuri
"""
        manifest_file = tmp_path / "pipeline.yml"
        manifest_file.write_text(manifest_content)

        stack_dir = tmp_path / "fstack"
        stack_dir.mkdir()
        (stack_dir / "template.yaml").touch()  # For ManifestValidator semantic pass

        pipeline = Pipeline.from_file(manifest_file)

        assert hasattr(pipeline, "pydantic_model")
        assert isinstance(pipeline.pydantic_model, PipelineManifestModel)
        assert pipeline.pydantic_model.pipeline_name == "MyFilePipeline"

        expected_default_sam = {
            "version": 0.1,
            "global": {"parameters": {"tracing": "active"}},
        }
        assert (
            pipeline.pipeline_settings.get("default_sam_config") == expected_default_sam
        )

        assert len(pipeline.stacks) == 1
        expected_override = {
            "default": {"deploy": {"parameters": {"ImageUri": "myimageuri"}}}
        }
        assert pipeline.stacks[0].sam_config_overrides == expected_override


# Other existing tests like TestStackGetName can remain as they test runtime object logic.
# The fixture `mock_stack_dir_exists` might need to be more nuanced if those tests
# depend on specific dir existence checks that are now part of ManifestValidator.
# For now, keeping the broad Path.exists mock for core tests.


class TestPipelineSummary:
    """Tests for pipeline summary functionality."""

    def test_render_summary_if_present_with_valid_summary(self, mocker):
        """Test that a valid summary is properly rendered."""
        mock_ui = mocker.patch("samstacks.core.ui")

        manifest_dict = {
            **MINIMAL_MANIFEST_DICT,
            "summary": "# Deployment Complete!\n\nAll stacks are ready.",
        }

        pipeline = Pipeline.from_dict(manifest_dict, manifest_base_dir=Path("."))
        pipeline._render_summary_if_present()

        # Verify that ui.render_markdown was called with the summary content
        mock_ui.render_markdown.assert_called_once_with(
            "# Deployment Complete!\n\nAll stacks are ready.",
            title="📋 Pipeline Summary",
            rule_style="green",
            style="simple",
        )

    def test_render_summary_if_present_with_templated_summary(self, mocker):
        """Test that a templated summary is properly processed and rendered."""
        mock_ui = mocker.patch("samstacks.core.ui")

        manifest_dict = {
            **MINIMAL_MANIFEST_DICT,
            "pipeline_settings": {
                "inputs": {"environment": {"type": "string", "default": "dev"}}
            },
            "summary": "# Deployment Complete!\n\nEnvironment: ${{ inputs.environment }}",
        }

        pipeline = Pipeline.from_dict(manifest_dict, manifest_base_dir=Path("."))
        pipeline._render_summary_if_present()

        # Verify that the templated content was processed
        expected_processed_summary = "# Deployment Complete!\n\nEnvironment: dev"
        mock_ui.render_markdown.assert_called_once_with(
            expected_processed_summary,
            title="📋 Pipeline Summary",
            rule_style="green",
            style="simple",
        )

    def test_render_summary_if_present_with_no_summary(self, mocker):
        """Test that no rendering occurs when summary is None."""
        mock_ui = mocker.patch("samstacks.core.ui")

        manifest_dict = {
            **MINIMAL_MANIFEST_DICT,
            # No summary field
        }

        pipeline = Pipeline.from_dict(manifest_dict, manifest_base_dir=Path("."))
        pipeline._render_summary_if_present()

        # Verify that ui.render_markdown was not called
        mock_ui.render_markdown.assert_not_called()

    def test_render_summary_if_present_with_empty_summary(self, mocker):
        """Test that no rendering occurs when summary is empty."""
        mock_ui = mocker.patch("samstacks.core.ui")

        manifest_dict = {
            **MINIMAL_MANIFEST_DICT,
            "summary": "",
        }

        pipeline = Pipeline.from_dict(manifest_dict, manifest_base_dir=Path("."))
        pipeline._render_summary_if_present()

        # Verify that ui.render_markdown was not called for empty summary
        mock_ui.render_markdown.assert_not_called()

    def test_render_summary_if_present_with_whitespace_only_summary(self, mocker):
        """Test that no rendering occurs when summary is only whitespace."""
        mock_ui = mocker.patch("samstacks.core.ui")

        manifest_dict = {
            **MINIMAL_MANIFEST_DICT,
            "summary": "   \n  \t  \n  ",
        }

        pipeline = Pipeline.from_dict(manifest_dict, manifest_base_dir=Path("."))
        pipeline._render_summary_if_present()

        # Verify that ui.render_markdown was not called for whitespace-only summary
        mock_ui.render_markdown.assert_not_called()

    def test_render_summary_if_present_handles_template_error_gracefully(self, mocker):
        """Test that template processing errors are handled gracefully."""
        mock_ui = mocker.patch("samstacks.core.ui")

        # Use malformed template syntax to trigger an actual error
        manifest_dict = {
            **MINIMAL_MANIFEST_DICT,
            "summary": "# Deployment Complete!\n\nMalformed: ${{ inputs.bad_syntax !!!! }}}",
        }

        pipeline = Pipeline.from_dict(manifest_dict, manifest_base_dir=Path("."))
        pipeline._render_summary_if_present()

        # Verify that ui.warning was called when template processing fails
        mock_ui.warning.assert_called_once()
        warning_call = mock_ui.warning.call_args
        assert "Summary rendering failed" in warning_call[0][0]

        # Verify that ui.render_markdown was not called due to the error
        mock_ui.render_markdown.assert_not_called()

    def test_render_summary_if_present_no_pydantic_model(self, mocker):
        """Test that method handles missing pydantic_model gracefully."""
        mock_ui = mocker.patch("samstacks.core.ui")

        pipeline = Pipeline.from_dict(
            MINIMAL_MANIFEST_DICT, manifest_base_dir=Path(".")
        )
        # Simulate missing pydantic_model
        pipeline.pydantic_model = None

        pipeline._render_summary_if_present()

        # Verify that no UI methods were called
        mock_ui.render_markdown.assert_not_called()
        mock_ui.warning.assert_not_called()


class TestPipelineExternalConfigDeletion:
    """Tests for external config path resolution during deletion operations."""

    def test_resolve_external_config_path_with_valid_config(self):
        """Test that external config path resolution works for stacks with config field."""
        manifest_dict = {
            **MINIMAL_MANIFEST_DICT,
            "pipeline_settings": {
                "inputs": {"environment": {"type": "string", "default": "dev"}}
            },
            "stacks": [
                {
                    "id": "test-stack",
                    "dir": "./stack/",
                    "config": "configs/${{ inputs.environment }}/stack/",
                }
            ],
        }

        pipeline = Pipeline.from_dict(manifest_dict, manifest_base_dir=Path("."))
        stack = pipeline.stacks[0]

        # Test the helper method
        resolved_path = pipeline._resolve_external_config_path(stack)

        assert resolved_path is not None
        assert str(resolved_path).endswith("configs/dev/stack/samconfig.yaml")

    def test_resolve_external_config_path_no_external_config(self):
        """Test that resolution returns None for stacks without config field."""
        manifest_dict = {
            **MINIMAL_MANIFEST_DICT,
            "stacks": [
                {
                    "id": "local-stack",
                    "dir": "./stack/",
                    # No config field - should use local samconfig.yaml
                }
            ],
        }

        pipeline = Pipeline.from_dict(manifest_dict, manifest_base_dir=Path("."))
        stack = pipeline.stacks[0]

        # Test the helper method
        resolved_path = pipeline._resolve_external_config_path(stack)

        assert resolved_path is None

    def test_get_deployed_stack_name_external_config_exists(self, mocker):
        """Test that deployed stack name is read from external config when it exists."""
        # Mock the external config file exists and contains stack name
        mock_read_function = mocker.patch(
            "samstacks.core._read_deployed_stack_name_from_samconfig",
            return_value="deployed-stack-name-from-external-config",
        )

        manifest_dict = {
            **MINIMAL_MANIFEST_DICT,
            "pipeline_settings": {
                "inputs": {"environment": {"type": "string", "default": "prod"}}
            },
            "stacks": [
                {
                    "id": "api-stack",
                    "dir": "./stacks/api/",
                    "config": "configs/${{ inputs.environment }}/api/",
                }
            ],
        }

        pipeline = Pipeline.from_dict(manifest_dict, manifest_base_dir=Path("."))
        stack = pipeline.stacks[0]

        # Mock the config file exists
        mock_resolve_method = mocker.patch.object(
            pipeline,
            "_resolve_external_config_path",
            return_value=Path("/mock/configs/prod/api/samconfig.yaml"),
        )
        mocker.patch.object(Path, "exists", return_value=True)

        # Test the method
        deployed_name = pipeline._get_deployed_stack_name(stack)

        assert deployed_name == "deployed-stack-name-from-external-config"
        mock_resolve_method.assert_called_once_with(stack)
        mock_read_function.assert_called_once_with(
            Path("/mock/configs/prod/api"), "api-stack", sam_env="default"
        )

    def test_get_deployed_stack_name_external_config_missing(self, mocker):
        """Test that None is returned when external config file doesn't exist."""
        manifest_dict = {
            **MINIMAL_MANIFEST_DICT,
            "stacks": [
                {
                    "id": "missing-config-stack",
                    "dir": "./stacks/missing/",
                    "config": "configs/missing/stack/",
                }
            ],
        }

        pipeline = Pipeline.from_dict(manifest_dict, manifest_base_dir=Path("."))
        stack = pipeline.stacks[0]

        # Mock the config file doesn't exist
        mock_resolve_method = mocker.patch.object(
            pipeline,
            "_resolve_external_config_path",
            return_value=Path("/mock/configs/missing/stack/samconfig.yaml"),
        )
        mocker.patch.object(Path, "exists", return_value=False)

        # Test the method
        deployed_name = pipeline._get_deployed_stack_name(stack)

        assert deployed_name is None
        mock_resolve_method.assert_called_once_with(stack)

    def test_get_deployed_stack_name_local_mode(self, mocker):
        """Test that deployed stack name is read from local samconfig.yaml for non-external config stacks."""
        mock_read_function = mocker.patch(
            "samstacks.core._read_deployed_stack_name_from_samconfig",
            return_value="local-deployed-stack-name",
        )

        manifest_dict = {
            **MINIMAL_MANIFEST_DICT,
            "stacks": [
                {
                    "id": "local-stack",
                    "dir": "./stacks/local/",
                    # No config field - should use local samconfig.yaml
                }
            ],
        }

        pipeline = Pipeline.from_dict(manifest_dict, manifest_base_dir=Path("."))
        stack = pipeline.stacks[0]

        # Test the method
        deployed_name = pipeline._get_deployed_stack_name(stack)

        assert deployed_name == "local-deployed-stack-name"
        # The path gets resolved to absolute when creating the Stack object
        expected_path = Path("./stacks/local/").resolve()
        mock_read_function.assert_called_once_with(expected_path, "local-stack")

    def test_resolve_external_config_path_template_processing_error(self, mocker):
        """Test that template processing errors are handled gracefully."""
        manifest_dict = {
            **MINIMAL_MANIFEST_DICT,
            "stacks": [
                {
                    "id": "bad-template-stack",
                    "dir": "./stack/",
                    "config": "configs/${{ inputs.bad_syntax !!!! }}/stack/",
                }
            ],
        }

        pipeline = Pipeline.from_dict(manifest_dict, manifest_base_dir=Path("."))
        stack = pipeline.stacks[0]

        # Mock template processing to fail
        mock_process_string = mocker.patch.object(
            pipeline.template_processor,
            "process_string",
            side_effect=Exception("Template processing failed"),
        )

        # Test the helper method
        resolved_path = pipeline._resolve_external_config_path(stack)

        assert resolved_path is None
        mock_process_string.assert_called_once()
