# tests/test_cli.py
import pytest
from click.testing import CliRunner
from pathlib import Path
import yaml

from samstacks.cli import cli  # Changed from 'main' to 'cli'


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
        """Stop any autouse Path mocks from other test files if they interfere."""
        # If Path was globally mocked by an autouse fixture in another test file,
        # this attempts to restore it for CLI tests which need real Path behavior (for tmp_path)
        # or more controlled local mocks.
        mocker.stopall()  # Stops all active mocks started by pytest-mock for this test function
        # This is broad; more targeted unpatching might be needed if it causes issues.

    def test_deploy_success_generates_samconfig_and_calls_sam_correctly(
        self, tmp_path: Path, mocker
    ):
        # 1. Setup: Create a pipeline.yml and stack directories
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
                    "dir": "./stack1/",  # Relative to pipeline.yml location (tmp_path)
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

        # 2. Mock subprocess.run for `sam build` and `sam deploy`
        def mock_subprocess_run(*args, **kwargs):
            # Mock successful sam build and sam deploy
            cmd = args[0]
            if cmd[0:2] == ["sam", "build"]:
                return mocker.Mock(returncode=0, stdout="Build succeeded", stderr="")
            elif cmd[0:2] == ["sam", "deploy"]:
                return mocker.Mock(returncode=0, stdout="Deploy succeeded", stderr="")
            else:
                return mocker.Mock(returncode=0, stdout="", stderr="")

        mock_subprocess_run_obj = mocker.patch(
            "subprocess.run", side_effect=mock_subprocess_run
        )
        # Mock AWS utilities at the core.py level since they're imported directly there
        mocker.patch("samstacks.core.get_stack_outputs", return_value={})
        mocker.patch(
            "samstacks.core.get_stack_status", return_value="CREATE_COMPLETE"
        )  # Mock stack exists
        mocker.patch("samstacks.core.list_failed_no_update_changesets", return_value=[])
        mocker.patch("samstacks.core.delete_changeset")
        mocker.patch("samstacks.core.delete_cloudformation_stack")
        mocker.patch("samstacks.core.wait_for_stack_delete_complete")

        # 3. Run the CLI command
        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", str(pipeline_file)])

        if result.exit_code != 0:
            print(f"CLI Output on Error: {result.output}")
            print(f"Exception: {result.exception}")
        assert result.exit_code == 0, f"CLI command failed: {result.output}"

        # 4. Assert samconfig.yaml generation
        expected_samconfig_path = stack1_dir / "samconfig.yaml"
        assert expected_samconfig_path.exists(), (
            f"samconfig.yaml not found at {expected_samconfig_path}"
        )

        with open(expected_samconfig_path, "r") as f:
            generated_samconfig = yaml.safe_load(f)

        assert generated_samconfig.get("version") == 0.1
        deploy_params = (
            generated_samconfig.get("default", {})
            .get("deploy", {})
            .get("parameters", {})
        )

        assert deploy_params.get("stack_name") == "CliTestPipe-s1"
        assert deploy_params.get("s3_prefix") == "CliTestPipe-s1"
        assert deploy_params.get("GlobalTag") == "TestValue"
        assert deploy_params.get("capabilities") == ["CAPABILITY_IAM"]
        assert deploy_params.get("region") == "us-west-2"
        assert deploy_params.get("parameter_overrides") == "BucketName=cli-test-bucket"

        # 5. Assert correct `sam build` and `sam deploy` calls
        sam_build_called = False
        sam_deploy_called = False
        for call_obj in mock_subprocess_run_obj.call_args_list:
            cmd_list = call_obj.args[0]

            if cmd_list[0:2] == ["sam", "build"]:
                sam_build_called = True
                assert "--config-file" not in cmd_list

            if cmd_list[0:2] == ["sam", "deploy"]:
                sam_deploy_called = True
                assert "--config-file" not in cmd_list
                assert "--stack-name" not in cmd_list
                assert "--s3-prefix" not in cmd_list
                assert "--region" not in cmd_list
                assert "--capabilities" not in cmd_list
                assert "--parameter-overrides" not in cmd_list

        assert sam_build_called, "sam build was not called"
        assert sam_deploy_called, "sam deploy was not called"

    def test_deploy_with_existing_samconfig_toml_backup(self, tmp_path: Path, mocker):
        # 1. Setup
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

        # Mocks
        def mock_subprocess_run(*args, **kwargs):
            # Mock successful sam build and sam deploy
            cmd = args[0]
            if cmd[0:2] == ["sam", "build"]:
                return mocker.Mock(returncode=0, stdout="Build succeeded", stderr="")
            elif cmd[0:2] == ["sam", "deploy"]:
                return mocker.Mock(returncode=0, stdout="Deploy succeeded", stderr="")
            else:
                return mocker.Mock(returncode=0, stdout="", stderr="")

        mock_subprocess_run_obj = mocker.patch(
            "subprocess.run", side_effect=mock_subprocess_run
        )
        # Mock AWS utilities at the core.py level since they're imported directly there
        mocker.patch("samstacks.core.get_stack_outputs", return_value={})
        mocker.patch(
            "samstacks.core.get_stack_status", return_value="CREATE_COMPLETE"
        )  # Mock stack exists
        mocker.patch("samstacks.core.list_failed_no_update_changesets", return_value=[])
        mocker.patch("samstacks.core.delete_changeset")
        mocker.patch("samstacks.core.delete_cloudformation_stack")
        mocker.patch("samstacks.core.wait_for_stack_delete_complete")

        # 2. Run
        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", str(pipeline_file)])
        if result.exit_code != 0:
            print(f"CLI Output on Error: {result.output}")
            print(f"Exception: {result.exception}")
        assert result.exit_code == 0

        # 3. Assertions
        assert not (stack1_dir / "samconfig.toml").exists(), (
            ".toml should have been moved"
        )
        assert (stack1_dir / "samconfig.toml.bak").exists(), ".toml.bak should exist"
        assert (stack1_dir / "samconfig.yaml").exists(), (
            "new samconfig.yaml should be generated"
        )

        with open(stack1_dir / "samconfig.toml.bak", "r") as f:
            backed_up_content = f.read()
            assert backed_up_content == existing_toml_content
