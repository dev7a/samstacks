# tests/test_samconfig_manager.py
import pytest
import yaml  # For loading string to dict for test inputs
from pathlib import Path
import os
import shutil

from samstacks.samconfig_manager import SamConfigManager
from samstacks.pipeline_models import StackModel as PydanticStackModel
from samstacks.templating import TemplateProcessor
from samstacks.exceptions import ManifestError  # Import ManifestError


# Helper to create a mock TemplateProcessor
def create_mock_template_processor(mocker):
    mock_tp = mocker.MagicMock(spec=TemplateProcessor)
    # Make process_structure and process_string pass through data by default for simple tests
    # or return a modified version if needed by specific tests.
    mock_tp.process_structure.side_effect = (
        lambda data_structure, **kwargs: data_structure
    )
    mock_tp.process_string.side_effect = (
        lambda template_string, **kwargs: template_string if template_string else ""
    )
    return mock_tp


class TestSamConfigManagerHelpers:
    @pytest.fixture
    def manager_instance(self, mocker):
        """Provides a SamConfigManager instance with a mock TemplateProcessor."""
        mock_tp = create_mock_template_processor(mocker)
        return SamConfigManager(
            pipeline_name="TestPipeline",
            pipeline_description="A test pipeline",
            default_sam_config_from_pipeline=None,
            template_processor=mock_tp,
        )

    # Tests for _deep_copy_dict
    def test_deep_copy_dict_empty_and_none(self, manager_instance):
        assert manager_instance._deep_copy_dict(None) == {}
        assert manager_instance._deep_copy_dict({}) == {}

    def test_deep_copy_dict_simple(self, manager_instance):
        original = {"a": 1, "b": "hello"}
        copied = manager_instance._deep_copy_dict(original)
        assert copied == original
        assert copied is not original

    def test_deep_copy_dict_nested(self, manager_instance):
        original = {"a": 1, "b": {"c": 2, "d": [3, 4]}, "e": [{"f": 5}]}
        copied = manager_instance._deep_copy_dict(original)
        assert copied == original
        assert copied is not original
        assert copied["b"] is not original["b"]
        assert copied["b"]["d"] is not original["b"]["d"]
        assert copied["e"][0] is not original["e"][0]

    # Tests for _deep_merge_dicts
    def test_deep_merge_dicts_empty(self, manager_instance):
        assert manager_instance._deep_merge_dicts({}, {}) == {}
        base = {"a": 1}
        assert manager_instance._deep_merge_dicts(base, {}) == base
        assert manager_instance._deep_merge_dicts({}, base) == base

    def test_deep_merge_dicts_simple_override(self, manager_instance):
        base = {"a": 1, "b": 2}
        updates = {"b": 3, "c": 4}
        expected = {"a": 1, "b": 3, "c": 4}
        assert manager_instance._deep_merge_dicts(base, updates) == expected

    def test_deep_merge_dicts_nested(self, manager_instance):
        base = {"a": 1, "b": {"c": 2, "d": 5}, "f": [1, 2]}
        updates = {"b": {"c": 3, "e": 4}, "f": [3, 4], "g": 7}
        expected = {"a": 1, "b": {"c": 3, "d": 5, "e": 4}, "f": [3, 4], "g": 7}
        merged = manager_instance._deep_merge_dicts(base, updates)
        assert merged == expected
        # Ensure original base 'd' is preserved if not in updates at that level
        assert merged["b"]["d"] == 5
        # Ensure lists are replaced, not merged element-wise
        assert merged["f"] == [3, 4]

    def test_deep_merge_preserves_base_if_no_update_key(self, manager_instance):
        base = {"key1": "value1", "nested": {"n_key1": "n_value1"}}
        updates = {"key2": "value2"}
        expected = {
            "key1": "value1",
            "nested": {"n_key1": "n_value1"},
            "key2": "value2",
        }
        assert manager_instance._deep_merge_dicts(base, updates) == expected

    def test_deep_merge_updates_list_replaces(self, manager_instance):
        base = {"a": [1, 2], "b": {"c": [10, 20]}}
        updates = {"a": [3, 4], "b": {"c": [30, 40]}}
        expected = {"a": [3, 4], "b": {"c": [30, 40]}}
        assert manager_instance._deep_merge_dicts(base, updates) == expected

    def test_deep_merge_updates_primitive_replaces_dict(self, manager_instance):
        base = {"a": {"b": 1}}
        updates = {"a": "string_value"}
        expected = {"a": "string_value"}
        assert manager_instance._deep_merge_dicts(base, updates) == expected

    def test_deep_merge_updates_dict_replaces_primitive(self, manager_instance):
        base = {"a": "string_value"}
        updates = {"a": {"b": 1}}
        expected = {"a": {"b": 1}}
        assert manager_instance._deep_merge_dicts(base, updates) == expected


