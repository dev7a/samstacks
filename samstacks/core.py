"""
Core classes for samstacks pipeline and stack management.
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import shlex


# Import the global console from presentation.py
# This creates a slight coupling but is pragmatic for a CLI tool.
# Ensure presentation.py defines 'console = Console()' globally.

# Import ui module
from . import ui

from .exceptions import (
    ConditionalEvaluationError,
    ManifestError,
    OutputRetrievalError,
    PostDeploymentScriptError,
    StackDeploymentError,
    TemplateError,
)
from .templating import TemplateProcessor
from .validation import ManifestValidator
from .aws_utils import (
    get_stack_outputs,
    get_stack_status,
    delete_cloudformation_stack,
    wait_for_stack_delete_complete,
    list_failed_no_update_changesets,
    delete_changeset,
)
from .presentation import console  # Ensure this is the rich Console

logger = logging.getLogger(__name__)


class Stack:
    """Represents a single SAM stack in the pipeline."""

    def __init__(
        self,
        id: str,
        name: str,
        dir: Union[str, Path],
        params: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
        region: Optional[str] = None,
        profile: Optional[str] = None,
        stack_name_suffix: Optional[str] = None,
        if_condition: Optional[str] = None,
        run_script: Optional[str] = None,
    ):
        """Initialize a Stack instance."""
        self.id = id
        self.name = name
        self.dir = Path(dir)
        self.params = params or {}
        self.description = description
        self.region = region
        self.profile = profile
        self.stack_name_suffix = stack_name_suffix
        self.if_condition = if_condition
        self.run_script = run_script

        # Runtime state
        self.deployed_stack_name: Optional[str] = None
        self.outputs: Dict[str, str] = {}
        self.skipped = False

    def should_deploy(self, template_processor: "TemplateProcessor") -> bool:
        """Evaluate if this stack should be deployed based on its 'if' condition."""
        if not self.if_condition:
            return True

        try:
            # Process the condition string with template substitution
            processed_condition = template_processor.process_string(self.if_condition)

            # Evaluate truthiness
            return self._evaluate_condition(processed_condition)

        except Exception as e:
            raise ConditionalEvaluationError(
                f"Failed to evaluate 'if' condition for stack '{self.id}': {e}"
            )

    def _evaluate_condition(self, condition_str: str) -> bool:
        """Evaluate a condition string for truthiness."""
        condition_lower = condition_str.lower().strip()
        return condition_lower in ("true", "1", "yes", "on")

    def get_stack_name(self, global_prefix: str = "", global_suffix: str = "") -> str:
        """Generate the CloudFormation stack name for this stack."""
        name_parts = []

        if global_prefix:
            name_parts.append(global_prefix.rstrip("-"))

        name_parts.append(self.id)

        if self.stack_name_suffix:
            name_parts.append(self.stack_name_suffix.strip("-"))

        if global_suffix:
            name_parts.append(global_suffix.strip("-"))

        return "-".join(part for part in name_parts if part)


class Pipeline:
    """Represents a complete SAM stacks pipeline."""

    def __init__(
        self,
        name: str,
        description: str = "",
        stacks: Optional[List[Stack]] = None,
        pipeline_settings: Optional[Dict[str, Any]] = None,
    ):
        """Initialize a Pipeline instance."""
        self.name = name
        self.description = description
        self.stacks = stacks or []
        self.pipeline_settings = pipeline_settings or {}

        # Template processor for handling substitutions
        self.template_processor = TemplateProcessor()

    @classmethod
    def from_file(cls, manifest_path: Union[str, Path]) -> "Pipeline":
        """Create a Pipeline instance from a manifest file."""
        manifest_path = Path(manifest_path).resolve()
        manifest_base_dir = manifest_path.parent

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                yaml_content = f.read()
        except Exception as e:
            raise ManifestError(f"Failed to load manifest file '{manifest_path}': {e}")

        # Use the new validator with line number tracking
        validator = ManifestValidator.from_yaml_content(yaml_content, manifest_path)
        validator.validate_and_raise_if_errors()

        return cls.from_dict(
            validator.manifest_data,
            manifest_base_dir=manifest_base_dir,
            skip_validation=True,
        )

    @classmethod
    def from_dict(
        cls,
        manifest_data: Dict[str, Any],
        manifest_base_dir: Optional[Path] = None,
        skip_validation: bool = False,
    ) -> "Pipeline":
        """Create a Pipeline instance from a manifest dictionary."""
        try:
            # Validate manifest schema and template expressions first (unless skipped)
            if not skip_validation:
                validator = ManifestValidator(manifest_data)
                validator.validate_and_raise_if_errors()

            pipeline_name = manifest_data.get("pipeline_name", "")
            pipeline_description = manifest_data.get("pipeline_description", "")
            pipeline_settings = manifest_data.get("pipeline_settings", {})

            stacks = []
            for stack_data in manifest_data.get("stacks", []):
                stack_dir_relative = Path(stack_data["dir"])

                if manifest_base_dir:
                    resolved_stack_dir = (
                        manifest_base_dir / stack_dir_relative
                    ).resolve()
                else:
                    resolved_stack_dir = stack_dir_relative.resolve()

                stack = Stack(
                    id=stack_data["id"],
                    name=stack_data.get("name", stack_data["id"]),
                    dir=resolved_stack_dir,
                    params=stack_data.get("params", {}),
                    description=stack_data.get("description"),
                    region=stack_data.get("region"),
                    profile=stack_data.get("profile"),
                    stack_name_suffix=stack_data.get("stack_name_suffix"),
                    if_condition=stack_data.get("if"),
                    run_script=stack_data.get("run"),
                )
                stacks.append(stack)

            return cls(
                name=pipeline_name,
                description=pipeline_description,
                stacks=stacks,
                pipeline_settings=pipeline_settings,
            )

        except KeyError as e:
            raise ManifestError(f"Missing required field in manifest: {e}")
        except Exception as e:
            raise ManifestError(f"Failed to parse manifest: {e}")

    def validate(self) -> None:
        """Validate the pipeline configuration."""
        if not self.stacks:
            raise ManifestError("Pipeline must contain at least one stack")

        # Check for duplicate stack IDs
        stack_ids = [stack.id for stack in self.stacks]
        if len(stack_ids) != len(set(stack_ids)):
            raise ManifestError("Duplicate stack IDs found in pipeline")

        # Validate each stack's directory exists
        for stack in self.stacks:
            if not stack.dir.exists():
                raise ManifestError(f"Stack directory does not exist: {stack.dir}")

            template_file = stack.dir / "template.yaml"
            if not template_file.exists():
                template_file = stack.dir / "template.yml"
                if not template_file.exists():
                    raise ManifestError(
                        f"No template.yaml or template.yml found in {stack.dir}"
                    )

    def set_global_region(self, region: str) -> None:
        """Set the global AWS region, overriding manifest settings."""
        self.pipeline_settings["default_region"] = region

    def set_global_profile(self, profile: str) -> None:
        """Set the global AWS profile, overriding manifest settings."""
        self.pipeline_settings["default_profile"] = profile

    def deploy(self, auto_delete_failed: bool = False) -> None:
        """Deploy all stacks in the pipeline."""
        ui.header(f"Starting deployment of pipeline: {self.name}")

        # Validate before deployment
        self.validate()

        for stack in self.stacks:
            self._deploy_stack(stack, auto_delete_failed)

        # The final success message is printed by cli.py using ui.success()
        # ui.header("Pipeline deployment completed successfully") # This might be too much if cli.py also prints
        # logger.info("Pipeline deployment completed successfully") # Log is fine

    def _handle_auto_delete(self, stack: Stack) -> None:
        """Check stack status and delete if in ROLLBACK_COMPLETE.
        Also cleans up FAILED changesets with 'No updates are to be performed.' reason.
        """
        stack_name = stack.deployed_stack_name
        if not stack_name:
            logger.warning(
                f"Stack name not determined for stack '{stack.id}', cannot perform auto-delete operations."
            )
            return

        region = stack.region or self.pipeline_settings.get("default_region")
        profile = stack.profile or self.pipeline_settings.get("default_profile")

        current_status = None  # Initialize current_status
        try:
            current_status = get_stack_status(stack_name, region, profile)
            if current_status == "ROLLBACK_COMPLETE":
                # Use ui.info or ui.warning for these operational messages
                ui.info(
                    "Stack status",
                    f"'{stack_name}' is in ROLLBACK_COMPLETE. Deleting (due to --auto-delete-failed).",
                )
                delete_cloudformation_stack(stack_name, region, profile)
                wait_for_stack_delete_complete(stack_name, region, profile)
                ui.info("Stack deletion", f"Successfully deleted stack '{stack_name}'.")
                current_status = None
            elif current_status:
                # This is more of a debug level, or not needed if ui.log handles it
                ui.debug(
                    f"Stack '{stack_name}' current status: {current_status}. No auto-deletion of stack needed."
                )
            else:
                ui.debug(
                    f"Stack '{stack_name}' does not exist. No auto-deletion of stack needed."
                )
        except Exception as e:
            ui.warning(
                "Auto-delete operation failed",
                details=f"During ROLLBACK_COMPLETE check for '{stack_name}': {e}. Proceeding.",
            )
            if current_status is None and "does not exist" not in str(e).lower():
                try:
                    current_status = get_stack_status(stack_name, region, profile)
                except Exception:
                    ui.warning(
                        "Status re-check failed",
                        details=f"Could not confirm status of stack '{stack_name}' for changeset cleanup.",
                    )
                    current_status = "UNKNOWN_ERROR_STATE"

        # Clean up "No updates are to be performed." FAILED changesets
        # Only if stack was not just deleted or confirmed non-existent from the ROLLBACK_COMPLETE check
        if current_status is not None and current_status != "UNKNOWN_ERROR_STATE":
            try:
                changeset_ids_to_delete = list_failed_no_update_changesets(
                    stack_name, region, profile
                )
                if changeset_ids_to_delete:
                    ui.info(
                        f"Changeset cleanup for '{stack_name}'",
                        value=f"Found {len(changeset_ids_to_delete)} 'FAILED - No updates' changesets. Deleting...",
                    )
                    deleted_cs_count = 0
                    for cs_id in changeset_ids_to_delete:
                        try:
                            delete_changeset(cs_id, stack_name, region, profile)
                            deleted_cs_count += 1
                        except Exception as cs_del_e:
                            ui.warning(
                                f"Changeset deletion failed for '{cs_id}'",
                                details=f"Stack '{stack_name}': {cs_del_e}. Continuing...",
                            )
                    if deleted_cs_count > 0:
                        ui.info(
                            f"Changeset cleanup for '{stack_name}'",
                            value=f"Successfully deleted {deleted_cs_count} changesets.",
                        )
                else:
                    ui.debug(
                        f"No 'FAILED - No updates' changesets found for stack '{stack_name}'."
                    )
            except Exception as e:
                ui.warning(
                    f"Changeset cleanup failed for '{stack_name}'",
                    details=f"Error listing/deleting 'FAILED - No updates' changesets: {e}. Proceeding.",
                )

    def _deploy_stack(self, stack: Stack, auto_delete_failed: bool) -> None:
        """Deploy a single stack."""
        ui.subheader(f"Processing stack: {stack.id} ({stack.name})")

        # Check if stack should be deployed
        if not stack.should_deploy(self.template_processor):
            ui.info(f"Skipping stack '{stack.id}'", "Due to 'if' condition.")
            stack.skipped = True
            return

        # Generate stack name
        global_prefix = self.pipeline_settings.get("stack_name_prefix", "")
        global_suffix = self.pipeline_settings.get("stack_name_suffix", "")

        # Process prefix/suffix for template substitution
        if global_prefix:
            global_prefix = self.template_processor.process_string(global_prefix)
        if global_suffix:
            global_suffix = self.template_processor.process_string(global_suffix)

        stack.deployed_stack_name = stack.get_stack_name(global_prefix, global_suffix)

        # Handle auto-deletion of ROLLBACK_COMPLETE stacks if flag is set
        if auto_delete_failed:
            self._handle_auto_delete(stack)

        if stack.deployed_stack_name is None:  # Guard added in previous steps
            # This should ideally not happen if get_stack_name was called correctly
            logger.error(
                f"Critical error: deployed_stack_name is None for stack {stack.id} before deployment logic."
            )
            # Potentially raise an error to halt if this state is unexpected
            return

        # Use rich console directly for this specific styled line
        console.print(
            f"  Deploying stack [cyan]'{stack.id}'[/cyan] as [green]'{stack.deployed_stack_name}'[/green]..."
        )

        # Store absolute path before changing directories
        stack_abs_dir = stack.dir.absolute()

        # Change to stack directory
        original_cwd = os.getcwd()
        try:
            os.chdir(stack.dir)
            samconfig_path = self._process_samconfig(stack)
            self._run_sam_build(stack, samconfig_path)
            self._run_sam_deploy(stack, samconfig_path)

            # Ensure deployed_stack_name is not None before using it for output retrieval
            if stack.deployed_stack_name is None:
                raise StackDeploymentError(
                    f"Stack {stack.id} has no deployed_stack_name after deploy call, cannot retrieve outputs."
                )
            self._retrieve_stack_outputs(stack)

            if stack.outputs:
                ui.subheader(f"Outputs for Stack: {stack.deployed_stack_name}")
                output_rows = [[key, value] for key, value in stack.outputs.items()]
                if output_rows:  # Ensure there are rows to display
                    ui.format_table(headers=["Output Key", "Value"], rows=output_rows)
            else:
                ui.debug(f"No outputs found for stack '{stack.id}'.")

            # Add stack outputs to template processor
            self.template_processor.add_stack_outputs(stack.id, stack.outputs)

            if stack.run_script:
                # process_string now returns "" for None input, so processed_script is str
                processed_script: str = self.template_processor.process_string(
                    stack.run_script
                )
                if processed_script:  # Only run if script content is not empty
                    self._run_post_deployment_script(
                        stack, stack_abs_dir, processed_script
                    )

        finally:
            os.chdir(original_cwd)

    def _process_samconfig(self, stack: Stack) -> Optional[str]:
        """Process samconfig.toml with template substitution if it exists."""
        samconfig_path = stack.dir / "samconfig.toml"
        if not samconfig_path.exists():
            return None

        try:
            with open(samconfig_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Process template substitutions
            processed_content = self.template_processor.process_string(content)

            # Write to temporary file
            temp_fd, temp_path = tempfile.mkstemp(suffix=".toml", prefix="samconfig_")
            try:
                with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                    f.write(processed_content)
                return temp_path
            except:
                os.unlink(temp_path)
                raise

        except Exception as e:
            raise TemplateError(
                f"Failed to process samconfig.toml for stack '{stack.id}': {e}"
            )

    def _run_sam_build(self, stack: Stack, samconfig_path: Optional[str]) -> None:
        """Run sam build for the stack."""
        cmd = ["sam", "build"]

        if samconfig_path:
            cmd.extend(["--config-file", samconfig_path])

        logger.debug(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            logger.debug(f"sam build output: {result.stdout}")

        except subprocess.CalledProcessError as e:
            raise StackDeploymentError(
                f"sam build failed for stack '{stack.id}': {e.stderr}"
            )
        except FileNotFoundError:
            raise StackDeploymentError(
                "sam command not found. Please ensure AWS SAM CLI is installed."
            )

    def _run_sam_deploy(self, stack: Stack, samconfig_path: str | None) -> None:
        """Run sam deploy for the stack."""
        if stack.deployed_stack_name is None:  # Guard
            raise StackDeploymentError(
                f"Cannot deploy stack {stack.id}, deployed_stack_name is not set."
            )

        base_cmd = [
            "sam",
            "deploy",
            "--stack-name",
            stack.deployed_stack_name,
            "--s3-prefix",
            stack.deployed_stack_name,
            "--resolve-s3",
        ]
        config_opts: List[str] = []
        if samconfig_path:
            config_opts.extend(["--config-file", samconfig_path])

        region_val = stack.region or self.pipeline_settings.get("default_region")
        region_opts: List[str] = ["--region", region_val] if region_val else []

        profile_val = stack.profile or self.pipeline_settings.get("default_profile")
        profile_opts: List[str] = ["--profile", profile_val] if profile_val else []

        param_override_str: str | None = None
        if stack.params:
            processed_params: Dict[str, str] = {}
            for key, value in stack.params.items():
                if isinstance(value, str):
                    # process_string ensures str output
                    processed_params[key] = self.template_processor.process_string(
                        value
                    )
                else:
                    processed_params[key] = str(value)
            param_override_str = " ".join(
                f'{key}="{processed_params[key]}"'
                for key, value in processed_params.items()
            )  # Ensure values with spaces are quoted for CLI

        param_opts: List[str] = (
            ["--parameter-overrides", param_override_str] if param_override_str else []
        )

        # Construct the command list, filtering out any None parts implicitly by not adding them
        cmd: List[str] = (
            base_cmd + config_opts + region_opts + profile_opts + param_opts
        )

        # For logging, join only string parts (though all should be strings now)
        logger.debug(f"Running: {' '.join(shlex.quote(str(s)) for s in cmd)}")

        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            if e.returncode != 0:
                try:
                    # Re-run with capture to get stderr for specific error messages
                    error_result = subprocess.run(
                        cmd, capture_output=True, text=True, check=False
                    )
                    if "No changes to deploy" in error_result.stderr:
                        ui.info(
                            f"Stack '{stack.id}' is already up to date",
                            "No changes deployed.",
                        )
                        self._cleanup_just_created_no_update_changeset(stack)
                        return
                    raise StackDeploymentError(
                        f"sam deploy failed for stack '{stack.id}': {error_result.stderr}"
                    )
                except Exception as inner_e:
                    logger.debug(
                        f"Inner exception during error handling for sam deploy: {inner_e}"
                    )
                    raise StackDeploymentError(
                        f"sam deploy failed for stack '{stack.id}' with exit code {e.returncode}. Further error details unavailable."
                    )

    def _retrieve_stack_outputs(self, stack: Stack) -> None:
        """Retrieve outputs from the deployed CloudFormation stack."""
        if stack.deployed_stack_name is None:  # Guard
            logger.warning(
                f"Cannot retrieve outputs for stack {stack.id}, deployed_stack_name is not set."
            )
            stack.outputs = {}
            return
        try:
            region = stack.region or self.pipeline_settings.get("default_region")
            profile = stack.profile or self.pipeline_settings.get("default_profile")

            stack.outputs = get_stack_outputs(
                stack.deployed_stack_name,
                region=region,
                profile=profile,
            )

            logger.debug(f"Retrieved outputs for stack '{stack.id}': {stack.outputs}")

        except Exception as e:
            raise OutputRetrievalError(
                f"Failed to retrieve outputs for stack '{stack.id}': {e}"
            )

    def _run_post_deployment_script(
        self, stack: Stack, stack_abs_dir: Path, processed_script: str
    ) -> None:
        """Run the post-deployment script for the stack."""
        ui.status(
            f"Running post-deployment script for stack '{stack.id}'", "Executing..."
        )
        logger.info(f"Running post-deployment script for stack '{stack.id}'")

        try:
            # Execute the script in the stack directory using absolute path
            result = subprocess.run(
                ["bash", "-c", processed_script],
                capture_output=True,
                text=True,
                cwd=str(stack_abs_dir),
            )

            # Log output
            if result.stdout:
                # logger.info(f"[{stack.id}][run] {result.stdout}")
                ui.subheader(f"Output from 'run' script for stack '{stack.id}':")
                ui.command_output_block(
                    result.stdout.strip(), prefix="  "
                )  # Use a simpler prefix
            if result.stderr:
                # logger.warning(f"[{stack.id}][run] {result.stderr}")
                ui.warning(
                    f"Errors from 'run' script for stack '{stack.id}':",
                    details=result.stderr.strip(),
                )

            # Check for failure
            if result.returncode != 0:
                raise PostDeploymentScriptError(
                    f"Post-deployment script failed for stack '{stack.id}' "
                    f"with exit code {result.returncode}"
                )

        except Exception as e:
            if isinstance(e, PostDeploymentScriptError):
                raise
            raise PostDeploymentScriptError(
                f"Failed to execute post-deployment script for stack '{stack.id}': {e}"
            )

    def _cleanup_just_created_no_update_changeset(self, stack: Stack) -> None:
        """Cleans up FAILED changesets with 'No updates are to be performed.'
        Typically called immediately after sam deploy reports no changes.
        """
        stack_name = stack.deployed_stack_name
        if not stack_name:  # Should not happen if deploy just ran
            return

        logger.info(
            f"Attempting to clean up 'No updates' FAILED changeset for stack '{stack_name}'."
        )
        region = stack.region or self.pipeline_settings.get("default_region")
        profile = stack.profile or self.pipeline_settings.get("default_profile")

        try:
            # It's possible SAM CLI might not always leave a changeset in this specific scenario,
            # or it might be cleaned up very quickly by AWS itself in some cases.
            # We list and delete any that match the specific criteria.
            changeset_ids_to_delete = list_failed_no_update_changesets(
                stack_name, region, profile
            )
            if changeset_ids_to_delete:
                # ui.debug is better here as it's verbose
                ui.debug(
                    f"Found {len(changeset_ids_to_delete)} 'FAILED - No updates' changesets for stack '{stack_name}"
                    f"immediately after 'No changes to deploy' message. Deleting them..."
                )
                deleted_cs_count = 0
                for cs_id in changeset_ids_to_delete:
                    try:
                        delete_changeset(cs_id, stack_name, region, profile)
                        deleted_cs_count += 1
                    except Exception as cs_del_e:
                        ui.warning(
                            f"Failed to delete changeset '{cs_id}' for stack '{stack_name}' during immediate cleanup",
                            details=str(cs_del_e),
                        )
                if deleted_cs_count > 0:
                    ui.info(
                        f"Changeset cleanup for '{stack_name}'",
                        value=f"Successfully cleaned up {deleted_cs_count} changeset(s).",
                    )
            else:
                ui.debug(
                    f"No 'FAILED - No updates' changesets found for stack '{stack_name}' to cleanup immediately."
                )
        except Exception as e:
            ui.warning(
                f"Error during immediate cleanup of 'FAILED - No updates' changesets for '{stack_name}'",
                details=str(e),
            )
