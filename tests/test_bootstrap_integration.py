"""
Integration tests for the `samstacks bootstrap` command.
"""

import pytest
import yaml
from pathlib import Path
from click.testing import CliRunner

from samstacks.cli import cli  # Main CLI entry point

# Define the path to the test project relative to the tests directory
TEST_PROJECT_ROOT = Path(__file__).parent.parent  # Gets /Users/alessandro/git/samstacks
TESTS_DIR = Path(__file__).parent  # Gets the tests directory
BOOTSTRAP_TEST_PROJECT_DIR = TESTS_DIR / "fixtures" / "bootstrap_test_project"
EXPECTED_PIPELINE_FILE = BOOTSTRAP_TEST_PROJECT_DIR / "expected_pipeline.yml"
GENERATED_PIPELINE_FILE_NAME = (
    "generated_test_pipeline.yml"  # Use a different name to avoid git issues
)


class TestBootstrapIntegration:
    @pytest.fixture(
        scope="class"
    )  # Use class scope if resources are shared by all tests in class
    def setup_test_environment(self, tmp_path_factory):
        """Prepares a clean copy of the bootstrap_test_project for each test run."""
        # It's safer to copy the test project to a temporary location
        # to avoid modifications to the committed version, especially if tests write files.
        # However, for a read-only bootstrap test that generates output elsewhere,
        # using the committed path directly might be okay if we clean up the output file.

        # For this test, we'll generate the output in a temp directory.
        output_dir = tmp_path_factory.mktemp("bootstrap_output")
        generated_pipeline_path = output_dir / GENERATED_PIPELINE_FILE_NAME

        # Ensure the source project exists
        if not BOOTSTRAP_TEST_PROJECT_DIR.is_dir():
            pytest.fail(
                f"Bootstrap test project not found at: {BOOTSTRAP_TEST_PROJECT_DIR}"
            )
        if not EXPECTED_PIPELINE_FILE.is_file():
            pytest.fail(
                f"Expected pipeline file not found at: {EXPECTED_PIPELINE_FILE}"
            )

        yield BOOTSTRAP_TEST_PROJECT_DIR, generated_pipeline_path

        # Cleanup: generated_pipeline_path is in tmp_path, auto-cleaned by pytest

    def test_bootstrap_generates_expected_pipeline(self, setup_test_environment):
        source_project_path, generated_pipeline_path = setup_test_environment

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "bootstrap",
                str(source_project_path),
                "--output-file",
                str(generated_pipeline_path),
                "--overwrite",  # Ensure it overwrites if run multiple times locally
            ],
        )

        assert result.exit_code == 0, (
            f"CLI command failed: {result.output}\nException: {result.exception}"
        )
        assert generated_pipeline_path.is_file(), (
            f"Generated pipeline file not found at {generated_pipeline_path}"
        )

        with open(generated_pipeline_path, "r") as f_generated:
            generated_content = yaml.safe_load(f_generated)
        with open(EXPECTED_PIPELINE_FILE, "r") as f_expected:
            expected_content = yaml.safe_load(f_expected)

        # Basic check: ensure top-level keys are somewhat similar before deep diff
        assert generated_content.get("pipeline_name") == expected_content.get(
            "pipeline_name"
        ), "Pipeline names do not match"
        assert "pipeline_settings" in generated_content
        assert "stacks" in generated_content

        # The order of stacks is critical and should be preserved by topological sort
        # The order of keys within dicts might not be, but yaml.dump(sort_keys=False) helps.
        # For a robust comparison, especially if there are minor formatting differences
        # or dict key order issues not controlled by sort_keys=False at all levels,
        # comparing the loaded Python objects is best.

        # Compare pipeline_settings.default_sam_config
        gen_default_sam_config = generated_content.get("pipeline_settings", {}).get(
            "default_sam_config"
        )
        exp_default_sam_config = expected_content.get("pipeline_settings", {}).get(
            "default_sam_config"
        )
        dump_gen_default = yaml.dump(
            gen_default_sam_config, indent=2, sort_keys=False, default_flow_style=False
        )
        dump_exp_default = yaml.dump(
            exp_default_sam_config, indent=2, sort_keys=False, default_flow_style=False
        )
        error_msg_default_sam_config = (
            f"Default SAM Config differs.\n"
            f"Generated:\n{dump_gen_default}"
            f"Expected:\n{dump_exp_default}"
        )
        assert gen_default_sam_config == exp_default_sam_config, (
            error_msg_default_sam_config
        )

        # Compare stacks list (order and content)
        gen_stacks = generated_content.get("stacks", [])
        exp_stacks = expected_content.get("stacks", [])
        assert len(gen_stacks) == len(exp_stacks), "Number of stacks differs"

        for i, gen_stack in enumerate(gen_stacks):
            exp_stack = exp_stacks[i]
            assert gen_stack.get("id") == exp_stack.get("id"), (
                f"Stack ID at index {i} differs"
            )
            assert gen_stack.get("dir") == exp_stack.get("dir"), (
                f"Stack dir for {gen_stack.get('id')} differs"
            )

            # Compare params (important for dependency inference)
            gen_params = gen_stack.get("params")
            exp_params = exp_stack.get("params")
            params_error_msg = (
                f"Params for stack {gen_stack.get('id')} differ.\n"
                f"Generated: {gen_params}\n"
                f"Expected: {exp_params}"
            )
            assert gen_params == exp_params, params_error_msg

            # Compare sam_config_overrides
            gen_overrides = gen_stack.get("sam_config_overrides")
            exp_overrides = exp_stack.get("sam_config_overrides")
            overrides_error_msg = (
                f"SAM Config Overrides for stack {gen_stack.get('id')} differ.\n"
                f"Generated: {yaml.dump(gen_overrides, indent=2)}\n"
                f"Expected: {yaml.dump(exp_overrides, indent=2)}"
            )
            assert gen_overrides == exp_overrides, overrides_error_msg

        # If all stack-wise comparisons pass, consider the full structure matched for this test's purpose.
        # For a stricter full-object comparison, you can just do:
        # assert generated_content == expected_content, "Generated pipeline content does not match expected content"
        # However, the granular checks above give better failure messages.