class TestSamConfigManagerApplySpecifics:
    @pytest.fixture
    def manager_instance(self, mocker):
        mock_tp = create_mock_template_processor(mocker)
        # Provide some default_sam_config for these tests to see interaction
        default_sam_config = {
            "version": 0.1,
            "default": {
                "deploy": {
                    "parameters": {
                        "existing_default_param": "default_val",
                        "resolve_s3": False,  # Test that our logic can override this to True if not set by user to True
                        "tags": {"App": "MyPipelineApp"},
                    }
                }
            },
        }
        return SamConfigManager(
            pipeline_name="ApplySpecificsPipe",
            pipeline_description="Testing apply specifics",
            default_sam_config_from_pipeline=default_sam_config,
            template_processor=mock_tp,
        )

    def test_apply_specifics_basic_overrides(self, manager_instance):
        base_config = manager_instance._deep_copy_dict(
            manager_instance.default_sam_config_from_pipeline
        )
        deployed_name = "my-stack-final-name"
        region = "us-east-1"
        pipeline_params = {"PipelineParam1": "Value1"}

        final_config = manager_instance._apply_stack_specific_configs(
            base_config, deployed_name, region, pipeline_params
        )

        params_section = final_config["default"]["deploy"]["parameters"]
        assert params_section["stack_name"] == deployed_name
        assert params_section["s3_prefix"] == deployed_name
        assert (
            params_section["resolve_s3"] is False
        )  # User's False should be kept if they explicitly set it
        assert (
            params_section["region"] == region
        )  # Set because not in original params_section
        assert params_section["parameter_overrides"] == "PipelineParam1=Value1"
        assert (
            params_section["existing_default_param"] == "default_val"
        )  # Original default preserved

    def test_apply_specifics_resolve_s3_defaulting(self, manager_instance):
        # Test when resolve_s3 is not in the input config at all
        config_without_resolve_s3 = {
            "default": {"deploy": {"parameters": {"some_other_param": "val"}}}
        }
        final_config = manager_instance._apply_stack_specific_configs(
            config_without_resolve_s3, "stack1", "us-west-2", {}
        )
        assert final_config["default"]["deploy"]["parameters"]["resolve_s3"] is True

        # Test when resolve_s3 is explicitly True by user
        config_with_resolve_s3_true = {
            "default": {"deploy": {"parameters": {"resolve_s3": True}}}
        }
        final_config_true = manager_instance._apply_stack_specific_configs(
            config_with_resolve_s3_true, "stack1", "us-west-2", {}
        )
        assert (
            final_config_true["default"]["deploy"]["parameters"]["resolve_s3"] is True
        )

    def test_apply_specifics_region_handling(self, manager_instance):
        base_config = {
            "default": {"deploy": {"parameters": {"region": "ap-southeast-2"}}}
        }
        # Region in base_config should be kept if effective_region is passed but region key exists
        final_config_region_exists = manager_instance._apply_stack_specific_configs(
            base_config, "stack-name", "us-east-1", {}
        )
        assert (
            final_config_region_exists["default"]["deploy"]["parameters"]["region"]
            == "ap-southeast-2"
        )

        # Region should be set if not in base_config parameters
        config_no_region = {"default": {"deploy": {"parameters": {}}}}
        final_config_no_region = manager_instance._apply_stack_specific_configs(
            config_no_region, "stack-name", "eu-west-1", {}
        )
        assert (
            final_config_no_region["default"]["deploy"]["parameters"]["region"]
            == "eu-west-1"
        )

        # Region should not be set if effective_region is None and not in base config
        final_config_no_effective_region = (
            manager_instance._apply_stack_specific_configs(
                config_no_region, "stack-name", None, {}
            )
        )
        assert (
            "region"
            not in final_config_no_effective_region["default"]["deploy"]["parameters"]
        )

    def test_apply_specifics_parameter_overrides_merge(self, manager_instance):
        base_config = {
            "default": {
                "deploy": {
                    "parameters": {
                        "parameter_overrides": {
                            "BaseParam": "BaseValue",
                            "ConflictParam": "BaseConflict",
                        }
                    }
                }
            }
        }
        pipeline_params = {
            "PipelineParam": "PipelineValue",
            "ConflictParam": "PipelineConflict",
        }

        final_config = manager_instance._apply_stack_specific_configs(
            base_config, "s1", "us-west-1", pipeline_params
        )

        # Expected format: space-separated key=value pairs
        expected_overrides_string = "BaseParam=BaseValue ConflictParam=PipelineConflict PipelineParam=PipelineValue"
        assert (
            final_config["default"]["deploy"]["parameters"]["parameter_overrides"]
            == expected_overrides_string
        )

    def test_apply_specifics_parameter_overrides_pipeline_only(self, manager_instance):
        base_config = {"default": {"deploy": {"parameters": {}}}}
        pipeline_params = {"MyParam": "OnlyFromPipeline"}
        final_config = manager_instance._apply_stack_specific_configs(
            base_config, "s1", "us-west-1", pipeline_params
        )
        assert (
            final_config["default"]["deploy"]["parameters"]["parameter_overrides"]
            == "MyParam=OnlyFromPipeline"
        )

    def test_apply_specifics_parameter_overrides_base_only(self, manager_instance):
        base_overrides = {"MyParam": "OnlyFromBase"}
        base_config = {
            "default": {
                "deploy": {"parameters": {"parameter_overrides": base_overrides}}
            }
        }
        pipeline_params = {}
        final_config = manager_instance._apply_stack_specific_configs(
            base_config, "s1", "us-west-1", pipeline_params
        )
        assert (
            final_config["default"]["deploy"]["parameters"]["parameter_overrides"]
            == "MyParam=OnlyFromBase"
        )

    def test_apply_specifics_parameter_overrides_empty_if_none_provided(
        self, manager_instance
    ):
        base_config = {"default": {"deploy": {"parameters": {}}}}
        pipeline_params = {}
        final_config = manager_instance._apply_stack_specific_configs(
            base_config, "s1", "us-west-1", pipeline_params
        )
        # Ensure parameter_overrides key is not added if no params from base or pipeline
        assert (
            "parameter_overrides" not in final_config["default"]["deploy"]["parameters"]
        )

    def test_apply_specifics_parameter_overrides_bad_existing_type(
        self, manager_instance, caplog
    ):
        base_config = {
            "default": {"deploy": {"parameters": {"parameter_overrides": "not_a_dict"}}}
        }
        pipeline_params = {"Key": "Value"}
        final_config = manager_instance._apply_stack_specific_configs(
            base_config, "s1", "us-west-1", pipeline_params
        )
        assert "not a dictionary. It will be overwritten" in caplog.text
        assert (
            final_config["default"]["deploy"]["parameters"]["parameter_overrides"]
            == "Key=Value"
        )


