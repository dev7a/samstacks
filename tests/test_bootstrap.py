"""
Unit tests for the samstacks.bootstrap module.
"""

import pytest
import yaml
from pathlib import Path
import os
from typing import Optional, Dict, Any, List

from samstacks.bootstrap import BootstrapManager, DiscoveredStack
from samstacks.exceptions import SamStacksError

# The temp_project_dir fixture is now defined in tests/conftest.py
# and will be automatically available to tests in this file.


class TestBootstrapManagerDiscoverStacks:
    def test_discover_stacks_no_templates_found(self, temp_project_dir: Path):
        """Test discovery when no SAM templates are present."""
        manager = BootstrapManager(scan_path=str(temp_project_dir))
        manager._discover_stacks()  # Call the private method directly for focused testing
        assert not manager.discovered_stacks
        # Test log message (optional, requires caplog fixture)

    def test_discover_stacks_simple_discovery_one_stack(self, temp_project_dir: Path):
        """Test discovery of a single stack with template.yaml and samconfig.toml."""
        stack1_dir = temp_project_dir / "stack_alpha"
        stack1_dir.mkdir()
        (stack1_dir / "template.yaml").write_text(
            "AWSTemplateFormatVersion: '2010-09-09'\nResources:\n  MyBucket: {Type: AWS::S3::Bucket}"
        )
        (stack1_dir / "samconfig.toml").write_text("version = 0.1")

        manager = BootstrapManager(scan_path=str(temp_project_dir))
        manager._discover_stacks()

        assert len(manager.discovered_stacks) == 1
        stack = manager.discovered_stacks[0]
        assert (
            stack.id == "stack-alpha"
        )  # CloudFormation-compatible (hyphens not underscores)
        assert stack.abs_dir_path == stack1_dir.resolve()
        assert Path(stack.relative_dir_path) == Path(
            "stack_alpha"
        )  # Relative to temp_project_dir (scan_path)
        assert stack.template_path.name == "template.yaml"
        assert stack.samconfig_path is not None
        assert stack.samconfig_path.name == "samconfig.toml"

    def test_discover_stacks_template_yml_discovery(self, temp_project_dir: Path):
        """Test discovery of a stack with template.yml."""
        stack_dir = temp_project_dir / "stack_beta"
        stack_dir.mkdir()
        (stack_dir / "template.yml").write_text(
            "AWSTemplateFormatVersion: '2010-09-09'"
        )

        manager = BootstrapManager(scan_path=str(temp_project_dir))
        manager._discover_stacks()

        assert len(manager.discovered_stacks) == 1
        assert manager.discovered_stacks[0].id == "stack-beta"
        assert manager.discovered_stacks[0].template_path.name == "template.yml"

    def test_discover_stacks_multiple_stacks_mixed_samconfig(
        self, temp_project_dir: Path
    ):
        """Test discovery of multiple stacks, some with and some without samconfig.toml."""
        # Stack 1 (with samconfig)
        stack1_dir = temp_project_dir / "s1_with_config"
        stack1_dir.mkdir()
        (stack1_dir / "template.yaml").touch()
        (stack1_dir / "samconfig.toml").touch()

        # Stack 2 (without samconfig)
        stack2_dir = temp_project_dir / "s2_no_config"
        stack2_dir.mkdir()
        (stack2_dir / "template.yaml").touch()

        # Stack 3 (nested, with samconfig)
        nested_parent_dir = temp_project_dir / "parent_dir"
        nested_parent_dir.mkdir()
        stack3_dir = nested_parent_dir / "s3_nested_with_config"
        stack3_dir.mkdir()
        (stack3_dir / "template.yml").touch()
        (stack3_dir / "samconfig.toml").touch()

        manager = BootstrapManager(scan_path=str(temp_project_dir))
        manager._discover_stacks()

        assert len(manager.discovered_stacks) == 3
        ids = sorted([s.id for s in manager.discovered_stacks])
        assert ids == sorted(
            ["s1-with-config", "s2-no-config", "s3-nested-with-config"]
        )

        s1 = next(s for s in manager.discovered_stacks if s.id == "s1-with-config")
        s2 = next(s for s in manager.discovered_stacks if s.id == "s2-no-config")
        s3 = next(
            s for s in manager.discovered_stacks if s.id == "s3-nested-with-config"
        )

        assert s1.samconfig_path is not None
        assert s2.samconfig_path is None
        assert s3.samconfig_path is not None

        assert Path(s1.relative_dir_path) == Path("s1_with_config")
        assert Path(s2.relative_dir_path) == Path("s2_no_config")
        assert Path(s3.relative_dir_path) == Path("parent_dir/s3_nested_with_config")

    def test_discover_stacks_id_sanitization_and_uniqueness(
        self, temp_project_dir: Path
    ):
        """Test stack ID sanitization and uniqueness generation."""
        # Names that need sanitization
        (temp_project_dir / "stack with spaces").mkdir()
        ((temp_project_dir / "stack with spaces") / "template.yaml").touch()

        (temp_project_dir / "01_numeric_start").mkdir()
        ((temp_project_dir / "01_numeric_start") / "template.yaml").touch()

        # Names that might become duplicates after sanitization
        (temp_project_dir / "my-stack").mkdir()
        ((temp_project_dir / "my-stack") / "template.yaml").touch()
        (temp_project_dir / "my_stack").mkdir()  # Will also sanitize to my_stack
        ((temp_project_dir / "my_stack") / "template.yaml").touch()

        manager = BootstrapManager(scan_path=str(temp_project_dir))
        manager._discover_stacks()

        ids = sorted([s.id for s in manager.discovered_stacks])
        print(f"Generated IDs: {ids}")

        assert "stack-with-spaces" in ids
        assert "stack-01-numeric-start" in ids  # Number start gets "stack-" prefix
        # my-stack and my_stack both become similar after sanitization, so one gets uniqueness suffix
        assert "my-stack" in ids
        assert "my-stack-1" in ids  # Uniqueness counter with hyphen
        assert len(ids) == 4

    def test_discover_stacks_duplicate_templates_in_same_dir(
        self, temp_project_dir: Path
    ):
        """Test that a directory with both template.yaml and template.yml is processed once."""
        stack_dir = temp_project_dir / "dual_templates"
        stack_dir.mkdir()
        (
            stack_dir / "template.yaml"
        ).touch()  # Should be preferred due to pattern order
        (stack_dir / "template.yml").touch()

        manager = BootstrapManager(scan_path=str(temp_project_dir))
        manager._discover_stacks()

        assert len(manager.discovered_stacks) == 1
        stack = manager.discovered_stacks[0]
        assert stack.id == "dual-templates"
        assert (
            stack.template_path.name == "template.yaml"
        )  # Verifies which one was picked

    def test_discover_stacks_output_file_in_subdir(self, temp_project_dir: Path):
        """Test relative path calculation when output_file is in a subdirectory."""
        stack1_dir = temp_project_dir / "stack_zeta"
        stack1_dir.mkdir()
        (stack1_dir / "template.yaml").touch()

        output_subdir = temp_project_dir / "output_configs"
        output_subdir.mkdir()
        output_file_name = "generated_pipeline.yml"

        manager = BootstrapManager(
            scan_path=str(temp_project_dir),
            output_file=str(output_subdir / output_file_name),  # Path object to string
        )
        # Manually set output_file_path as it's normally set in __init__
        # using scan_path / output_file_name_only if output_file is just a name.
        # If output_file is a path (as intended by bootstrap plan), it should be relative to scan_path or absolute.
        # For this test, we assume output_file constructor logic correctly resolves it or it's passed as absolute.
        # The crucial part is relative_dir_path calculation *from* output_file_path.parent
        manager.output_file_path = (output_subdir / output_file_name).resolve()

        manager._discover_stacks()

        assert len(manager.discovered_stacks) == 1
        stack = manager.discovered_stacks[0]
        assert stack.id == "stack-zeta"

        # Expected: stack_zeta is at temp_project_dir/stack_zeta
        # scan_path is temp_project_dir
        # Relative path from temp_project_dir to temp_project_dir/stack_zeta is "stack_zeta"
        expected_rel_path = Path("stack_zeta")
        assert Path(stack.relative_dir_path) == expected_rel_path, (
            f"Expected {expected_rel_path}, got {Path(stack.relative_dir_path)}"
        )

    # TODO: Add tests for default_stack_id_source = "samconfig_stack_name" once _analyze_stacks is testable


