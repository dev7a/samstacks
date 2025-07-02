import pytest
from pydantic import ValidationError
from pathlib import Path

from samstacks.pipeline_models import (
    PipelineManifestModel,
    PipelineSettingsModel,
    StackModel,
    PipelineInputItem,
    SamConfigContentType,
)


# Tests for PipelineInputItem model
class TestPipelineInputItem:
    def test_valid_input_types(self):
        valid_types = ["string", "number", "boolean"]
        for type_val in valid_types:
            item = PipelineInputItem(type=type_val)
            assert item.type == type_val

    def test_invalid_input_type(self):
        with pytest.raises(ValidationError) as excinfo:
            PipelineInputItem(type="invalid_type")
        assert "Input type must be one of" in str(excinfo.value)
        # Example of checking specific error details in Pydantic V2
        # errors = excinfo.value.errors()
        # assert errors[0]["type"] == "value_error"
        # assert "Input type must be one of" in errors[0]["msg"]

    def test_input_item_with_defaults_and_description(self):
        item = PipelineInputItem(
            type="string", description="A test input", default="hello"
        )
        assert item.type == "string"
        assert item.description == "A test input"
        assert item.default == "hello"


# Tests for StackModel
class TestStackModel:
    def test_stack_model_basic(self):
        stack = StackModel(id="test-stack", dir=Path("./some/dir"))
        assert stack.id == "test-stack"
        assert stack.dir == Path("./some/dir")
        assert stack.params == {}
        assert stack.sam_config_overrides is None

    def test_stack_model_with_all_fields(self):
        sam_config: SamConfigContentType = {
            "default": {"deploy": {"parameters": {"Foo": "Bar"}}}
        }
        stack_data = {
            "id": "s1",
            "dir": "stack_dir",
            "name": "My Stack",
            "description": "A test stack",
            "params": {"Param1": "Value1"},
            "stack_name_suffix": "-dev",
            "region": "us-west-2",
            "profile": "myprofile",
            "if": "${{ env.DEPLOY_IT }}",
            "run": "echo hello",
            "sam_config_overrides": sam_config,
        }
        stack = StackModel(**stack_data)
        assert stack.id == "s1"
        assert stack.dir == Path("stack_dir")
        assert stack.name == "My Stack"
        assert stack.params == {"Param1": "Value1"}
        assert stack.sam_config_overrides == sam_config
        assert stack.if_condition == "${{ env.DEPLOY_IT }}"

    def test_stack_model_aliases(self):
        # Test that 'if' and 'run' aliases work
        stack_data = {
            "id": "s2",
            "dir": Path("./another/dir"),
            "if": "${{ inputs.cond }}",
            "run": "./do_stuff.sh",
        }
        stack = StackModel(**stack_data)  # Uses populate_by_name due to model_config
        assert stack.if_condition == "${{ inputs.cond }}"
        assert stack.run_script == "./do_stuff.sh"

    def test_stack_model_with_config_field(self):
        """Test that the new config field is properly handled."""
        # Test with config field provided as Path
        stack_data = {
            "id": "test-stack",
            "dir": Path("./stack/dir"),
            "config": Path("./configs/dev/test-stack.yaml"),
        }
        stack = StackModel(**stack_data)
        assert stack.id == "test-stack"
        assert stack.dir == Path("./stack/dir")
        assert stack.config == Path("./configs/dev/test-stack.yaml")

        # Test without config field (should default to None)
        stack_data_no_config = {
            "id": "legacy-stack",
            "dir": Path("./legacy/dir"),
        }
        stack_no_config = StackModel(**stack_data_no_config)
        assert stack_no_config.config is None

        # Test with config field as string using model_validate (Pydantic handles conversion)
        stack_data_str_config = {
            "id": "str-config-stack",
            "dir": "./stack/dir",
            "config": "configs/staging/stack.yaml",
        }
        stack_str_config = StackModel.model_validate(stack_data_str_config)
        assert stack_str_config.config == Path("configs/staging/stack.yaml")

        # Test with templated config path
        stack_data_templated = {
            "id": "templated-stack",
            "dir": "./stack/dir",
            "config": "./configs/${{ inputs.environment }}/stack.yaml",
        }
        stack_templated = StackModel.model_validate(stack_data_templated)
        assert stack_templated.config == Path(
            "./configs/${{ inputs.environment }}/stack.yaml"
        )

    def test_config_path_validation_rules(self):
        """Test the new config path validation and normalization rules."""
        base_stack = {
            "id": "test-stack",
            "dir": "./stack/dir",
        }

        # Valid: Explicit .yaml file
        stack1 = StackModel.model_validate(
            {**base_stack, "config": "configs/dev/app/samconfig.yaml"}
        )
        assert stack1.config == Path("configs/dev/app/samconfig.yaml")

        # Valid: Explicit .yml file
        stack2 = StackModel.model_validate(
            {**base_stack, "config": "configs/dev/app/config.yml"}
        )
        assert stack2.config == Path("configs/dev/app/config.yml")

        # Valid: Directory path (auto-appends samconfig.yaml)
        stack3 = StackModel.model_validate({**base_stack, "config": "configs/dev/app/"})
        assert stack3.config == Path("configs/dev/app/samconfig.yaml")

        # Valid: No config (None)
        stack4 = StackModel.model_validate(base_stack)
        assert stack4.config is None

        # Invalid: Missing extension and trailing slash
        with pytest.raises(ValidationError, match="Invalid config path.*must end with"):
            StackModel.model_validate({**base_stack, "config": "configs/dev/app"})

        # Invalid: Wrong extension
        with pytest.raises(ValidationError, match="Invalid config path.*must end with"):
            StackModel.model_validate(
                {**base_stack, "config": "configs/dev/app/config.json"}
            )

        # Test that directory normalization works with templates
        stack_templated = StackModel.model_validate(
            {**base_stack, "config": "configs/${{ inputs.environment }}/app/"}
        )
        assert stack_templated.config == Path(
            "configs/${{ inputs.environment }}/app/samconfig.yaml"
        )

    def test_stack_runtime_instantiation_with_config_path(self):
        """Test that Stack runtime objects can be created with config_path."""
        from samstacks.core import Stack
        from pathlib import Path

        # Test with config_path provided
        stack = Stack(
            id="test-stack",
            name="Test Stack",
            dir="./stack/dir",
            config_path=Path("./configs/dev/test-stack.yaml"),
        )
        assert stack.id == "test-stack"
        assert stack.name == "Test Stack"
        assert stack.dir == Path("./stack/dir")
        assert stack.config_path == Path("./configs/dev/test-stack.yaml")

        # Test without config_path (should default to None)
        stack_no_config = Stack(
            id="legacy-stack", name="Legacy Stack", dir="./legacy/dir"
        )
        assert stack_no_config.config_path is None

    def test_config_path_template_processing_and_validation(self):
        """Test that config paths support template substitution and validation."""
        from samstacks.core import _validate_config_path
        from samstacks.exceptions import ManifestError
        from pathlib import Path
        import pytest

        # Test config path validation function directly
        # Should not raise for valid paths
        _validate_config_path(Path("./configs/dev/api.yaml"), "test-stack")
        _validate_config_path(Path("configs/staging/api.yaml"), "test-stack")

        # Should raise for system directories
        with pytest.raises(ManifestError, match="Cannot write to system directory"):
            _validate_config_path(Path("/etc/samstacks/config.yaml"), "test-stack")

        with pytest.raises(ManifestError, match="Cannot write to system directory"):
            _validate_config_path(Path("/usr/local/config.yaml"), "test-stack")

        # Test template processing in config path (integration test would be ideal,
        # but for now we test that the templated path is preserved in the model)
        stack_data_templated = {
            "id": "templated-stack",
            "dir": "./stack/dir",
            "config": "./configs/${{ inputs.environment }}/stack.yaml",
        }
        stack_templated = StackModel.model_validate(stack_data_templated)
        assert "${{ inputs.environment }}" in str(stack_templated.config)

    def test_external_config_generation_integration(self):
        """Test that external config generation works with SamConfigManager."""
        from samstacks.samconfig_manager import SamConfigManager
        from samstacks.templating import TemplateProcessor
        from pathlib import Path
        import tempfile
        import yaml
        import os

        # Create a temporary directory for the test
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Set up test data
            template_processor = TemplateProcessor(
                defined_inputs={"environment": {"type": "string", "default": "dev"}},
                cli_inputs={"environment": "staging"},
            )

            sam_config_manager = SamConfigManager(
                pipeline_name="Test Pipeline",
                pipeline_description="Test Description",
                default_sam_config_from_pipeline={
                    "version": 0.1,
                    "default": {
                        "deploy": {
                            "parameters": {
                                "capabilities": "CAPABILITY_IAM",
                                "resolve_s3": True,
                            }
                        }
                    },
                },
                template_processor=template_processor,
            )

            # Create stack model
            stack_model = StackModel(id="test-stack", dir=temp_path / "stack")

            # Create fake stack directory and template
            stack_dir = temp_path / "stack"
            stack_dir.mkdir()
            template_file = stack_dir / "template.yaml"
            template_file.write_text(
                "AWSTemplateFormatVersion: '2010-09-09'\nResources: {}"
            )

            # Generate external config
            config_path = temp_path / "configs" / "staging" / "test-stack.yaml"

            result_path = sam_config_manager.generate_external_config_file(
                config_path=config_path,
                stack_dir=stack_dir,
                stack_id="test-stack",
                pydantic_stack_model=stack_model,
                deployed_stack_name="staging-test-stack",
                effective_region="us-west-2",
                resolved_stack_params={"Environment": "staging"},
            )

            # Verify external config was created
            assert result_path == config_path
            assert config_path.exists()

            # Verify content
            with open(config_path, "r") as f:
                config_content = yaml.safe_load(f)

            assert config_content["version"] == 0.1
            assert (
                config_content["default"]["deploy"]["parameters"]["stack_name"]
                == "staging-test-stack"
            )
            assert (
                config_content["default"]["deploy"]["parameters"]["region"]
                == "us-west-2"
            )
            assert (
                "Environment=staging"
                in config_content["default"]["deploy"]["parameters"][
                    "parameter_overrides"
                ]
            )

            # Verify template references were added
            assert "template" in config_content["default"]["build"]["parameters"]
            assert "template" in config_content["default"]["deploy"]["parameters"]

            # The template path should be relative from config to stack
            expected_template_path = os.path.relpath(template_file, config_path.parent)
            assert (
                config_content["default"]["build"]["parameters"]["template"]
                == expected_template_path
            )
            assert (
                config_content["default"]["deploy"]["parameters"]["template"]
                == expected_template_path
            )


