"""
Tests for manifest validation functionality.
"""

import pytest
from pathlib import Path

from samstacks.exceptions import ManifestError
from samstacks.validation import ManifestValidator, LineNumberTracker
from samstacks.pipeline_models import PipelineManifestModel
from pydantic import ValidationError as PydanticValidationError


# Helper function to setup validator for tests
def setup_validator(
    manifest_data_dict: dict, manifest_base_dir_str: str = "."
) -> ManifestValidator:
    """Parses dict to Pydantic model and instantiates ManifestValidator."""
    try:
        pipeline_model = PipelineManifestModel.model_validate(manifest_data_dict)
    except PydanticValidationError as e:
        pytest.fail(f"Test setup failed: Pydantic model validation error: {e}")

    # LineNumberTracker is not easily used here without raw YAML content for the dictionary.
    # For semantic tests, we mostly care about logic, less about exact line numbers from validator itself for now.
    return ManifestValidator(
        pipeline_model, line_tracker=None, manifest_base_dir=Path(manifest_base_dir_str)
    )


class TestManifestValidatorSemantic:
    """Test semantic validation rules in ManifestValidator (post-Pydantic parsing)."""

    def test_valid_manifest_semantic_passes(self, tmp_path: Path) -> None:
        """Test that a semantically valid manifest (post-Pydantic) passes."""
        stack1_dir = tmp_path / "stack1"
        stack1_dir.mkdir()
        (stack1_dir / "template.yaml").write_text(
            "AWSTemplateFormatVersion: '2010-09-09'"
        )

        stack2_dir = tmp_path / "stack2"
        stack2_dir.mkdir()
        (stack2_dir / "template.yaml").write_text(
            "AWSTemplateFormatVersion: '2010-09-09'"
        )

        manifest_data = {
            "pipeline_name": "test-pipeline",
            "stacks": [
                {
                    "id": "stack1",
                    "dir": str(stack1_dir.relative_to(tmp_path)),
                    "params": {"Param1": "value1"},
                },
                {
                    "id": "stack2",
                    "dir": str(stack2_dir.relative_to(tmp_path)),
                    "params": {"Param2": "${{ stacks.stack1.outputs.Output1 }}"},
                },
            ],
        }
        # Base directory for resolving stack.dir will be tmp_path
        validator = setup_validator(manifest_data, manifest_base_dir_str=str(tmp_path))
        validator.validate_semantic_rules_and_raise_if_errors()  # Should not raise

    def test_stack_singular_expression_error(self, tmp_path: Path) -> None:
        """Test that 'stack.id' (singular) gives helpful error for template expressions."""
        s1d = tmp_path / "stack1"
        s1d.mkdir()
        (s1d / "template.yaml").touch()
        s2d = tmp_path / "stack2"
        s2d.mkdir()
        (s2d / "template.yaml").touch()
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
        validator = setup_validator(manifest_data, manifest_base_dir_str=str(tmp_path))
        with pytest.raises(
            ManifestError,
            match=r"stack 'stack2' param 'Param1': Invalid expression 'stack.stack1.outputs.Output1'.*Did you mean 'stacks.stack1.outputs.Output1'.*'stacks' is plural",
        ):
            validator.validate_semantic_rules_and_raise_if_errors()

    def test_nonexistent_stack_reference(self, tmp_path: Path) -> None:
        """Test that referencing a nonexistent stack in template expressions fails."""
        s1d = tmp_path / "stack1"
        s1d.mkdir()
        (s1d / "template.yaml").touch()
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
        validator = setup_validator(manifest_data, manifest_base_dir_str=str(tmp_path))
        with pytest.raises(
            ManifestError,
            match=r"stack 'stack1' param 'Param1': Stack 'nonexistent' does not exist in the pipeline. Available stacks: \['stack1'\]",
        ):
            validator.validate_semantic_rules_and_raise_if_errors()

    def test_forward_reference_error(self, tmp_path: Path) -> None:
        s1d = tmp_path / "stack1"
        s1d.mkdir()
        (s1d / "template.yaml").touch()
        s2d = tmp_path / "stack2"
        s2d.mkdir()
        (s2d / "template.yaml").touch()
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
        validator = setup_validator(manifest_data, manifest_base_dir_str=str(tmp_path))
        with pytest.raises(
            ManifestError,
            match=r"stack 'stack1' param 'Param1': Stack 'stack2' is defined later in the pipeline.*Stack outputs can only reference stacks defined earlier",
        ):
            validator.validate_semantic_rules_and_raise_if_errors()

    def test_valid_env_expressions(self, tmp_path: Path) -> None:
        s1d = tmp_path / "stack1"
        s1d.mkdir()
        (s1d / "template.yaml").touch()
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
        validator = setup_validator(manifest_data, manifest_base_dir_str=str(tmp_path))
        validator.validate_semantic_rules_and_raise_if_errors()  # Should not raise

    def test_stack_dir_does_not_exist(self, tmp_path: Path) -> None:
        manifest_data = {
            "pipeline_name": "test_dir",
            "stacks": [{"id": "s1", "dir": "nonexistent_dir/"}],
        }
        validator = setup_validator(manifest_data, manifest_base_dir_str=str(tmp_path))
        with pytest.raises(
            ManifestError,
            match=r"stack 's1' field 'dir': Stack directory does not exist",
        ):
            validator.validate_semantic_rules_and_raise_if_errors()

    def test_stack_dir_is_file(self, tmp_path: Path) -> None:
        file_path = tmp_path / "is_a_file.txt"
        file_path.write_text("hello")
        manifest_data = {
            "pipeline_name": "test_dir_file",
            "stacks": [{"id": "s1", "dir": str(file_path.relative_to(tmp_path))}],
        }
        validator = setup_validator(manifest_data, manifest_base_dir_str=str(tmp_path))
        with pytest.raises(
            ManifestError,
            match=r"stack 's1' field 'dir': Stack path is not a directory",
        ):
            validator.validate_semantic_rules_and_raise_if_errors()

    def test_stack_dir_no_template_file(self, tmp_path: Path) -> None:
        stack_dir = tmp_path / "empty_stack_dir"
        stack_dir.mkdir()
        manifest_data = {
            "pipeline_name": "test_no_template",
            "stacks": [{"id": "s1", "dir": str(stack_dir.relative_to(tmp_path))}],
        }
        validator = setup_validator(manifest_data, manifest_base_dir_str=str(tmp_path))
        with pytest.raises(
            ManifestError, match=r"stack 's1': No template.yaml or template.yml found"
        ):
            validator.validate_semantic_rules_and_raise_if_errors()

    def test_valid_input_expression(self, tmp_path: Path):
        s1d = tmp_path / "s1"
        s1d.mkdir()
        (s1d / "template.yaml").touch()
        manifest_data = {
            "pipeline_name": "test-inputs",
            "pipeline_settings": {
                "inputs": {"env_name": {"type": "string", "default": "dev"}}
            },
            "stacks": [
                {"id": "s1", "dir": "s1/", "params": {"Env": "${{ inputs.env_name }}"}}
            ],
        }
        validator = setup_validator(manifest_data, manifest_base_dir_str=str(tmp_path))
        validator.validate_semantic_rules_and_raise_if_errors()

    def test_invalid_input_expression_undefined_input(self, tmp_path: Path):
        s1d = tmp_path / "s1"
        s1d.mkdir()
        (s1d / "template.yaml").touch()
        manifest_data = {
            "pipeline_name": "test-inputs",
            "pipeline_settings": {"inputs": {}},
            "stacks": [
                {
                    "id": "s1",
                    "dir": "s1/",
                    "params": {"Env": "${{ inputs.undefined_input }}"},
                }
            ],
        }
        validator = setup_validator(manifest_data, manifest_base_dir_str=str(tmp_path))
        with pytest.raises(
            ManifestError,
            match=r"stack 's1' param 'Env': Input 'undefined_input' is not defined .* Available inputs: none defined",
        ):
            validator.validate_semantic_rules_and_raise_if_errors()

    def test_template_expression_in_pipeline_name(self, tmp_path: Path):
        manifest_data = {
            "pipeline_name": "${{ env.PIPELINE_NAME_VAR }}",  # Pydantic accepts this as a string
            "stacks": [],
        }
        validator = setup_validator(manifest_data, manifest_base_dir_str=str(tmp_path))
        validator.validate_semantic_rules_and_raise_if_errors()

    def test_valid_pipeline_attribute_expression(self, tmp_path: Path):
        s1d = tmp_path / "s1"
        s1d.mkdir()
        (s1d / "template.yaml").touch()
        manifest_data = {
            "pipeline_name": "MyPipe",
            "pipeline_description": "My Desc",
            "stacks": [
                {
                    "id": "s1",
                    "dir": "s1/",
                    "params": {
                        "Desc": "${{ pipeline.description }}",
                        "Name": "${{ pipeline.name }}",
                    },
                }
            ],
        }
        validator = setup_validator(manifest_data, manifest_base_dir_str=str(tmp_path))
        validator.validate_semantic_rules_and_raise_if_errors()

    def test_invalid_pipeline_attribute_expression(self, tmp_path: Path):
        s1d = tmp_path / "s1"
        s1d.mkdir()
        (s1d / "template.yaml").touch()
        manifest_data = {
            "pipeline_name": "MyPipe",
            "stacks": [
                {
                    "id": "s1",
                    "dir": "s1/",
                    "params": {"Attr": "${{ pipeline.unknown_attr }}"},
                }
            ],
        }
        validator = setup_validator(manifest_data, manifest_base_dir_str=str(tmp_path))
        with pytest.raises(
            ManifestError, match=r"Invalid pipeline attribute 'unknown_attr'"
        ):
            validator.validate_semantic_rules_and_raise_if_errors()