class TestBootstrapManagerAnalyzeStacks:
    @pytest.fixture
    def manager_with_discovered_stack(
        self, temp_project_dir: Path, mocker
    ) -> BootstrapManager:
        """Provides a BootstrapManager with a single mock DiscoveredStack and basic files."""
        manager = BootstrapManager(scan_path=str(temp_project_dir))

        stack_dir = temp_project_dir / "analyzed_stack"
        stack_dir.mkdir()
        template_file = stack_dir / "template.yaml"
        samconfig_file = stack_dir / "samconfig.toml"

        # Create dummy DiscoveredStack object (as if _discover_stacks ran)
        discovered_stack = DiscoveredStack(
            abs_dir_path=stack_dir,
            template_path=template_file,
            samconfig_path=samconfig_file,
        )
        discovered_stack.id = (
            "analyzed_stack"  # Pre-assign ID for simplicity in this fixture
        )
        discovered_stack.relative_dir_path = "analyzed_stack"
        manager.discovered_stacks = [discovered_stack]
        return manager

    def test_analyze_stacks_valid_template_and_samconfig(
        self, manager_with_discovered_stack: BootstrapManager
    ):
        manager = manager_with_discovered_stack
        stack_obj = manager.discovered_stacks[0]

        # Create content for files
        template_content = {
            "AWSTemplateFormatVersion": "2010-09-09",
            "Parameters": {
                "Param1": {"Type": "String"},
                "Param2": {"Type": "Number", "Default": 123},
            },
            "Outputs": {"Output1": {"Value": "Val1"}, "Output2": {"Value": "Val2"}},
        }
        samconfig_content = (
            'version = 0.1\n[default.deploy.parameters]\nstack_name = "MySamStackName"'
        )

        stack_obj.template_path.write_text(yaml.dump(template_content))
        stack_obj.samconfig_path.write_text(samconfig_content)

        manager._analyze_stacks()

        assert stack_obj.template_data == template_content
        assert "Param1" in stack_obj.parameters
        assert stack_obj.parameters["Param1"]["Type"] == "String"
        assert "Param2" in stack_obj.parameters
        assert stack_obj.parameters["Param2"]["Type"] == "Number"
        assert stack_obj.parameters["Param2"]["Default"] == 123
        assert stack_obj.outputs == {"Output1", "Output2"}

        assert stack_obj.samconfig_data is not None
        assert stack_obj.samconfig_data["version"] == 0.1
        assert (
            stack_obj.samconfig_data["default"]["deploy"]["parameters"]["stack_name"]
            == "MySamStackName"
        )

    def test_analyze_stacks_template_no_params_no_outputs(
        self, manager_with_discovered_stack: BootstrapManager
    ):
        manager = manager_with_discovered_stack
        stack_obj = manager.discovered_stacks[0]

        template_content = {
            "AWSTemplateFormatVersion": "2010-09-09",
            "Resources": {"R1": {"Type": "AWS::S3::Bucket"}},
        }
        stack_obj.template_path.write_text(yaml.dump(template_content))
        # No samconfig for this test
        if stack_obj.samconfig_path.exists():
            os.remove(stack_obj.samconfig_path)
        stack_obj.samconfig_path = None

        manager._analyze_stacks()

        assert not stack_obj.parameters
        assert not stack_obj.outputs
        assert stack_obj.samconfig_data is None

    def test_analyze_stacks_missing_samconfig_file(
        self, manager_with_discovered_stack: BootstrapManager
    ):
        manager = manager_with_discovered_stack
        stack_obj = manager.discovered_stacks[0]

        stack_obj.template_path.write_text("AWSTemplateFormatVersion: '2010-09-09'")
        # Ensure samconfig.toml does not exist, even if path was set
        if stack_obj.samconfig_path and stack_obj.samconfig_path.exists():
            os.remove(stack_obj.samconfig_path)
        # stack_obj.samconfig_path might still point to non-existent file, _analyze_stacks should handle

        manager._analyze_stacks()
        assert stack_obj.samconfig_data is None
        assert (
            stack_obj.samconfig_path is None
        )  # Should be reset if not found during analysis

    def test_analyze_stacks_invalid_template_yaml(
        self, manager_with_discovered_stack: BootstrapManager, caplog
    ):
        manager = manager_with_discovered_stack
        stack_obj = manager.discovered_stacks[0]

        stack_obj.template_path.write_text("Resources: R1: Type: Invalid YAML ::")
        if stack_obj.samconfig_path.exists():
            os.remove(stack_obj.samconfig_path)
        stack_obj.samconfig_path = None

        manager._analyze_stacks()  # Should log error and skip/continue

        assert f"Error parsing YAML template for stack {stack_obj.id}" in caplog.text
        # Depending on error strategy, params/outputs might be empty or stack removed
        # Current impl. continues, so check for empty (or potentially defaults if we add them)
        assert not stack_obj.parameters
        assert not stack_obj.outputs

    def test_analyze_stacks_invalid_samconfig_toml(
        self, manager_with_discovered_stack: BootstrapManager, caplog
    ):
        manager = manager_with_discovered_stack
        stack_obj = manager.discovered_stacks[0]

        stack_obj.template_path.write_text("AWSTemplateFormatVersion: '2010-09-09'")
        stack_obj.samconfig_path.write_text(
            "version = 0.1\ninvalid_toml_entry = [eke"
        )  # Invalid TOML

        manager._analyze_stacks()

        # The exact error message from tomllib might vary slightly based on content/version
        # We should check for the core part of our logging
        assert f"Error parsing samconfig file {stack_obj.samconfig_path}" in caplog.text
        assert stack_obj.samconfig_data is None  # Should be None after parsing error

    def test_analyze_stacks_template_file_not_found(
        self, manager_with_discovered_stack: BootstrapManager, caplog
    ):
        manager = manager_with_discovered_stack
        stack_obj = manager.discovered_stacks[0]

        if stack_obj.template_path.exists():
            os.remove(stack_obj.template_path)
        # No need to remove samconfig, as template parsing failure should cause stack to be skipped

        # Modify the list in place for the test as _analyze_stacks iterates over it
        # If a stack is skipped, it would still be in self.discovered_stacks but perhaps without data
        # For this test, we want to see the error logged and that it continues for other stacks (if any)
        manager._analyze_stacks()

        assert f"Template file not found for stack {stack_obj.id}" in caplog.text
        # Assert that stack_obj has empty data because it was skipped
        assert not stack_obj.template_data
        assert not stack_obj.parameters
        assert not stack_obj.outputs

    def test_analyze_stacks_refine_id_from_samconfig(self, temp_project_dir: Path):
        """Test stack ID refinement using default_stack_id_source = samconfig_stack_name."""
        # Setup: Two stacks, one will get ID from samconfig, other from dir
        stack1_dir = temp_project_dir / "original_dir_id_1"
        stack1_dir.mkdir()
        (stack1_dir / "template.yaml").write_text("Resources: {R1: {Type: S3}}")
        (stack1_dir / "samconfig.toml").write_text(
            'version = 0.1\n[default.deploy.parameters]\nstack_name = "MyCustomStackName"'
        )

        stack2_dir = temp_project_dir / "original_dir_id_2"
        stack2_dir.mkdir()
        (stack2_dir / "template.yaml").write_text("Resources: {R2: {Type: SQS}}")
        # No samconfig for stack2, or one without stack_name

        manager = BootstrapManager(
            scan_path=str(temp_project_dir),
            default_stack_id_source="samconfig_stack_name",  # KEY SETTING FOR THIS TEST
        )
        manager._discover_stacks()  # Initial discovery (IDs will be dir-based)
        # Manually check initial IDs for clarity before _analyze_stacks refines them
        initial_s1 = next(
            s for s in manager.discovered_stacks if s.abs_dir_path == stack1_dir
        )
        initial_s2 = next(
            s for s in manager.discovered_stacks if s.abs_dir_path == stack2_dir
        )
        assert initial_s1.id == "original-dir-id-1"
        assert initial_s2.id == "original-dir-id-2"

        manager._analyze_stacks()  # This should parse samconfig and refine IDs

        assert len(manager.discovered_stacks) == 2

        s1_final = next(
            s for s in manager.discovered_stacks if s.abs_dir_path == stack1_dir
        )  # Find by path
        s2_final = next(
            s for s in manager.discovered_stacks if s.abs_dir_path == stack2_dir
        )

        assert s1_final.id == "MyCustomStackName"  # ID should be from samconfig
        assert s2_final.id == "original-dir-id-2"  # ID should remain dir-based

    def test_analyze_stacks_refine_id_uniqueness_from_samconfig(
        self, temp_project_dir: Path
    ):
        """Test ID uniqueness when multiple samconfigs suggest the same stack_name."""
        stack1_dir = temp_project_dir / "dir1"
        stack1_dir.mkdir()
        (stack1_dir / "template.yaml").touch()
        (stack1_dir / "samconfig.toml").write_text(
            '[default.deploy.parameters]\nstack_name = "SharedName"'
        )

        stack2_dir = temp_project_dir / "dir2"
        stack2_dir.mkdir()
        (stack2_dir / "template.yaml").touch()
        (stack2_dir / "samconfig.toml").write_text(
            '[default.deploy.parameters]\nstack_name = "SharedName"'
        )  # Same stack_name

        stack3_dir = (
            temp_project_dir / "SharedName"
        )  # Dir name that clashes after sanitization
        stack3_dir.mkdir()
        (stack3_dir / "template.yaml").touch()
        # No samconfig for stack3, so its ID will be dir-based initially

        manager = BootstrapManager(
            scan_path=str(temp_project_dir),
            default_stack_id_source="samconfig_stack_name",
        )
        manager._discover_stacks()  # IDs initially: dir1, dir2, SharedName
        manager._analyze_stacks()  # IDs refined: SharedName, SharedName-1, SharedName-2 (or similar)

        ids = sorted([s.id for s in manager.discovered_stacks])
        print(f"Refined IDs: {ids}")
        assert len(ids) == 3
        assert "SharedName" in ids
        assert "SharedName-1" in ids
        assert "SharedName-2" in ids

    # TODO: Test cases for invalid Parameters/Outputs sections (not dicts)
    # TODO: Test case for parameters with no Type (should default to String)