# Tests for PipelineSettingsModel
class TestPipelineSettingsModel:
    def test_pipeline_settings_defaults(self):
        settings = PipelineSettingsModel()
        assert settings.stack_name_prefix is None
        assert settings.default_sam_config is None
        assert settings.inputs == {}

    def test_pipeline_settings_with_values(self):
        """Test pipeline settings with all values provided."""
        data = {
            "stack_name_prefix": "prod-",
            "stack_name_suffix": "-v1",
            "default_region": "us-east-1",
            "default_profile": "production",
            "inputs": {
                "environment": {
                    "type": "string",
                    "description": "Deployment environment",
                    "default": "prod",
                }
            },
            "default_sam_config": {
                "version": 0.1,
                "default": {
                    "deploy": {"parameters": {"capabilities": "CAPABILITY_IAM"}}
                },
            },
        }

        settings = PipelineSettingsModel.model_validate(data)
        assert settings.stack_name_prefix == "prod-"
        assert settings.stack_name_suffix == "-v1"
        assert settings.default_region == "us-east-1"
        assert settings.default_profile == "production"
        assert settings.inputs is not None
        assert "environment" in settings.inputs
        assert settings.inputs["environment"].type == "string"
        assert settings.default_sam_config is not None

    def test_output_masking_defaults(self):
        """Test that output_masking defaults properly."""
        data = {"default_region": "us-west-2"}

        settings = PipelineSettingsModel.model_validate(data)
        assert settings.output_masking.enabled is False
        assert settings.output_masking.categories.account_ids is False


