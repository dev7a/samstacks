# tests/test_samconfig_manager.py
import pytest
import yaml  # For loading string to dict for test inputs

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
        assert params_section["parameter_overrides"] == ["PipelineParam1=Value1"]
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
        # Pipeline region settings (effective_region) should always override local config region
        final_config_region_override = manager_instance._apply_stack_specific_configs(
            base_config, "stack-name", "us-east-1", {}
        )
        assert (
            final_config_region_override["default"]["deploy"]["parameters"]["region"]
            == "us-east-1"  # Pipeline region overrides local config
        )

        # If no effective_region is provided, existing region should remain unchanged
        final_config_no_region = manager_instance._apply_stack_specific_configs(
            base_config, "stack-name", None, {}
        )
        assert (
            final_config_no_region["default"]["deploy"]["parameters"]["region"]
            == "ap-southeast-2"  # Original region preserved when no override
        )

    def test_apply_specifics_parameter_overrides_merge(self, manager_instance):
        base_config = {
            "default": {
                "deploy": {
                    "parameters": {
                        # This will be ignored by the new logic if pipeline_params are provided
                        "parameter_overrides": "BaseParam=BaseValue ConflictParam=BaseConflictOld"
                    }
                }
            }
        }
        pipeline_params = {  # These will take full precedence
            "PipelineParam": "PipelineValue",
            "ConflictParam": "PipelineConflictNew",
        }

        final_config = manager_instance._apply_stack_specific_configs(
            base_config, "s1", "us-west-1", pipeline_params
        )

        expected_overrides_array = [
            "PipelineParam=PipelineValue",
            "ConflictParam=PipelineConflictNew",
        ]
        assert (
            final_config["default"]["deploy"]["parameters"]["parameter_overrides"]
            == expected_overrides_array
        )

    def test_apply_specifics_parameter_overrides_pipeline_only(self, manager_instance):
        base_config = {"default": {"deploy": {"parameters": {}}}}
        pipeline_params = {"MyParam": "OnlyFromPipeline"}
        final_config = manager_instance._apply_stack_specific_configs(
            base_config, "s1", "us-west-1", pipeline_params
        )
        assert final_config["default"]["deploy"]["parameters"][
            "parameter_overrides"
        ] == ["MyParam=OnlyFromPipeline"]

    def test_apply_specifics_parameter_overrides_base_only(self, manager_instance):
        base_config = {
            "default": {
                "deploy": {
                    "parameters": {"parameter_overrides": "MyParam=OnlyFromBase"}
                }
            }
        }
        pipeline_params = {}  # Empty pipeline_params
        final_config = manager_instance._apply_stack_specific_configs(
            base_config, "s1", "us-west-1", pipeline_params
        )
        # parameter_overrides should now be absent because pipeline_params is empty
        assert (
            "parameter_overrides" not in final_config["default"]["deploy"]["parameters"]
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
            # This initial non-dict value will be removed if pipeline_params is empty
            "default": {
                "deploy": {
                    "parameters": {
                        "parameter_overrides": "not_a_valid_sam_cli_string_format_but_still_a_string"
                    }
                }
            }
        }
        pipeline_params = {"Key": "Value"}  # Pipeline params will overwrite
        final_config = manager_instance._apply_stack_specific_configs(
            base_config, "s1", "us-west-1", pipeline_params
        )
        # No warning log is expected anymore
        assert "not a dictionary" not in caplog.text
        assert final_config["default"]["deploy"]["parameters"][
            "parameter_overrides"
        ] == ["Key=Value"]

        # Test case where pipeline_params is empty, so pre-existing string should be removed
        pipeline_params_empty = {}
        final_config_empty_params = manager_instance._apply_stack_specific_configs(
            base_config, "s2", "us-west-1", pipeline_params_empty
        )
        assert (
            "parameter_overrides"
            not in final_config_empty_params["default"]["deploy"]["parameters"]
        )

    def test_apply_specifics_parameter_overrides_empty_string_value(
        self, manager_instance
    ):
        base_config = {"default": {"deploy": {"parameters": {}}}}
        pipeline_params = {"EmptyVpcId": "", "NormalParam": "NormalValue"}
        final_config = manager_instance._apply_stack_specific_configs(
            base_config, "s_empty_string", "us-west-1", pipeline_params
        )
        expected_overrides = ['EmptyVpcId=""', "NormalParam=NormalValue"]
        # The order might vary depending on dict iteration, so we check presence and length
        actual_overrides = final_config["default"]["deploy"]["parameters"][
            "parameter_overrides"
        ]
        assert len(actual_overrides) == len(expected_overrides)
        for expected_item in expected_overrides:
            assert expected_item in actual_overrides

    def test_apply_stack_specific_configs_parameter_overrides_formatting(
        self, manager_instance
    ):
        """Test various parameter override formatting including empty, spaces, and equals signs."""
        base_config = {"default": {"deploy": {"parameters": {}}}}
        pipeline_params = {
            "EmptyVpcId": "",
            "NormalParam": "NormalValue",
            "SpacedParam": "Value With Spaces",
            "EqualsParam": "Key=InternalValue",
            "SpacedAndEqualsParam": "Value With Spaces And Key=InternalValue",
            "QuotedSpacedParam": '"Quoted Value With Spaces"',  # Value already has quotes
        }
        final_config = manager_instance._apply_stack_specific_configs(
            base_config, "s_formatting_test", "us-west-1", pipeline_params
        )
        expected_overrides = [
            'EmptyVpcId=""',
            "NormalParam=NormalValue",
            'SpacedParam="Value With Spaces"',
            'EqualsParam="Key=InternalValue"',
            'SpacedAndEqualsParam="Value With Spaces And Key=InternalValue"',
            'QuotedSpacedParam="\\"Quoted Value With Spaces\\""',  # Existing quotes should be escaped
        ]

        actual_overrides = final_config["default"]["deploy"]["parameters"][
            "parameter_overrides"
        ]
        assert len(actual_overrides) == len(expected_overrides)
        # Use set comparison for order-insensitivity
        assert set(actual_overrides) == set(expected_overrides)


