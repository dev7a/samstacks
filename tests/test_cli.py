# tests/test_cli.py
import pytest
from click.testing import CliRunner
from pathlib import Path
import yaml
from unittest import mock  # Import mock for patching BootstrapManager

from samstacks.cli import cli  # Changed from 'main' to 'cli'
from samstacks.bootstrap import BootstrapManager  # We need to mock this


# Helper to create a minimal valid stack directory
def create_stack_dir_with_template(base_path: Path, stack_dir_name: str) -> Path:
    stack_dir = base_path / stack_dir_name
    stack_dir.mkdir(parents=True, exist_ok=True)
    # A minimal valid SAM template
    (stack_dir / "template.yaml").write_text(
        "AWSTemplateFormatVersion: '2010-09-09'\n"
        "Description: Minimal stack for CLI test\n"
        "Resources:\n"
        "  MyBucket: \n"
        "    Type: AWS::S3::Bucket\n"
    )
    return stack_dir


class TestCliDeployCommand:
    @pytest.fixture(autouse=True)
    def ensure_no_global_path_mocks(self, mocker):
        mocker.stopall()

    @pytest.fixture
    def mock_aws_utilities(self, mocker):
        """Shared fixture for mocking AWS utilities used in deploy tests."""
        mocker.patch("samstacks.aws_utils.get_stack_outputs", return_value={})
        mocker.patch(
            "samstacks.aws_utils.get_stack_status", return_value="CREATE_COMPLETE"
        )
        mocker.patch(
            "samstacks.aws_utils.list_failed_no_update_changesets", return_value=[]
        )
        mocker.patch("samstacks.aws_utils.delete_changeset")
        mocker.patch("samstacks.aws_utils.delete_cloudformation_stack")
        mocker.patch("samstacks.aws_utils.wait_for_stack_delete_complete")

    def test_deploy_success_generates_samconfig_and_calls_sam_correctly(
        self, tmp_path: Path, mocker, mock_aws_utilities
    ):
        # 1. Setup:
        pipeline_data = {
            "pipeline_name": "CliTestPipe",
            "pipeline_settings": {
                "stack_name_prefix": "CliTestPipe-",
                "default_sam_config": {
                    "version": 0.1,
                    "default": {
                        "deploy": {
                            "parameters": {
                                "GlobalTag": "TestValue",
                                "capabilities": ["CAPABILITY_IAM"],
                            }
                        }
                    },
                },
            },
            "stacks": [
                {
                    "id": "s1",
                    "dir": "./stack1/",
                    "params": {"BucketName": "cli-test-bucket"},
                    "sam_config_overrides": {
                        "default": {"deploy": {"parameters": {"region": "us-west-2"}}}
                    },
                }
            ],
        }
        pipeline_file = tmp_path / "pipeline.yml"
        with open(pipeline_file, "w") as f:
            yaml.dump(pipeline_data, f)
        stack1_dir = create_stack_dir_with_template(tmp_path, "stack1")

        sam_build_called_flag_obj = {"called": False}
        sam_deploy_called_flag_obj = {"called": False}

        def stderr_capture_side_effect_fn(cmd, cwd, env_dict):
            if cmd[0:2] == ["sam", "build"]:
                sam_build_called_flag_obj["called"] = True
                return (0, "")  # Success with no stderr
            elif cmd[0:2] == ["sam", "deploy"]:
                sam_deploy_called_flag_obj["called"] = True
                return (
                    1,
                    "Error: No changes to deploy. Stack CliTestPipe-s1 is up to date",
                )  # stderr contains the message
            pytest.fail(
                f"_run_command_with_stderr_capture was called with unexpected cmd: {cmd}"
            )
            return (1, "fail")

        mock_stderr_capture_helper = mocker.patch(
            "samstacks.core._run_command_with_stderr_capture",
            side_effect=stderr_capture_side_effect_fn,
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", str(pipeline_file)])

        assert result.exit_code == 0, (
            f"CLI command failed: {result.output} {result.exception}"
        )

        expected_samconfig_path = stack1_dir / "samconfig.yaml"
        assert expected_samconfig_path.exists()
        with open(expected_samconfig_path, "r") as f:
            generated_samconfig = yaml.safe_load(f)
        assert generated_samconfig.get("version") == 0.1
        deploy_params = (
            generated_samconfig.get("default", {})
            .get("deploy", {})
            .get("parameters", {})
        )
        assert deploy_params.get("stack_name") == "CliTestPipe-s1"
        assert deploy_params.get("parameter_overrides") == [
            "BucketName=cli-test-bucket"
        ]

        assert sam_build_called_flag_obj["called"], "sam build was not called"
        assert sam_deploy_called_flag_obj["called"], "sam deploy was not called"

        assert mock_stderr_capture_helper.call_count == 2
        assert mock_stderr_capture_helper.call_args_list[0].args[0] == ["sam", "build"]
        deploy_call_args_actual = mock_stderr_capture_helper.call_args_list[1].args[0]
        assert deploy_call_args_actual == ["sam", "deploy"]
        assert "--config-file" not in deploy_call_args_actual
        assert "--stack-name" not in deploy_call_args_actual

    def test_deploy_with_existing_samconfig_toml_backup(
        self, tmp_path: Path, mocker, mock_aws_utilities
    ):
        # 1. Setup:
        pipeline_data = {
            "pipeline_name": "BackupTest",
            "stacks": [{"id": "s1", "dir": "./stack1/"}],
        }
        pipeline_file = tmp_path / "pipeline.yml"
        with open(pipeline_file, "w") as f:
            yaml.dump(pipeline_data, f)
        stack1_dir = create_stack_dir_with_template(tmp_path, "stack1")
        existing_toml_content = (
            'version = 0.1\n[default.deploy.parameters]\nstack_name = "old-name"'
        )
        (stack1_dir / "samconfig.toml").write_text(existing_toml_content)

        sam_build_called_flag_obj = {"called": False}
        sam_deploy_called_flag_obj = {"called": False}

        def stderr_capture_side_effect_fn_backup(cmd, cwd, env_dict):
            if cmd[0:2] == ["sam", "build"]:
                sam_build_called_flag_obj["called"] = True
                return (0, "")  # Success with no stderr
            elif cmd[0:2] == ["sam", "deploy"]:
                sam_deploy_called_flag_obj["called"] = True
                return (
                    1,
                    "Error: No changes to deploy. Stack s1 is up to date",
                )  # stderr contains the message
            pytest.fail(
                f"_run_command_with_stderr_capture was called with unexpected cmd in backup test: {cmd}"
            )
            return (1, "fail")

        # ONLY mock _run_command_with_stderr_capture
        mock_stderr_capture_helper = mocker.patch(
            "samstacks.core._run_command_with_stderr_capture",
            side_effect=stderr_capture_side_effect_fn_backup,
        )

        # 2. Run
        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", str(pipeline_file)])
        assert result.exit_code == 0, f"CLI Error: {result.output} {result.exception}"

        # 3. Assertions for file backup
        assert not (stack1_dir / "samconfig.toml").exists()
        assert (stack1_dir / "samconfig.toml.bak").exists()
        assert (stack1_dir / "samconfig.yaml").exists()
        with open(stack1_dir / "samconfig.toml.bak", "r") as f:
            backed_up_content = f.read()
            assert backed_up_content == existing_toml_content

        assert sam_build_called_flag_obj["called"], (
            "sam build was not called in backup test"
        )
        assert sam_deploy_called_flag_obj["called"], (
            "sam deploy was not called in backup test"
        )
        assert mock_stderr_capture_helper.call_count == 2


class TestCliBootstrapCommand:
    @pytest.fixture(autouse=True)
    def ensure_no_global_path_mocks(self, mocker):
        mocker.stopall()

    @pytest.fixture
    def mock_bootstrap_manager(self, mocker) -> mock.MagicMock:
        """Mocks the BootstrapManager class and its bootstrap_pipeline method."""
        mock_instance = mocker.MagicMock(spec=BootstrapManager)
        mock_instance.bootstrap_pipeline.return_value = None

        # Set up attributes that the CLI command will try to access on the bootstrapper instance
        # The actual value of output_file_path for the mock doesn't strictly matter for these CLI tests,
        # as long as it exists. We can give it a dummy Path object.
        mock_instance.output_file_path = Path("mocked/output/pipeline.yml")
        # Also ensure discovered_stacks is an attribute, as cli.py checks its length
        mock_instance.discovered_stacks = [
            mocker.MagicMock()
        ]  # Simulate at least one stack found
        mock_instance.pipeline_name = "MockedPipelineName"  # For ui.info call
        mock_instance.stack_name_prefix = None  # Default for one test path

        mock_constructor = mocker.patch(
            "samstacks.cli.BootstrapManager", return_value=mock_instance
        )
        return mock_constructor, mock_instance

    def test_bootstrap_default_options(self, tmp_path: Path, mock_bootstrap_manager):
        mock_constructor, mock_instance = mock_bootstrap_manager
        runner = CliRunner()

        # Create a dummy directory for scan_path to exist
        scan_dir = tmp_path / "my_project"
        scan_dir.mkdir()

        result = runner.invoke(cli, ["bootstrap", str(scan_dir)])

        assert result.exit_code == 0, f"CLI Error: {result.output} {result.exception}"
        mock_constructor.assert_called_once_with(
            scan_path=str(scan_dir.resolve()),
            output_file="pipeline.yml",  # Default
            default_stack_id_source="dir",  # Default
            pipeline_name=None,  # Default
            stack_name_prefix=None,  # Default
            overwrite=False,  # Default
        )
        mock_instance.bootstrap_pipeline.assert_called_once()

    def test_bootstrap_all_options_provided(
        self, tmp_path: Path, mock_bootstrap_manager
    ):
        mock_constructor, mock_instance = mock_bootstrap_manager
        runner = CliRunner()
        scan_dir = tmp_path / "another_project"
        scan_dir.mkdir()

        result = runner.invoke(
            cli,
            [
                "bootstrap",
                str(scan_dir),
                "--output-file",
                "custom_pipeline.yaml",
                "--default-stack-id-source",
                "samconfig_stack_name",
                "--pipeline-name",
                "MyCustomPipeline",
                "--stack-name-prefix",
                "test-",
                "--overwrite",
            ],
        )

        assert result.exit_code == 0, f"CLI Error: {result.output} {result.exception}"
        mock_constructor.assert_called_once_with(
            scan_path=str(scan_dir.resolve()),
            output_file="custom_pipeline.yaml",
            default_stack_id_source="samconfig_stack_name",
            pipeline_name="MyCustomPipeline",
            stack_name_prefix="test-",
            overwrite=True,
        )
        mock_instance.bootstrap_pipeline.assert_called_once()

    def test_bootstrap_scan_path_defaults_to_current_dir(
        self, tmp_path: Path, mock_bootstrap_manager, mocker
    ):
        mock_constructor, mock_instance = mock_bootstrap_manager
        runner = CliRunner()

        # Use isolated_filesystem to change CWD for the invoke call
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            # td is now a Path object to the temporary current working directory
            # Ensure this directory exists for Click's Path(exists=True) type check
            # (it's created by isolated_filesystem)

            result = runner.invoke(cli, ["bootstrap"])  # No scan_path provided

        assert result.exit_code == 0, f"CLI Error: {result.output} {result.exception}"
        mock_constructor.assert_called_once_with(
            scan_path=str(Path(td).resolve()),  # Should default to the isolated CWD
            output_file="pipeline.yml",
            default_stack_id_source="dir",
            pipeline_name=None,
            stack_name_prefix=None,
            overwrite=False,
        )
        mock_instance.bootstrap_pipeline.assert_called_once()

    def test_bootstrap_invalid_stack_id_source(
        self, tmp_path: Path, mock_bootstrap_manager
    ):
        _, _ = mock_bootstrap_manager  # We don't need to assert calls here
        runner = CliRunner()
        scan_dir = tmp_path / "project_invalid_id_source"
        scan_dir.mkdir()

        result = runner.invoke(
            cli,
            ["bootstrap", str(scan_dir), "--default-stack-id-source", "invalid_choice"],
        )

        assert result.exit_code != 0
        assert "Invalid value for '--default-stack-id-source'" in result.output

    def test_bootstrap_scan_path_not_a_directory(
        self, tmp_path: Path, mock_bootstrap_manager
    ):
        _, _ = mock_bootstrap_manager
        runner = CliRunner()
        file_path = tmp_path / "not_a_dir.txt"
        file_path.touch()

        result = runner.invoke(cli, ["bootstrap", str(file_path)])
        assert result.exit_code != 0
        assert (
            f"Invalid value for '[SCAN_PATH]': Directory '{str(file_path.resolve())}' is a file."
            in result.output
        )

    def test_bootstrap_scan_path_does_not_exist(
        self, tmp_path: Path, mock_bootstrap_manager
    ):
        _, _ = mock_bootstrap_manager
        runner = CliRunner()
        non_existent_path = tmp_path / "i_do_not_exist"

        result = runner.invoke(cli, ["bootstrap", str(non_existent_path)])
        assert result.exit_code != 0
        assert (
            f"Invalid value for '[SCAN_PATH]': Directory '{str(non_existent_path.resolve())}' does not exist."
            in result.output
        )