# Tests for PipelineManifestModel
class TestPipelineManifestModel:
    def test_minimal_valid_manifest(self):
        manifest = PipelineManifestModel(
            pipeline_name="TestPipeline",
            stacks=[
                StackModel(id="s1", dir=Path("s1dir")),
                StackModel(id="s2", dir=Path("s2dir")),
            ],
        )
        assert manifest.pipeline_name == "TestPipeline"
        assert len(manifest.stacks) == 2
        assert manifest.stacks[0].id == "s1"

    def test_duplicate_stack_ids(self):
        with pytest.raises(ValidationError) as excinfo:
            PipelineManifestModel(
                pipeline_name="DupPipeline",
                stacks=[
                    StackModel(id="s1", dir=Path("s1dir")),
                    StackModel(id="s1", dir=Path("s2dir")),
                ],
            )
        # Pydantic V2 includes error details in a structured way
        # We check if the message from the validator is in the exception string for simplicity
        assert "Duplicate stack ID found: s1" in str(excinfo.value)
        # errors = excinfo.value.errors()
        # assert errors[0]["type"] == "value_error"
        # assert "Duplicate stack ID found: s1" in errors[0]["msg"]

    def test_empty_stacks_list(self):
        # Pydantic allows empty list if default_factory is used
        manifest = PipelineManifestModel(pipeline_name="EmptyStacks")
        assert manifest.stacks == []

    def test_full_manifest_structure(self):
        manifest_data = {
            "pipeline_name": "FullApp",
            "pipeline_description": "A full application pipeline",
            "pipeline_settings": {
                "stack_name_prefix": "full-app-",
                "default_region": "us-east-1",
                "inputs": {
                    "environment": {"type": "string", "default": "staging"},
                    "log_level": {"type": "string", "description": "Logging level"},
                },
                "default_sam_config": {
                    "version": 0.1,
                    "default": {"deploy": {"parameters": {"ResolveS3": True}}},
                },
            },
            "stacks": [
                {
                    "id": "backend",
                    "dir": "./services/backend",
                    "params": {"TableName": "MyTable"},
                    "sam_config_overrides": {
                        "default": {"deploy": {"parameters": {"MemorySize": 512}}}
                    },
                },
                {
                    "id": "frontend",
                    "dir": "./services/frontend",
                    "if": "${{ inputs.environment == 'prod' }}",
                },
            ],
        }
        pipeline = PipelineManifestModel.model_validate(manifest_data)
        assert pipeline.pipeline_name == "FullApp"
        assert pipeline.pipeline_settings.default_region == "us-east-1"
        assert pipeline.pipeline_settings.inputs is not None
        assert pipeline.pipeline_settings.inputs["environment"].default == "staging"
        assert pipeline.pipeline_settings.default_sam_config is not None
        assert pipeline.stacks[0].id == "backend"
        assert pipeline.stacks[0].sam_config_overrides is not None
        assert pipeline.stacks[1].if_condition == "${{ inputs.environment == 'prod' }}"

    def test_extra_fields_forbidden(self):
        invalid_manifest_data = {
            "pipeline_name": "TestExtra",
            "stacks": [],
            "unknown_top_level_field": "some_value",
        }
        with pytest.raises(ValidationError) as excinfo:
            PipelineManifestModel.model_validate(invalid_manifest_data)
        assert "Extra inputs are not permitted" in str(
            excinfo.value
        )  # Pydantic V2 message for extra fields

        invalid_stack_data = {
            "id": "s1",
            "dir": "./s1dir",
            "unknown_stack_field": "value",
        }
        with pytest.raises(ValidationError) as excinfo:
            StackModel.model_validate(invalid_stack_data)
        assert "Extra inputs are not permitted" in str(excinfo.value)

        invalid_settings_data = {
            "default_region": "us-west-1",
            "unknown_settings_field": "value",
        }
        with pytest.raises(ValidationError) as excinfo:
            PipelineSettingsModel.model_validate(invalid_settings_data)
        assert "Extra inputs are not permitted" in str(excinfo.value)

        invalid_input_item_data = {"type": "string", "unknown_input_field": "value"}
        with pytest.raises(ValidationError) as excinfo:
            PipelineInputItem.model_validate(invalid_input_item_data)
        assert "Extra inputs are not permitted" in str(excinfo.value)

    def test_summary_field_validation(self):
        """Test that the summary field is properly validated."""
        # Test with valid summary
        manifest_data = {
            "pipeline_name": "TestSummary",
            "summary": "# Deployment Complete!\n\nAll stacks deployed successfully.",
            "stacks": [{"id": "test-stack", "dir": "./test"}],
        }
        pipeline = PipelineManifestModel.model_validate(manifest_data)
        assert (
            pipeline.summary
            == "# Deployment Complete!\n\nAll stacks deployed successfully."
        )

        # Test with None summary (should be allowed)
        manifest_data_no_summary = {
            "pipeline_name": "TestNoSummary",
            "stacks": [{"id": "test-stack", "dir": "./test"}],
        }
        pipeline_no_summary = PipelineManifestModel.model_validate(
            manifest_data_no_summary
        )
        assert pipeline_no_summary.summary is None

        # Test with empty string summary (should be allowed)
        manifest_data_empty = {
            "pipeline_name": "TestEmptySummary",
            "summary": "",
            "stacks": [{"id": "test-stack", "dir": "./test"}],
        }
        pipeline_empty = PipelineManifestModel.model_validate(manifest_data_empty)
        assert pipeline_empty.summary == ""

        # Test with multiline summary with template expressions
        manifest_data_templated = {
            "pipeline_name": "TestTemplatedSummary",
            "summary": """# Deployment Complete!
            
Your **${{ inputs.environment }}** environment is ready.

## Infrastructure:
- Stack: ${{ stacks.backend.outputs.StackName }}
- Region: ${{ pipeline.settings.default_region }}
            """,
            "stacks": [{"id": "backend", "dir": "./backend"}],
        }
        pipeline_templated = PipelineManifestModel.model_validate(
            manifest_data_templated
        )
        assert pipeline_templated.summary is not None
        assert "${{ inputs.environment }}" in pipeline_templated.summary
        assert "${{ stacks.backend.outputs.StackName }}" in pipeline_templated.summary
