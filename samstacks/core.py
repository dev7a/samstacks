"""
Core classes for samstacks pipeline and stack management.
"""

import logging
import os
import subprocess
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
from .input_utils import process_cli_input_value, coerce_and_validate_value
from .templating import TemplateProcessor
from .validation import ManifestValidator, LineNumberTracker
from .aws_utils import (
    get_stack_outputs,
    get_stack_status,
    delete_cloudformation_stack,
    wait_for_stack_delete_complete,
    list_failed_no_update_changesets,
    delete_changeset,
)
from .presentation import console  # Ensure this is the rich Console
from .pipeline_models import (
    SamConfigContentType,
    PipelineManifestModel,
    StackModel as PydanticStackModel,
)  # Added Pydantic Models
from pydantic import (
    ValidationError as PydanticValidationError,
)  # For catching Pydantic errors

from .samconfig_manager import SamConfigManager  # Import SamConfigManager

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
        sam_config_overrides: Optional[SamConfigContentType] = None,  # New parameter
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
        self.sam_config_overrides = sam_config_overrides  # Store the new attribute

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
        defined_inputs: Optional[Dict[str, Any]] = None,
        cli_inputs: Optional[Dict[str, str]] = None,
        pydantic_model: Optional[
            PipelineManifestModel
        ] = None,  # New parameter to store the parsed model
    ):
        """Initialize a Pipeline instance."""
        self.name = name
        self.description = description
        self.stacks = stacks or []
        self.pipeline_settings = pipeline_settings or {}
        self.defined_inputs = defined_inputs or {}
        self.cli_inputs = cli_inputs or {}
        self.pydantic_model = pydantic_model  # Store the model

        # Resolve and validate templated default values for inputs
        if self.defined_inputs:
            default_value_processor = TemplateProcessor(
                defined_inputs={}, cli_inputs={}
            )
            for input_name, input_def in self.defined_inputs.items():
                default_value = input_def.get("default")
                if isinstance(default_value, str) and "${{" in default_value:
                    try:
                        resolved_default_str = default_value_processor.process_string(
                            default_value
                        )
                        if (
                            resolved_default_str == default_value
                            and "${{" in default_value
                        ):
                            raise TemplateError(
                                f"Malformed template expression in default: {default_value}"
                            )
                        coerced_default = coerce_and_validate_value(
                            resolved_default_str,
                            input_name,
                            input_def,
                            value_source="Default value",
                        )
                        self.defined_inputs[input_name]["default"] = coerced_default
                    except TemplateError as e:
                        raise ManifestError(
                            f"Error processing templated default for input '{input_name}': {e}"
                        ) from e

        self.template_processor = TemplateProcessor(
            defined_inputs=self.defined_inputs,
            cli_inputs=self.cli_inputs,
            pipeline_name=self.name,  # Pass pipeline context
            pipeline_description=self.description,
        )

        # Instantiate SamConfigManager
        self.sam_config_manager = SamConfigManager(
            pipeline_name=self.name,
            pipeline_description=self.description,
            default_sam_config_from_pipeline=self.pipeline_settings.get(
                "default_sam_config"
            ),
            template_processor=self.template_processor,
        )

    @classmethod
    def from_file(
        cls,
        manifest_path: Union[str, Path],
        cli_inputs: Optional[Dict[str, str]] = None,
    ) -> "Pipeline":
        """Create a Pipeline instance from a manifest file."""
        manifest_path_obj = Path(manifest_path).resolve()
        manifest_base_dir = manifest_path_obj.parent

        try:
            with open(manifest_path_obj, "r", encoding="utf-8") as f:
                yaml_content = f.read()
        except Exception as e:
            raise ManifestError(
                f"Failed to load manifest file '{manifest_path_obj}': {e}"
            )

        # 1. Parse YAML and track line numbers

        line_tracker = LineNumberTracker(manifest_path_obj)
        try:
            raw_manifest_data, _ = line_tracker.parse_yaml_with_line_numbers(
                yaml_content
            )
            if not isinstance(raw_manifest_data, dict):
                raise ManifestError(
                    "Manifest content is not a valid YAML mapping (dictionary)."
                )
        except ManifestError as e:
            raise ManifestError(f"YAML parsing error in '{manifest_path_obj}': {e}")

        # 2. Pydantic Validation and Parsing
        try:
            pipeline_pydantic_model = PipelineManifestModel.model_validate(
                raw_manifest_data
            )
        except PydanticValidationError as e:
            error_messages = []
            for error in e.errors():
                loc_str = " -> ".join(map(str, error["loc"]))
                error_messages.append(
                    f"  - At '{loc_str}': {error['msg']} (Input: {error.get('input')})"
                )
            raise ManifestError(
                "Manifest validation failed (Pydantic):\n" + "\n".join(error_messages)
            )

        # 3. Semantic Validation (using adapted ManifestValidator)
        validator = ManifestValidator(
            pipeline_pydantic_model, line_tracker, manifest_base_dir
        )
        validator.validate_semantic_rules_and_raise_if_errors()  # Expecting this new method in ManifestValidator

        # 4. Instantiate runtime Pipeline and Stack objects
        defined_inputs_for_runtime: Dict[str, Dict[str, Any]] = {}
        if pipeline_pydantic_model.pipeline_settings.inputs:
            for (
                name,
                p_input_item,
            ) in pipeline_pydantic_model.pipeline_settings.inputs.items():
                defined_inputs_for_runtime[name] = {
                    "type": p_input_item.type,
                    "description": p_input_item.description,
                    "default": p_input_item.default,
                }

        pipeline_settings_for_runtime: Dict[str, Any] = {
            "stack_name_prefix": pipeline_pydantic_model.pipeline_settings.stack_name_prefix,
            "stack_name_suffix": pipeline_pydantic_model.pipeline_settings.stack_name_suffix,
            "default_region": pipeline_pydantic_model.pipeline_settings.default_region,
            "default_profile": pipeline_pydantic_model.pipeline_settings.default_profile,
            "inputs": defined_inputs_for_runtime,
            "default_sam_config": pipeline_pydantic_model.pipeline_settings.default_sam_config,
        }

        runtime_stacks: List[Stack] = []
        for stack_model in pipeline_pydantic_model.stacks:
            resolved_stack_dir = (manifest_base_dir / stack_model.dir).resolve()

            stack_runtime = Stack(
                id=stack_model.id,
                name=stack_model.name or stack_model.id,
                dir=resolved_stack_dir,
                params=stack_model.params,
                description=stack_model.description,
                region=stack_model.region,
                profile=stack_model.profile,
                stack_name_suffix=stack_model.stack_name_suffix,
                if_condition=stack_model.if_condition,
                run_script=stack_model.run_script,
                sam_config_overrides=stack_model.sam_config_overrides,
            )
            runtime_stacks.append(stack_runtime)

        return cls(
            name=pipeline_pydantic_model.pipeline_name,
            description=pipeline_pydantic_model.pipeline_description or "",
            stacks=runtime_stacks,
            pipeline_settings=pipeline_settings_for_runtime,
            defined_inputs=defined_inputs_for_runtime,
            cli_inputs=cli_inputs or {},
            pydantic_model=pipeline_pydantic_model,  # Pass the parsed Pydantic model
        )

    @classmethod
    def from_dict(
        cls,
        manifest_data: Dict[str, Any],
        manifest_base_dir: Optional[Path] = None,
        cli_inputs: Optional[Dict[str, str]] = None,
        skip_validation: bool = False,
        # Add pydantic_model parameter if from_dict could be called with an already parsed model
        # For now, from_dict does its own Pydantic parsing if manifest_data is raw.
    ) -> "Pipeline":
        """Create a Pipeline instance from a manifest dictionary."""
        # 1. Pydantic Validation and Parsing
        try:
            pipeline_pydantic_model = PipelineManifestModel.model_validate(
                manifest_data
            )
        except PydanticValidationError as e:
            error_messages = []
            for error in e.errors():
                loc_str = " -> ".join(map(str, error["loc"]))
                error_messages.append(
                    f"  - At '{loc_str}': {error['msg']} (Input: {error.get('input')})"
                )
            raise ManifestError(
                "Manifest validation failed (Pydantic):\n" + "\n".join(error_messages)
            )

        # 2. Semantic Validation (if not skipped)
        if not skip_validation:
            from .validation import ManifestValidator

            validator = ManifestValidator(
                pipeline_pydantic_model,
                line_tracker=None,
                manifest_base_dir=manifest_base_dir
                if manifest_base_dir
                else Path(".").resolve(),
            )
            validator.validate_semantic_rules_and_raise_if_errors()

        # 3. Instantiate runtime Pipeline and Stack objects
        defined_inputs_for_runtime: Dict[str, Dict[str, Any]] = {}
        if pipeline_pydantic_model.pipeline_settings.inputs:
            for (
                name,
                p_input_item,
            ) in pipeline_pydantic_model.pipeline_settings.inputs.items():
                defined_inputs_for_runtime[name] = {
                    "type": p_input_item.type,
                    "description": p_input_item.description,
                    "default": p_input_item.default,
                }

        pipeline_settings_for_runtime: Dict[str, Any] = {
            "stack_name_prefix": pipeline_pydantic_model.pipeline_settings.stack_name_prefix,
            "stack_name_suffix": pipeline_pydantic_model.pipeline_settings.stack_name_suffix,
            "default_region": pipeline_pydantic_model.pipeline_settings.default_region,
            "default_profile": pipeline_pydantic_model.pipeline_settings.default_profile,
            "inputs": defined_inputs_for_runtime,
            "default_sam_config": pipeline_pydantic_model.pipeline_settings.default_sam_config,
        }

        runtime_stacks: List[Stack] = []
        effective_base_dir = (
            manifest_base_dir if manifest_base_dir else Path(".").resolve()
        )

        for stack_model in pipeline_pydantic_model.stacks:
            resolved_stack_dir = (effective_base_dir / stack_model.dir).resolve()

            stack_runtime = Stack(
                id=stack_model.id,
                name=stack_model.name or stack_model.id,
                dir=resolved_stack_dir,
                params=stack_model.params,
                description=stack_model.description,
                region=stack_model.region,
                profile=stack_model.profile,
                stack_name_suffix=stack_model.stack_name_suffix,
                if_condition=stack_model.if_condition,
                run_script=stack_model.run_script,
                sam_config_overrides=stack_model.sam_config_overrides,
            )
            runtime_stacks.append(stack_runtime)

        return cls(
            name=pipeline_pydantic_model.pipeline_name,
            description=pipeline_pydantic_model.pipeline_description or "",
            stacks=runtime_stacks,
            pipeline_settings=pipeline_settings_for_runtime,
            defined_inputs=defined_inputs_for_runtime,
            cli_inputs=cli_inputs or {},
            pydantic_model=pipeline_pydantic_model,  # Pass the parsed Pydantic model
        )

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

                    # Check for unknown CLI input keys
        unknown_keys = set(self.cli_inputs.keys()) - set(self.defined_inputs.keys())
        if unknown_keys:
            raise ManifestError(
                f"Unknown CLI input keys provided: {', '.join(sorted(unknown_keys))}"
            )

        # Validate required inputs are provided (CLI or default)
        for input_name, definition in self.defined_inputs.items():
            is_required = definition.get("default") is None

            # Process CLI input if provided
            processed_cli_value = None
            if input_name in self.cli_inputs:
                processed_cli_value = process_cli_input_value(
                    input_name, self.cli_inputs[input_name], definition
                )

            # Check if required input is missing
            # Note: process_cli_input_value returns None for whitespace-only values,
            # ensuring they are treated as not provided for required input validation
            if is_required and processed_cli_value is None:
                raise ManifestError(
                    f"Required input '{input_name}' not provided via CLI and has no default value."
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

        # Validate before deployment (semantic validation by runtime Pipeline object)
        self.validate()

        if not self.pydantic_model:
            # This should ideally not happen if Pipeline was created via from_file or from_dict
            raise ManifestError(
                "Pipeline was not initialized with the Pydantic model. Cannot proceed."
            )

        if len(self.stacks) != len(self.pydantic_model.stacks):
            # This is a sanity check, should not occur if parsing is correct
            raise ManifestError(
                "Mismatch between runtime stacks and Pydantic model stacks count."
            )

        for i, runtime_stack in enumerate(self.stacks):
            pydantic_stack_model = self.pydantic_model.stacks[i]

            # Sanity check IDs, though order is assumed to be preserved
            if runtime_stack.id != pydantic_stack_model.id:
                raise ManifestError(
                    f"ID mismatch at index {i}: runtime stack '{runtime_stack.id}' vs pydantic model '{pydantic_stack_model.id}'."
                )
            self._deploy_stack(runtime_stack, pydantic_stack_model, auto_delete_failed)

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

    def _deploy_stack(
        self,
        stack: Stack,
        pydantic_stack_model: PydanticStackModel,
        auto_delete_failed: bool,
    ) -> None:
        """Deploy a single stack."""
        ui.subheader(f"Processing stack: {stack.id} ({stack.name})")

        if not stack.should_deploy(self.template_processor):
            ui.info(f"Skipping stack '{stack.id}'", "Due to 'if' condition.")
            stack.skipped = True
            return

        global_prefix = self.pipeline_settings.get("stack_name_prefix", "")
        global_suffix = self.pipeline_settings.get("stack_name_suffix", "")

        if global_prefix:
            global_prefix = self.template_processor.process_string(global_prefix)
        if global_suffix:
            global_suffix = self.template_processor.process_string(global_suffix)

        stack.deployed_stack_name = stack.get_stack_name(global_prefix, global_suffix)
        if stack.deployed_stack_name is None:  # Should be set by get_stack_name
            raise StackDeploymentError(
                f"Failed to determine deployed_stack_name for stack '{stack.id}'."
            )

        if auto_delete_failed:
            self._handle_auto_delete(stack)

        console.print(
            f"  Deploying stack [cyan]'{stack.id}'[/cyan] as [green]'{stack.deployed_stack_name}'[/green]..."
        )

        stack_abs_dir = stack.dir.absolute()

        # Fully resolve stack.params before passing to SamConfigManager
        resolved_stack_params_for_samconfig: Dict[str, str] = {}
        if stack.params:  # stack.params are from the runtime Stack object, originally from pipeline.yml
            for key, value in stack.params.items():
                # Ensure all template types, including stack outputs, are resolved for params
                resolved_value = self.template_processor.process_string(str(value))
                resolved_stack_params_for_samconfig[key] = resolved_value

        # Generate samconfig.yaml for the stack
        self.sam_config_manager.generate_samconfig_for_stack(
            stack_dir=stack.dir,
            stack_id=stack.id,
            pydantic_stack_model=pydantic_stack_model,  # Use the passed Pydantic model
            deployed_stack_name=stack.deployed_stack_name,
            effective_region=(
                stack.region or self.pipeline_settings.get("default_region")
            ),
            resolved_stack_params=resolved_stack_params_for_samconfig,
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(stack.dir)
            # samconfig_path is no longer needed for build/deploy calls
            self._run_sam_build(stack)  # Pass stack, no samconfig_path
            self._run_sam_deploy(stack)  # Pass stack, no samconfig_path

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
                processed_script: str = self.template_processor.process_string(
                    stack.run_script
                )
                if processed_script:
                    self._run_post_deployment_script(
                        stack, stack_abs_dir, processed_script
                    )
        finally:
            os.chdir(original_cwd)

    def _run_sam_build(self, stack: Stack) -> None:  # Removed samconfig_path
        """Run sam build for the stack. Relies on samconfig.yaml in stack.dir."""
        cmd = ["sam", "build"]
        # No longer add --config-file; SAM CLI will find samconfig.yaml

        logger.debug(f"Running: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.debug(f"sam build output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            raise StackDeploymentError(
                f"sam build failed for stack '{stack.id}': {e.stderr}"
            )
        except FileNotFoundError:
            raise StackDeploymentError(
                "sam command not found. Please ensure AWS SAM CLI is installed."
            )

    def _run_sam_deploy(self, stack: Stack) -> None:  # Removed samconfig_path
        """Run sam deploy for the stack. Relies on samconfig.yaml in stack.dir."""
        if stack.deployed_stack_name is None:
            raise StackDeploymentError(
                f"Cannot deploy stack {stack.id}, deployed_stack_name is not set."
            )

        # Basic command. All other configs (stack_name, s3_prefix, region, params, capabilities etc.)
        # are expected to be in samconfig.yaml in the stack's CWD.
        cmd = ["sam", "deploy"]

        # The following CLI options are removed as they should be in samconfig.yaml:
        # --stack-name, --s3-prefix, --resolve-s3 (usually true in samconfig)
        # --config-file
        # --region (should be in samconfig)
        # --profile (should be in samconfig)
        # --parameter-overrides (should be in samconfig)
        # --capabilities (should be in samconfig)

        # We might still need to pass --no-confirm-changeset or --confirm-changeset if not in samconfig
        # For now, assume samconfig.yaml handles this or SAM CLI default behavior is acceptable.
        # Example: cmd.append("--no-confirm-changeset") if that's desired default

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