class TestBootstrapManagerConsolidateSamconfigs:
    @pytest.fixture
    def manager_no_stacks(self, temp_project_dir: Path) -> BootstrapManager:
        return BootstrapManager(scan_path=str(temp_project_dir))

    @pytest.fixture
    def create_discovered_stack(self, temp_project_dir: Path):
        """Factory fixture to create a DiscoveredStack with minimal valid paths."""

        def _create(
            id: str, samconfig_data: Optional[Dict[str, Any]] = None
        ) -> DiscoveredStack:
            stack_dir = temp_project_dir / id
            stack_dir.mkdir(exist_ok=True)
            template_path = stack_dir / "template.yaml"
            template_path.touch()  # Needs to exist for some other parts if bootstrap_pipeline is called

            ds = DiscoveredStack(abs_dir_path=stack_dir, template_path=template_path)
            ds.id = id
            ds.samconfig_data = samconfig_data
            return ds

        return _create

    def test_consolidate_no_samconfigs(self, manager_no_stacks: BootstrapManager):
        manager = manager_no_stacks
        manager.discovered_stacks = []  # Explicitly empty
        default_cfg, overrides_cfg = manager._consolidate_samconfigs()
        assert default_cfg is None
        assert overrides_cfg == {}

    def test_consolidate_one_stack_with_samconfig(
        self, manager_no_stacks: BootstrapManager, create_discovered_stack
    ):
        manager = manager_no_stacks
        samconfig_content = {
            "version": 0.1,
            "default": {
                "deploy": {
                    "parameters": {
                        "region": "us-east-1",
                        "capabilities": "CAPABILITY_IAM",
                    }
                }
            },
        }
        stack1 = create_discovered_stack(id="s1", samconfig_data=samconfig_content)
        manager.discovered_stacks = [stack1]

        default_cfg, overrides_cfg = manager._consolidate_samconfigs()

        expected_default = {
            "version": 0.1,
            "default": {
                "deploy": {
                    "parameters": {
                        "region": "us-east-1",
                        "capabilities": "CAPABILITY_IAM",
                    }
                }
            },
        }
        assert default_cfg == expected_default
        assert overrides_cfg.get("s1") == {}  # No overrides if it all went to default

    def test_consolidate_all_settings_common(
        self, manager_no_stacks: BootstrapManager, create_discovered_stack
    ):
        manager = manager_no_stacks
        common_content = {
            "version": 0.1,
            "default": {"deploy": {"parameters": {"region": "us-west-2"}}},
        }
        stack1 = create_discovered_stack(
            id="s1", samconfig_data=yaml.safe_load(yaml.safe_dump(common_content))
        )
        stack2 = create_discovered_stack(
            id="s2", samconfig_data=yaml.safe_load(yaml.safe_dump(common_content))
        )
        manager.discovered_stacks = [stack1, stack2]

        default_cfg, overrides_cfg = manager._consolidate_samconfigs()
        assert default_cfg == common_content
        assert overrides_cfg.get("s1") == {}
        assert overrides_cfg.get("s2") == {}

    def test_consolidate_no_settings_common(
        self, manager_no_stacks: BootstrapManager, create_discovered_stack
    ):
        manager = manager_no_stacks
        config1 = {
            "version": 0.1,
            "default": {"deploy": {"parameters": {"region": "us-east-1"}}},
        }
        config2 = {"version": 0.2, "prod": {"build": {"parameters": {"cached": True}}}}
        stack1 = create_discovered_stack(id="s1", samconfig_data=config1)
        stack2 = create_discovered_stack(id="s2", samconfig_data=config2)
        manager.discovered_stacks = [stack1, stack2]

        default_cfg, overrides_cfg = manager._consolidate_samconfigs()
        assert (
            default_cfg is None
        )  # Or empty dict, depends on _intersect_configs strictness

        # Everything becomes an override if nothing is common
        assert overrides_cfg.get("s1") == config1
        assert overrides_cfg.get("s2") == config2

    def test_consolidate_mixed_common_and_specific(
        self, manager_no_stacks: BootstrapManager, create_discovered_stack
    ):
        manager = manager_no_stacks
        config1 = {
            "version": 0.1,
            "default": {
                "deploy": {
                    "parameters": {
                        "region": "us-east-1",
                        "capabilities": "CAPABILITY_IAM",
                    }
                }
            },
            "prod_env": {"deploy": {"parameters": {"timeout": 300}}},
        }
        config2 = {
            "version": 0.1,
            "default": {
                "deploy": {
                    "parameters": {
                        "region": "us-east-1",
                        "capabilities": "CAPABILITY_NAMED_IAM",
                    }
                }
            },
            "dev_env": {"deploy": {"parameters": {"memory": 512}}},
        }
        stack1 = create_discovered_stack(id="s1", samconfig_data=config1)
        stack2 = create_discovered_stack(id="s2", samconfig_data=config2)
        manager.discovered_stacks = [stack1, stack2]

        default_cfg, overrides_cfg = manager._consolidate_samconfigs()

        expected_default = {
            "version": 0.1,
            "default": {
                "deploy": {"parameters": {"region": "us-east-1"}}
            },  # Only version and region are common
        }
        assert default_cfg == expected_default

        expected_s1_overrides = {
            "default": {"deploy": {"parameters": {"capabilities": "CAPABILITY_IAM"}}},
            "prod_env": {"deploy": {"parameters": {"timeout": 300}}},
        }
        expected_s2_overrides = {
            "default": {
                "deploy": {"parameters": {"capabilities": "CAPABILITY_NAMED_IAM"}}
            },
            "dev_env": {"deploy": {"parameters": {"memory": 512}}},
        }
        assert overrides_cfg.get("s1") == expected_s1_overrides
        assert overrides_cfg.get("s2") == expected_s2_overrides

    def test_consolidate_globally_skipped_fields_are_ignored(
        self, manager_no_stacks: BootstrapManager, create_discovered_stack
    ):
        manager = manager_no_stacks
        config_with_skipped = {
            "version": 0.1,
            "default": {
                "deploy": {
                    "parameters": {
                        "region": "us-east-1",
                        "stack_name": "my-stack",  # Should be skipped
                        "s3_prefix": "my-prefix",  # Should be skipped
                        "parameter_overrides": {"MyParam": "Val"},  # Should be skipped
                        "tags": {"MyTag": "TagVal"},  # Should be skipped
                    }
                }
            },
        }
        stack1 = create_discovered_stack(
            id="s1", samconfig_data=yaml.safe_load(yaml.safe_dump(config_with_skipped))
        )
        stack2 = create_discovered_stack(
            id="s2", samconfig_data=yaml.safe_load(yaml.safe_dump(config_with_skipped))
        )
        manager.discovered_stacks = [stack1, stack2]

        default_cfg, overrides_cfg = manager._consolidate_samconfigs()

        expected_default_after_skips = {
            "version": 0.1,
            "default": {"deploy": {"parameters": {"region": "us-east-1"}}},
        }
        assert default_cfg == expected_default_after_skips
        # Overrides should be empty as all non-skipped fields were common
        assert overrides_cfg.get("s1") == {}
        assert overrides_cfg.get("s2") == {}

    def test_consolidate_deeply_nested_common_and_diff(
        self, manager_no_stacks: BootstrapManager, create_discovered_stack
    ):
        manager = manager_no_stacks
        config1 = {
            "env1": {"cmd1": {"params": {"p1": "common", "p2": "val1"}}},
            "common_key": "common_value",
        }
        config2 = {
            "env1": {"cmd1": {"params": {"p1": "common", "p2": "val2"}}},
            "common_key": "common_value",
        }
        stack1 = create_discovered_stack(id="s1", samconfig_data=config1)
        stack2 = create_discovered_stack(id="s2", samconfig_data=config2)
        manager.discovered_stacks = [stack1, stack2]

        default_cfg, overrides_cfg = manager._consolidate_samconfigs()

        expected_default = {
            "env1": {"cmd1": {"params": {"p1": "common"}}},
            "common_key": "common_value",
        }
        assert default_cfg == expected_default

        expected_s1_overrides = {"env1": {"cmd1": {"params": {"p2": "val1"}}}}
        expected_s2_overrides = {"env1": {"cmd1": {"params": {"p2": "val2"}}}}
        assert overrides_cfg.get("s1") == expected_s1_overrides
        assert overrides_cfg.get("s2") == expected_s2_overrides

    def test_consolidate_with_default_global_parameters(
        self, manager_no_stacks: BootstrapManager, create_discovered_stack
    ):
        manager = manager_no_stacks
        config1 = {
            "version": 0.1,
            "default": {
                "global": {
                    "parameters": {"beta_features": True, "common_global": "val"}
                },
                "deploy": {"parameters": {"region": "us-east-1"}},
            },
        }
        config2 = {
            "version": 0.1,
            "default": {
                "global": {
                    "parameters": {"beta_features": True, "common_global": "val"}
                },
                "deploy": {
                    "parameters": {
                        "region": "us-east-1",
                        "capabilities": "CAPABILITY_IAM",
                    }
                },
            },
        }
        stack1 = create_discovered_stack(id="s1", samconfig_data=config1)
        stack2 = create_discovered_stack(id="s2", samconfig_data=config2)
        manager.discovered_stacks = [stack1, stack2]

        default_cfg, overrides_cfg = manager._consolidate_samconfigs()

        expected_default = {
            "version": 0.1,
            "default": {
                "global": {
                    "parameters": {"beta_features": True, "common_global": "val"}
                },
                "deploy": {"parameters": {"region": "us-east-1"}},
            },
        }
        assert default_cfg == expected_default
        assert overrides_cfg.get("s1") == {}
        expected_s2_overrides = {
            "default": {"deploy": {"parameters": {"capabilities": "CAPABILITY_IAM"}}}
        }
        assert overrides_cfg.get("s2") == expected_s2_overrides