class TestSamConfigManagerGenerate:
    @pytest.fixture(autouse=True)
    def _stop_all_mocks_before_each_test(self, mocker):
        mocker.stopall()

    @pytest.fixture
    def manager_and_fileop_mocks(
        self, mocker, temp_project_dir, create_mock_template_processor
    ):
        """Provides manager and mocks for os.remove and shutil.move."""
        mock_tp = create_mock_template_processor
        manager = SamConfigManager(
            pipeline_name="GenTestPipe",
            pipeline_description="Desc",
            default_sam_config_from_pipeline={
                "version": 0.1,
                "default": {"deploy": {"parameters": {"GlobalParam": "GlobalVal"}}},
            },
            template_processor=mock_tp,
        )
        mock_os_remove = mocker.patch("os.remove")
        mock_shutil_move = mocker.patch("shutil.move")
        return manager, mock_tp, mock_os_remove, mock_shutil_move  # 4 items

    @pytest.fixture
    def manager_real_fileops(self, temp_project_dir, create_mock_template_processor):
        """Provides manager without mocking file operations - for tests that need real file I/O."""
        mock_tp = create_mock_template_processor
        manager = SamConfigManager(
            pipeline_name="GenTestPipe",
            pipeline_description="Desc",
            default_sam_config_from_pipeline={
                "version": 0.1,
                "default": {"deploy": {"parameters": {"GlobalParam": "GlobalVal"}}},
            },
            template_processor=mock_tp,
        )
        return manager, mock_tp

    def test_generate_samconfig_greenfield(
        self, manager_and_fileop_mocks, temp_project_dir, mocker
    ):
        manager, _, _, mock_shutil_move = manager_and_fileop_mocks
        mock_yaml_dump_sut = mocker.patch("samstacks.samconfig_manager.yaml.dump")

        stack_dir = temp_project_dir / "greenfield_stack"
        stack_dir.mkdir()
        template_file = stack_dir / "template.yaml"
        template_file.touch()
        pydantic_stack = PydanticStackModel(id="s_green", dir=stack_dir.name)

        target_path = manager.generate_samconfig_for_stack(
            stack_dir=stack_dir,
            stack_id="s_green",
            pydantic_stack_model=pydantic_stack,
            deployed_stack_name="GenTestPipe-s_green",
            effective_region="us-east-1",
            resolved_stack_params={"StackParam": "ResolvedValue"},
        )

        assert target_path == stack_dir / "samconfig.yaml"
        # In a real greenfield, target_path is created by SUT calling yaml.dump
        # We can check if yaml.dump was called with a file object for this path.
        mock_shutil_move.assert_not_called()
        mock_yaml_dump_sut.assert_called_once()
        # Assertions on dumped_config (as before)
        dumped_config = mock_yaml_dump_sut.call_args[0][0]
        assert (
            dumped_config["default"]["deploy"]["parameters"]["stack_name"]
            == "GenTestPipe-s_green"
        )
        assert dumped_config["default"]["deploy"]["parameters"][
            "parameter_overrides"
        ] == ["StackParam=ResolvedValue"]
        assert dumped_config["version"] == 0.1
        assert (
            dumped_config["default"]["deploy"]["parameters"]["GlobalParam"]
            == "GlobalVal"
        )

    def test_generate_samconfig_with_toml_backup(
        self, manager_real_fileops, temp_project_dir, mocker
    ):
        manager, _ = manager_real_fileops
        mock_yaml_dump_sut = mocker.patch("samstacks.samconfig_manager.yaml.dump")

        stack_dir = temp_project_dir / "toml_backup_stack"
        stack_dir.mkdir()
        template_file = stack_dir / "template.yaml"
        template_file.touch()
        existing_toml_file = stack_dir / "samconfig.toml"
        backup_toml_file = stack_dir / "samconfig.toml.bak"

        # Create the actual toml file with content we want to test
        toml_content_as_string = """
version = 0.1

[default.deploy.parameters]
region = "from-toml-region"
capabilities = "CAPABILITY_FROM_TOML"

[default.global.parameters]
beta_features = true
"""
        existing_toml_file.write_text(toml_content_as_string)

        pydantic_stack = PydanticStackModel(id="s_toml", dir=stack_dir.name)
        manager.generate_samconfig_for_stack(
            stack_dir, "s_toml", pydantic_stack, "Pipe-s_toml", "eu-west-1", {}
        )

        # Verify the backup file was created
        assert backup_toml_file.exists()

        dumped_config = mock_yaml_dump_sut.call_args[0][0]
        assert (
            dumped_config["default"]["deploy"]["parameters"]["region"] == "eu-west-1"
        )  # Pipeline effective_region overrides TOML region
        assert (
            dumped_config["default"]["deploy"]["parameters"]["capabilities"]
            == "CAPABILITY_FROM_TOML"
        )  # Other settings preserved
        assert (
            dumped_config.get("default", {})
            .get("global", {})
            .get("parameters", {})
            .get("beta_features")
            is True
        )

    def test_generate_samconfig_with_yaml_backup(
        self, manager_real_fileops, temp_project_dir, mocker
    ):
        manager, _ = manager_real_fileops
        mock_yaml_dump_sut = mocker.patch("samstacks.samconfig_manager.yaml.dump")

        stack_dir = temp_project_dir / "yaml_backup_stack"
        stack_dir.mkdir()
        template_file = stack_dir / "template.yaml"
        template_file.touch()
        existing_yaml_file = stack_dir / "samconfig.yaml"  # This is the target path
        backup_yaml_file = stack_dir / "samconfig.yaml.bak"

        # Create the actual YAML file with content we want to test
        yaml_content_as_string = """
version: 0.2
custom_env:
  deploy:
    parameters:
      my_yaml_param: "my_yaml_val"
"""
        existing_yaml_file.write_text(yaml_content_as_string)

        pydantic_stack = PydanticStackModel(id="s_yaml", dir=stack_dir.name)
        manager.generate_samconfig_for_stack(
            stack_dir, "s_yaml", pydantic_stack, "Pipe-s_yaml", "ap-south-1", {}
        )

        # Verify the backup file was created
        assert backup_yaml_file.exists()

        dumped_config_sut = mock_yaml_dump_sut.call_args[0][0]
        # Pipeline configuration takes precedence, so version should be 0.1 from pipeline defaults
        assert dumped_config_sut["version"] == 0.1
        # But custom sections from local YAML should be preserved
        assert (
            dumped_config_sut["custom_env"]["deploy"]["parameters"]["my_yaml_param"]
            == "my_yaml_val"
        )
        # And pipeline defaults should also be present
        assert (
            dumped_config_sut["default"]["deploy"]["parameters"]["GlobalParam"]
            == "GlobalVal"
        )

    def test_generate_samconfig_with_stack_overrides(
        self, manager_and_fileop_mocks, temp_project_dir, mocker
    ):
        manager, mock_tp, _, _ = (
            manager_and_fileop_mocks  # Corrected unpacking - only 4 items
        )
        mock_yaml_dump_sut = mocker.patch("samstacks.samconfig_manager.yaml.dump")

        stack_dir = temp_project_dir / "override_stack"
        stack_dir.mkdir()
        template_file = stack_dir / "template.yaml"
        template_file.touch()

        stack_specific_sam_config = {
            "default": {
                "deploy": {
                    "parameters": {
                        "StackSpecificParam": "StackVal",
                        "region": "override-region",
                    }
                }
            },
            "another_env": {"build": {"parameters": {"UseContainer": True}}},
            "version": 0.3,
        }
        pydantic_stack = PydanticStackModel(
            id="s4", dir=stack_dir.name, sam_config_overrides=stack_specific_sam_config
        )
        manager.generate_samconfig_for_stack(
            stack_dir=stack_dir,
            stack_id="s4",
            pydantic_stack_model=pydantic_stack,
            deployed_stack_name="Pipe-s4",
            effective_region=None,
            resolved_stack_params={},
        )
        mock_tp.process_structure.assert_called_once()
        dumped_config = mock_yaml_dump_sut.call_args[0][0]
        assert dumped_config["version"] == 0.3
        assert (
            dumped_config["default"]["deploy"]["parameters"]["GlobalParam"]
            == "GlobalVal"
        )
        assert (
            dumped_config["default"]["deploy"]["parameters"]["StackSpecificParam"]
            == "StackVal"
        )
        assert (
            dumped_config["default"]["deploy"]["parameters"]["region"]
            == "override-region"
        )
        assert (
            dumped_config["another_env"]["build"]["parameters"]["UseContainer"] is True
        )

    def test_generate_samconfig_write_failure(
        self, manager_and_fileop_mocks, temp_project_dir, mocker
    ):
        manager, _, _, _ = (
            manager_and_fileop_mocks  # Corrected unpacking - only 4 items
        )
        mocker.patch(
            "samstacks.samconfig_manager.yaml.dump",
            side_effect=yaml.YAMLError("Failed to dump"),
        )

        stack_dir = temp_project_dir / "fail_stack"
        stack_dir.mkdir()
        template_file = stack_dir / "template.yaml"
        template_file.touch()
        pydantic_stack = PydanticStackModel(id="s_fail", dir=stack_dir.name)

        with pytest.raises(ManifestError, match="Failed to write samconfig.yaml"):
            manager.generate_samconfig_for_stack(
                stack_dir=stack_dir,
                stack_id="s_fail",
                pydantic_stack_model=pydantic_stack,
                deployed_stack_name="Pipe-fail",
                effective_region=None,
                resolved_stack_params={},
            )