class TestLineNumberTrackerDirect:
    def test_parse_and_get_line_numbers(self):
        yaml_content = """key1: value1
key2:
  nested_key: nested_value
list_key:
  - item1
  - item2
"""
        tracker = LineNumberTracker()
        data, _ = tracker.parse_yaml_with_line_numbers(yaml_content)

        assert tracker.get_line_number(data) == 1  # Root dict
        assert tracker.get_line_number(data["key1"]) == 1  # value1
        assert (
            tracker.get_line_number(data["key2"]) == 3
        )  # nested_key dict (starts at line 3 where nested_key is)
        assert tracker.get_line_number(data["key2"]["nested_key"]) == 3  # nested_value
        assert (
            tracker.get_line_number(data["list_key"]) == 5
        )  # list object itself (starts at line 5 where first item is)
        if isinstance(data["list_key"], list) and len(data["list_key"]) > 0:
            assert tracker.get_line_number(data["list_key"][0]) == 5  # item1
            assert tracker.get_line_number(data["list_key"][1]) == 6  # item2

    def test_parse_invalid_yaml_raises_manifest_error(self):
        yaml_content = "key: value: another_value # Invalid YAML"
        tracker = LineNumberTracker()
        with pytest.raises(ManifestError, match="Failed to parse YAML"):
            tracker.parse_yaml_with_line_numbers(yaml_content)