class TestBootstrapManagerInferDependencies:
    @pytest.fixture
    def manager(self, temp_project_dir: Path) -> BootstrapManager:
        # Create a manager instance; actual stack discovery isn't the focus here,
        # so we'll populate manager.discovered_stacks manually in each test.
        return BootstrapManager(scan_path=str(temp_project_dir))

    def _create_stack(
        self, id: str, params: List[str], outputs: List[str], tmp_path: Path
    ) -> DiscoveredStack:
        """Helper to create a DiscoveredStack object for dependency testing."""
        # Create minimal dummy paths as DiscoveredStack expects them
        stack_dir = tmp_path / id
        stack_dir.mkdir(exist_ok=True)
        template_file = stack_dir / "template.yaml"
        template_file.touch()

        ds = DiscoveredStack(abs_dir_path=stack_dir, template_path=template_file)
        ds.id = id
        ds.parameters = {p: {"Type": "String"} for p in params}
        ds.outputs = set(outputs)
        return ds

    def test_infer_no_stacks(self, manager: BootstrapManager):
        manager.discovered_stacks = []
        ordered_stacks, inferred_params = manager._infer_dependencies_and_order()
        assert ordered_stacks == []
        assert inferred_params == {}

    def test_infer_no_dependencies(
        self, manager: BootstrapManager, temp_project_dir: Path
    ):
        s1 = self._create_stack("s1", ["P1"], ["O1"], temp_project_dir)
        s2 = self._create_stack("s2", ["P2"], ["O2"], temp_project_dir)
        manager.discovered_stacks = [
            s1,
            s2,
        ]  # Order might change due to internal sorting by ID

        ordered_stacks, inferred_params = manager._infer_dependencies_and_order()

        assert len(ordered_stacks) == 2
        # Order between s1 and s2 is not strictly defined if no dependencies, depends on initial sort
        assert {s.id for s in ordered_stacks} == {"s1", "s2"}
        assert inferred_params.get("s1", {}) == {}
        assert inferred_params.get("s2", {}) == {}

    def test_infer_simple_linear_dependency(
        self, manager: BootstrapManager, temp_project_dir: Path
    ):
        # s1 -> s2 (s2.ParamA depends on s1.OutputA)
        s1 = self._create_stack("s1", [], ["OutputA"], temp_project_dir)
        s2 = self._create_stack("s2", ["OutputA"], [], temp_project_dir)
        manager.discovered_stacks = [s2, s1]  # Intentionally out of order

        ordered_stacks, inferred_params = manager._infer_dependencies_and_order()

        assert [s.id for s in ordered_stacks] == ["s1", "s2"]
        assert inferred_params["s2"]["OutputA"] == "${{ stacks.s1.outputs.OutputA }}"
        assert "s1" not in inferred_params or not inferred_params["s1"]

    def test_infer_one_producer_multiple_consumers(
        self, manager: BootstrapManager, temp_project_dir: Path
    ):
        # s1 -> s2 (s2.P depends on s1.O)
        # s1 -> s3 (s3.P depends on s1.O)
        s1 = self._create_stack("s1", [], ["O"], temp_project_dir)
        s2 = self._create_stack("s2", ["O"], [], temp_project_dir)
        s3 = self._create_stack("s3", ["O"], [], temp_project_dir)
        manager.discovered_stacks = [s3, s2, s1]  # Out of order

        ordered_stacks, inferred_params = manager._infer_dependencies_and_order()
        ordered_ids = [s.id for s in ordered_stacks]

        assert ordered_ids[0] == "s1"
        assert set(ordered_ids[1:]) == {"s2", "s3"}  # s2, s3 order might vary
        assert inferred_params["s2"]["O"] == "${{ stacks.s1.outputs.O }}"
        assert inferred_params["s3"]["O"] == "${{ stacks.s1.outputs.O }}"

    def test_infer_multiple_producers_one_consumer(
        self, manager: BootstrapManager, temp_project_dir: Path
    ):
        # s1 -> s3 (s3.P1 depends on s1.O1)
        # s2 -> s3 (s3.P2 depends on s2.O2)
        s1 = self._create_stack("s1", [], ["O1"], temp_project_dir)
        s2 = self._create_stack("s2", [], ["O2"], temp_project_dir)
        s3 = self._create_stack("s3", ["O1", "O2"], [], temp_project_dir)
        manager.discovered_stacks = [s3, s1, s2]

        ordered_stacks, inferred_params = manager._infer_dependencies_and_order()
        ordered_ids = [s.id for s in ordered_stacks]

        assert ordered_ids[2] == "s3"
        assert set(ordered_ids[:2]) == {"s1", "s2"}
        assert inferred_params["s3"]["O1"] == "${{ stacks.s1.outputs.O1 }}"
        assert inferred_params["s3"]["O2"] == "${{ stacks.s2.outputs.O2 }}"

    def test_infer_cycle_detection(
        self, manager: BootstrapManager, temp_project_dir: Path
    ):
        # s1 -> s2 (s2.P1 from s1.O1)
        # s2 -> s1 (s1.P2 from s2.O2)
        s1 = self._create_stack("s1", ["O2"], ["O1"], temp_project_dir)
        s2 = self._create_stack("s2", ["O1"], ["O2"], temp_project_dir)
        manager.discovered_stacks = [s1, s2]

        with pytest.raises(SamStacksError, match="circular dependencies"):
            manager._infer_dependencies_and_order()

    def test_infer_ambiguous_dependency(
        self, manager: BootstrapManager, temp_project_dir: Path
    ):
        # s1 outputs X, s2 outputs X. s3 needs param X.
        s1 = self._create_stack("s1", [], ["X"], temp_project_dir)
        s2 = self._create_stack("s2", [], ["X"], temp_project_dir)
        s3 = self._create_stack("s3", ["X"], [], temp_project_dir)
        manager.discovered_stacks = [s1, s2, s3]

        with pytest.raises(SamStacksError, match="ambiguous dependencies") as excinfo:
            manager._infer_dependencies_and_order()

        assert "Parameter 'X' in stack 's3' has ambiguous sources" in str(excinfo.value)
        # Order of s1, s2 in the error message might vary, check for both
        assert "s1" in str(excinfo.value) and "s2" in str(excinfo.value)

    def test_infer_diamond_dependency(
        self, manager: BootstrapManager, temp_project_dir: Path
    ):
        #    s1
        #   /  \
        #  s2   s3
        #   \  /
        #    s4
        # s1: OutO1
        # s2: ParamP1 (from s1.OutO1), OutO2
        # s3: ParamP1 (from s1.OutO1), OutO3
        # s4: ParamP2 (from s2.OutO2), ParamP3 (from s3.OutO3)
        s1 = self._create_stack("s1", [], ["OutO1"], temp_project_dir)
        s2 = self._create_stack("s2", ["OutO1"], ["OutO2"], temp_project_dir)
        s3 = self._create_stack("s3", ["OutO1"], ["OutO3"], temp_project_dir)
        s4 = self._create_stack("s4", ["OutO2", "OutO3"], [], temp_project_dir)
        manager.discovered_stacks = [s4, s2, s3, s1]  # Out of order

        ordered_stacks, inferred_params = manager._infer_dependencies_and_order()
        ordered_ids = [s.id for s in ordered_stacks]

        assert ordered_ids[0] == "s1"
        assert set(ordered_ids[1:3]) == {
            "s2",
            "s3",
        }  # s2 and s3 can be in any order relative to each other
        assert ordered_ids[3] == "s4"

        assert inferred_params["s2"]["OutO1"] == "${{ stacks.s1.outputs.OutO1 }}"
        assert inferred_params["s3"]["OutO1"] == "${{ stacks.s1.outputs.OutO1 }}"
        assert inferred_params["s4"]["OutO2"] == "${{ stacks.s2.outputs.OutO2 }}"
        assert inferred_params["s4"]["OutO3"] == "${{ stacks.s3.outputs.OutO3 }}"