class TestSamConfigManagerGenerate:
    @pytest.fixture
    def mock_paths(self, mocker):
        """Mocks Path objects for file operations."""
        # Mock Path methods like exists, open, etc.
        # This is a simplified version; more specific mocks might be needed per test.
        mock_path_instance = mocker.MagicMock(spec=Path)
        mock_path_instance.exists.return_value = False
        mock_path_instance.__truediv__.return_value = (
            mock_path_instance  # path / "filename"
        )

        # Mock specific file paths if needed, e.g. for stack_dir / "samconfig.yaml"
        # For now, a generic mock that can be customized in tests.
        return mock_path_instance

    @pytest.fixture
    def manager_and_mocks(self, mocker):
        mock_tp = create_mock_template_processor(mocker)
        manager = SamConfigManager(
            pipeline_name="GenTestPipe",
            pipeline_description="Desc",
            default_sam_config_from_pipeline={
                "version": 0.1,
                "default": {"deploy": {"parameters": {"GlobalParam": "GlobalVal"}}},
            },
            template_processor=mock_tp,
        )

        # Mocks for file system operations
        mocker.patch("os.remove")
        mocker.patch("shutil.move")
        mock_open = mocker.patch("builtins.open", mocker.mock_open())
        mocker.patch("tomllib.load", return_value={})  # Default mock for tomllib.load
        mocker.patch("yaml.dump")

        # Mock for Path().exists() and other Path operations if needed globally for tests
        # This is tricky because Path is used everywhere. Specific patches per test are often better.
        # For instance, mock specific Path instances like stack_dir / "samconfig.toml"

        return manager, mock_tp, mock_open, os.remove, shutil.move, yaml.dump

    def test_generate_samconfig_greenfield(self, manager_and_mocks, mocker):
        manager, mock_tp, mock_open_func, _, mock_shutil_move, mock_yaml_dump = (
            manager_and_mocks
        )

        stack_dir = Path("/test/stack")
        pydantic_stack = PydanticStackModel(
            id="s1", dir=Path("rel_dir")
        )  # dir here is relative from manifest
        deployed_name = "GenTestPipe-s1"
        region = "us-east-1"
        resolved_params = {"StackParam": "ResolvedStackValue"}

        # Mock specific path behaviors for this test for greenfield
        mocker.patch.object(Path, "exists", return_value=False)

        # Make process_structure return a slightly modified structure for verification
        def custom_process_structure(data_structure, **kwargs):
            # Simulate some processing, e.g., resolving an env var if data had it
            processed = manager._deep_copy_dict(data_structure)
            if "default" in processed and "deploy" in processed["default"]:
                processed["default"]["deploy"]["parameters"]["ProcessedGlobalParam"] = (
                    "ProcessedGlobalVal"
                )
            return processed

        mock_tp.process_structure.side_effect = custom_process_structure

        target_path = manager.generate_samconfig_for_stack(
            stack_dir=stack_dir,
            stack_id="s1",
            pydantic_stack_model=pydantic_stack,
            deployed_stack_name=deployed_name,
            effective_region=region,
            resolved_stack_params=resolved_params,
        )

        assert target_path == stack_dir / "samconfig.yaml"
        mock_shutil_move.assert_not_called()  # No files to move in greenfield

        # Verify calls to template_processor.process_structure
        # It's called with the merged result of default_sam_config and stack's sam_config_overrides
        expected_base_for_processing = {
            "version": 0.1,
            "default": {"deploy": {"parameters": {"GlobalParam": "GlobalVal"}}},
        }  # pydantic_stack has no overrides in this test
        mock_tp.process_structure.assert_called_once_with(
            expected_base_for_processing,
            pipeline_name="GenTestPipe",
            pipeline_description="Desc",
        )

        # Verify the structure passed to yaml.dump
        # This structure is result of process_structure + _apply_stack_specific_configs
        args, _ = mock_yaml_dump.call_args
        dumped_config = args[0]

        assert (
            dumped_config["default"]["deploy"]["parameters"]["stack_name"]
            == deployed_name
        )
        assert (
            dumped_config["default"]["deploy"]["parameters"]["s3_prefix"]
            == deployed_name
        )
        assert dumped_config["default"]["deploy"]["parameters"]["region"] == region
        assert (
            dumped_config["default"]["deploy"]["parameters"]["parameter_overrides"]
            == "StackParam=ResolvedStackValue"
        )
        assert (
            dumped_config["default"]["deploy"]["parameters"]["ProcessedGlobalParam"]
            == "ProcessedGlobalVal"
        )
        assert (
            dumped_config["default"]["deploy"]["parameters"]["GlobalParam"]
            == "GlobalVal"
        )  # From initial default

    def test_generate_samconfig_with_toml_backup(self, manager_and_mocks, mocker):
        manager, mock_tp, _, mock_os_remove, mock_shutil_move, _ = manager_and_mocks

        stack_dir_path = Path("/test/stack_with_toml")
        existing_toml_file = stack_dir_path / "samconfig.toml"
        backup_toml_file = stack_dir_path / "samconfig.toml.bak"
        generated_yaml_file = stack_dir_path / "samconfig.yaml"

        EXISTING_TOML_FILE_STR = str(existing_toml_file)
        BACKUP_TOML_FILE_STR = str(backup_toml_file)
        GENERATED_YAML_FILE_STR = str(generated_yaml_file)

        # Use a different approach to mock Path.exists
        def mock_exists(path_instance):
            path_str_to_check = str(path_instance)
            print(
                f"mock_path_exists_side_effect_robust (TOML) called with Path instance: {path_str_to_check!r}"
            )

            if path_str_to_check == EXISTING_TOML_FILE_STR:
                return True
            if path_str_to_check == BACKUP_TOML_FILE_STR:
                return False
            if path_str_to_check == GENERATED_YAML_FILE_STR:
                return False
            return False

        mocker.patch.object(Path, "exists", mock_exists)
        mocker.patch("tomllib.load", return_value={"from_toml": "toml_value"})

        pydantic_stack = PydanticStackModel(id="s2", dir=Path("rel_path"))

        manager.generate_samconfig_for_stack(
            stack_dir=stack_dir_path,
            stack_id="s2",
            pydantic_stack_model=pydantic_stack,
            deployed_stack_name="Pipe-s2",
            effective_region="eu-west-1",
            resolved_stack_params={},
        )
        mock_shutil_move.assert_any_call(str(existing_toml_file), str(backup_toml_file))

    def test_generate_samconfig_with_yaml_backup(self, manager_and_mocks, mocker):
        manager, mock_tp, _, mock_os_remove, mock_shutil_move, _ = manager_and_mocks
        stack_dir_path = Path("/test/stack_with_yaml")
        existing_yaml_file = stack_dir_path / "samconfig.yaml"
        backup_yaml_file = stack_dir_path / "samconfig.yaml.bak"
        existing_toml_file_for_this_test = stack_dir_path / "samconfig.toml"

        EXISTING_YAML_FILE_STR = str(existing_yaml_file)
        BACKUP_YAML_FILE_STR = str(backup_yaml_file)
        EXISTING_TOML_FILE_STR_FOR_YAML_TEST = str(existing_toml_file_for_this_test)

        # Use a different approach to mock Path.exists
        def mock_exists_yaml(path_instance):
            path_str_to_check = str(path_instance)
            print(
                f"mock_path_exists_side_effect_robust (YAML) called with Path instance: {path_str_to_check!r}"
            )

            if path_str_to_check == EXISTING_YAML_FILE_STR:
                return True
            if path_str_to_check == BACKUP_YAML_FILE_STR:
                return False
            if path_str_to_check == EXISTING_TOML_FILE_STR_FOR_YAML_TEST:
                return False
            return False

        mocker.patch.object(Path, "exists", mock_exists_yaml)

        pydantic_stack = PydanticStackModel(id="s3", dir=Path("rel_path3"))
        manager.generate_samconfig_for_stack(
            stack_dir=stack_dir_path,
            stack_id="s3",
            pydantic_stack_model=pydantic_stack,
            deployed_stack_name="Pipe-s3",
            effective_region="ap-south-1",
            resolved_stack_params={},
        )
        mock_shutil_move.assert_any_call(str(existing_yaml_file), str(backup_yaml_file))

    def test_generate_samconfig_with_stack_overrides(self, manager_and_mocks, mocker):
        manager, mock_tp, _, _, _, mock_yaml_dump = manager_and_mocks
        mocker.patch.object(Path, "exists", return_value=False)  # Greenfield

        stack_specific_sam_config = {
            "default": {"deploy": {"parameters": {"StackSpecificParam": "StackVal"}}},
            "another_env": {"build": {"parameters": {"UseContainer": True}}},
        }
        pydantic_stack = PydanticStackModel(
            id="s4", dir=Path("s4dir"), sam_config_overrides=stack_specific_sam_config
        )

        manager.generate_samconfig_for_stack(
            stack_dir=Path("/test/s4"),
            stack_id="s4",
            pydantic_stack_model=pydantic_stack,
            deployed_stack_name="Pipe-s4",
            effective_region=None,
            resolved_stack_params={},
        )

        # Verify that process_structure was called with merged config
        expected_base_for_processing = manager._deep_merge_dicts(
            manager.default_sam_config_from_pipeline,  # Default from manager init
            stack_specific_sam_config,
        )
        mock_tp.process_structure.assert_called_once_with(
            expected_base_for_processing,
            pipeline_name="GenTestPipe",
            pipeline_description="Desc",
        )

        # Verify dumped config includes merged structure (assuming process_structure is pass-through for this test part)
        args, _ = mock_yaml_dump.call_args
        dumped_config = args[0]
        assert (
            dumped_config["default"]["deploy"]["parameters"]["GlobalParam"]
            == "GlobalVal"
        )
        assert (
            dumped_config["default"]["deploy"]["parameters"]["StackSpecificParam"]
            == "StackVal"
        )
        assert (
            dumped_config["another_env"]["build"]["parameters"]["UseContainer"] is True
        )

    def test_generate_samconfig_write_failure(self, manager_and_mocks, mocker):
        manager, _, mock_open_func, _, _, mock_yaml_dump = manager_and_mocks
        mocker.patch.object(Path, "exists", return_value=False)
        mock_yaml_dump.side_effect = yaml.YAMLError("Failed to dump")

        with pytest.raises(ManifestError) as excinfo:
            manager.generate_samconfig_for_stack(
                stack_dir=Path("/fail"),
                stack_id="s_fail",
                pydantic_stack_model=PydanticStackModel(id="s_fail", dir=Path("fdir")),
                deployed_stack_name="Pipe-fail",
                effective_region=None,
                resolved_stack_params={},
            )
        assert "Failed to write samconfig.yaml" in str(excinfo.value)
