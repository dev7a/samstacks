"""
Core classes for samstacks pipeline and stack management.
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Tuple, Generator
import shlex
from contextlib import contextmanager
import click


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

# Constants
DEFAULT_EXIT_CODE_ON_ERROR = 1
SAM_NO_CHANGES_MESSAGE = "No changes to deploy"


def _format_pydantic_error_user_friendly(error: dict) -> str:
    """Format a single Pydantic validation error in a user-friendly way."""
    import difflib

    error_type = error.get("type", "")
    msg = error.get("msg", "")
    loc = error.get("loc", ())
    input_value = error.get("input")

    # Create a readable location path
    loc_str = " -> ".join(str(item) for item in loc if item != "__root__")
    if not loc_str:
        loc_str = "manifest root"

    # Handle different types of validation errors with user-friendly messages
    if error_type == "extra_forbidden":
        field_name = str(loc[-1]) if loc else "unknown field"

        # Define valid field names for suggestions
        valid_root_fields = [
            "pipeline_name",
            "pipeline_description",
            "pipeline_settings",
            "stacks",
        ]
        valid_pipeline_settings_fields = [
            "stack_name_prefix",
            "stack_name_suffix",
            "default_region",
            "default_profile",
            "inputs",
            "default_sam_config",
        ]
        valid_stack_fields = [
            "id",
            "name",
            "description",
            "dir",
            "params",
            "stack_name_suffix",
            "region",
            "profile",
            "if",
            "run",
            "sam_config_overrides",
        ]

        # Choose the appropriate valid fields list based on context
        if len(loc) == 1:
            valid_fields = valid_root_fields
        elif len(loc) >= 2 and loc[0] == "pipeline_settings":
            valid_fields = valid_pipeline_settings_fields
        elif len(loc) >= 2 and loc[0] == "stacks":
            valid_fields = valid_stack_fields
        else:
            valid_fields = (
                valid_root_fields + valid_pipeline_settings_fields + valid_stack_fields
            )

        # Find the best suggestion
        suggestions = difflib.get_close_matches(
            field_name, valid_fields, n=1, cutoff=0.6
        )

        if suggestions:
            return f"  - {loc_str}: Unknown field '{field_name}', did you mean '{suggestions[0]}'?"
        else:
            return f"  - {loc_str}: Unknown field '{field_name}' is not allowed"

    elif error_type == "missing":
        field_name = str(loc[-1]) if loc else "field"
        return f"  - {loc_str}: Required field '{field_name}' is missing"

    elif error_type in [
        "string_type",
        "int_type",
        "float_type",
        "bool_type",
        "list_type",
        "dict_type",
    ]:
        expected_type = error_type.replace("_type", "")
        field_name = str(loc[-1]) if loc else "field"
        actual_type = type(input_value).__name__ if input_value is not None else "null"
        return f"  - {loc_str}: Field '{field_name}' must be a {expected_type}, got {actual_type}"

    elif "enum" in error_type.lower():
        field_name = str(loc[-1]) if loc else "field"
        # Extract allowed values from the message if possible
        if "permitted" in msg:
            return f"  - {loc_str}: Field '{field_name}' has invalid value. {msg}"
        else:
            return f"  - {loc_str}: Field '{field_name}' has invalid value"

    else:
        # Fallback for other error types - clean up the message
        clean_msg = msg.replace(
            "Extra inputs are not permitted", "contains unknown fields"
        )
        clean_msg = clean_msg.replace("Field required", "is required")
        return f"  - {loc_str}: {clean_msg}"


def _format_pydantic_validation_errors(e: PydanticValidationError) -> str:
    """Format Pydantic validation errors in a user-friendly way."""
    error_count = len(e.errors())

    if error_count == 1:
        header = "Found 1 validation error:"
    else:
        header = f"Found {error_count} validation errors:"

    formatted_errors = []
    for error in e.errors():
        formatted_errors.append(_format_pydantic_error_user_friendly(error))  # type: ignore

    return header + "\n" + "\n".join(formatted_errors)


def _read_deployed_stack_name_from_samconfig(
    stack_dir: Path, stack_id: str, sam_env: str = "default"
) -> Optional[str]:
    """
    Read the actual deployed stack name from a stack's samconfig.yaml file.

    Args:
        stack_dir: Path to the stack directory
        stack_id: Stack ID for error reporting
        sam_env: SAM environment to read from (defaults to "default")

    Returns:
        The deployed stack name if found, None if file doesn't exist or stack_name not found
    """
    import yaml

    samconfig_path = stack_dir / "samconfig.yaml"

    if not samconfig_path.exists():
        logger.debug(
            f"No samconfig.yaml found for stack '{stack_id}' at {samconfig_path}"
        )
        return None

    try:
        with open(samconfig_path, "r", encoding="utf-8") as f:
            samconfig_data = yaml.safe_load(f)

        if not isinstance(samconfig_data, dict):
            logger.warning(
                f"Invalid samconfig.yaml format for stack '{stack_id}': not a dictionary"
            )
            return None

        # Navigate to default.deploy.parameters.stack_name
        env_config = samconfig_data.get(sam_env, {})
        if not isinstance(env_config, dict):
            logger.debug(
                f"No '{sam_env}' environment found in samconfig.yaml for stack '{stack_id}'"
            )
            return None

        deploy_config = env_config.get("deploy", {})
        if not isinstance(deploy_config, dict):
            logger.debug(
                f"No 'deploy' configuration found in samconfig.yaml for stack '{stack_id}'"
            )
            return None

        parameters = deploy_config.get("parameters", {})
        if not isinstance(parameters, dict):
            logger.debug(
                f"No 'parameters' found in deploy configuration for stack '{stack_id}'"
            )
            return None

        stack_name = parameters.get("stack_name")
        if isinstance(stack_name, str) and stack_name.strip():
            logger.debug(
                f"Found deployed stack name '{stack_name}' for stack '{stack_id}'"
            )
            return stack_name.strip()
        else:
            logger.debug(
                f"No valid 'stack_name' found in samconfig.yaml for stack '{stack_id}'"
            )
            return None

    except Exception as e:
        logger.warning(f"Error reading samconfig.yaml for stack '{stack_id}': {e}")
        return None


def _handle_sam_command_exception(e: Exception, operation: str, stack_id: str) -> None:
    """Handle common exception patterns for SAM commands."""
    if isinstance(e, StackDeploymentError):
        raise  # Re-raise StackDeploymentError as-is
    else:
        # Handle unexpected errors
        logger.error(
            f"An unexpected error occurred during {operation} for stack '{stack_id}': {e}"
        )
        raise StackDeploymentError(
            f"Unexpected error during {operation} for stack '{stack_id}': {type(e).__name__} - {e}"
        ) from e


@contextmanager
def temporary_env(
    env_updates: Optional[Dict[str, str]] = None,
) -> Generator[None, None, None]:
    """Temporarily update os.environ with env_updates and restore on exit."""
    original_env = os.environ.copy()

    if env_updates:
        os.environ.update(env_updates)
        logger.debug(f"Temporarily updated os.environ with: {env_updates}")

    try:
        yield
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)
        logger.debug("Restored original os.environ after temporary update.")


@contextmanager
def change_directory(target_dir: Union[str, Path]) -> Generator[None, None, None]:
    """Context manager for safely changing directories."""
    original_cwd = os.getcwd()
    try:
        os.chdir(str(target_dir))
        yield
    finally:
        os.chdir(original_cwd)


def _run_command_with_stderr_capture(
    cmd_args: List[str], cwd: str, env_dict: Optional[Dict[str, str]] = None
) -> Tuple[int, str]:
    """
    Run a command capturing only stderr while allowing stdout to stream directly to terminal.
    This provides real-time feedback to users while capturing errors for programmatic handling.

    Args:
        cmd_args: Command and arguments to execute
        cwd: Working directory for the command
        env_dict: Environment variables for the subprocess

    Returns:
        Tuple of (exit_code, stderr_output)
    """
    logger.debug(
        f"Executing with stderr capture: {' '.join(shlex.quote(str(s)) for s in cmd_args)} in {cwd}"
    )

    try:
        # Run with stdout inherited (streams to terminal) and stderr captured
        result = subprocess.run(
            cmd_args,
            cwd=cwd,
            env=env_dict,
            stdin=subprocess.DEVNULL,  # Prevent hangs on unexpected prompts
            stdout=None,  # Inherit stdout - streams directly to terminal
            stderr=subprocess.PIPE,  # Capture stderr for error detection
            text=True,
            check=False,  # Don't raise on non-zero exit, we'll handle it
        )

        stderr_output = result.stderr or ""

        logger.debug(
            f"Command '{cmd_args[0]}' finished with exit code {result.returncode}"
        )
        if stderr_output:
            logger.debug(f"Command stderr output:\n{stderr_output.strip()}")

        return result.returncode, stderr_output

    except FileNotFoundError as e:
        logger.error(f"Command not found: {cmd_args[0]}. Details: {e}")
        raise StackDeploymentError(
            f"Command not found: {cmd_args[0]}. Ensure it's in your PATH."
        ) from e
    except Exception as e:
        logger.error(f"Error running command {' '.join(cmd_args)}: {e}")
        raise StackDeploymentError(
            f"Error running command {' '.join(cmd_args)}: {e}"
        ) from e


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
        self.pydantic_model = pydantic_model
        self.logger = logger  # Initialize logger instance attribute

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

        # Process template expressions in pipeline_settings fields
        template_supported_fields = [
            "stack_name_prefix",
            "stack_name_suffix",
            "default_region",
            "default_profile",
        ]
        for field_name in template_supported_fields:
            field_value = self.pipeline_settings.get(field_name)
            if isinstance(field_value, str) and "${{" in field_value:
                try:
                    processed_value = self.template_processor.process_string(
                        field_value
                    )
                    self.pipeline_settings[field_name] = processed_value
                except TemplateError as e:
                    raise ManifestError(
                        f"Error processing template expression in pipeline_settings.{field_name}: {e}"
                    ) from e

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
            user_friendly_message = _format_pydantic_validation_errors(e)
            raise ManifestError(user_friendly_message)

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
            user_friendly_message = _format_pydantic_validation_errors(e)
            raise ManifestError(user_friendly_message)

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

    def deploy(self, auto_delete_failed: bool = False) -> None:
        """Deploy all stacks in the pipeline."""
        ui.header(f"Starting deployment of pipeline: {self.name}")

        # Display pipeline description if available
        if self.description and self.description.strip():
            ui.info("Pipeline Description", self.description.strip())
            console.print()  # Add visual separation

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
            ui.warning(
                "Auto-delete skipped",
                f"Stack '{stack.id}' has no deployed name set for auto-delete operations",
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

        with change_directory(stack.dir):
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
                    # Add visual separation after the table
                    console.print()
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

    def _run_sam_build(self, stack: Stack) -> None:
        """Run sam build for the stack. Relies on samconfig.yaml in stack.dir."""
        cmd = ["sam", "build"]
        self.logger.debug(
            f"Running: {' '.join(shlex.quote(str(s)) for s in cmd)} in {stack.dir}"
        )

        # Clear header to distinguish SAM output from samstacks output
        ui.subheader(f"Executing SAM Build for '{stack.id}'")

        effective_env = self._get_effective_env(stack.region, stack.profile)
        try:
            # Use stderr capture only - stdout streams directly to terminal for real-time feedback
            return_code, stderr_output = _run_command_with_stderr_capture(
                cmd, cwd=str(stack.dir), env_dict=effective_env
            )

            # Log stderr at debug level if present
            if stderr_output:
                self.logger.debug(
                    f"sam build stderr for stack '{stack.id}':\n{stderr_output.strip()}"
                )

            if return_code != 0:
                error_detail = (
                    stderr_output.strip()
                    if stderr_output
                    else "Build failed - check output above for details."
                )
                self.logger.debug(
                    f"sam build failed for stack '{stack.id}'. RC: {return_code}"
                )
                ui.error(
                    "Build failed",
                    f"sam build failed for stack '{stack.id}': {error_detail}",
                )
                raise StackDeploymentError(
                    f"sam build failed for stack '{stack.id}': {error_detail}"
                )
            else:
                ui.info("Build completed", f"Successfully built stack '{stack.id}'")

        except Exception as e:
            _handle_sam_command_exception(e, "sam build", stack.id)

    def _run_sam_deploy(self, stack: Stack) -> None:
        """Run sam deploy for the stack. Relies on samconfig.yaml in stack.dir."""
        if stack.deployed_stack_name is None:
            raise StackDeploymentError(
                f"Cannot deploy stack {stack.id}, deployed_stack_name is not set."
            )
        cmd = ["sam", "deploy"]
        self.logger.debug(
            f"Running: {' '.join(shlex.quote(str(s)) for s in cmd)} in {stack.dir}"
        )

        # Clear header to distinguish SAM output from samstacks output
        ui.subheader(f"Executing SAM Deploy for '{stack.id}'")

        effective_env = self._get_effective_env(stack.region, stack.profile)

        try:
            # Use stderr capture only - stdout streams directly to terminal for real-time feedback
            return_code, stderr_output = _run_command_with_stderr_capture(
                cmd, cwd=str(stack.dir), env_dict=effective_env
            )

            if return_code != 0:
                # Handle "No changes to deploy" case first - this might be in stderr
                if SAM_NO_CHANGES_MESSAGE in stderr_output:
                    ui.info(
                        f"Stack '{stack.id}' is already up to date",
                        "No changes deployed.",
                    )
                    self._cleanup_just_created_no_update_changeset(stack)
                    return
                else:
                    error_detail = (
                        stderr_output.strip()
                        if stderr_output
                        else "Deploy failed - check output above for details."
                    )
                    self.logger.debug(
                        f"sam deploy failed for stack '{stack.id}'. RC: {return_code}"
                    )
                    ui.error(
                        "Deployment failed",
                        f"sam deploy failed for stack '{stack.id}': {error_detail}",
                    )
                    raise StackDeploymentError(
                        f"sam deploy failed for stack '{stack.id}': {error_detail}"
                    )
            # Deploy successful (RC=0) - success will be indicated by the real-time output

        except Exception as e:
            _handle_sam_command_exception(e, "sam deploy", stack.id)

    def _retrieve_stack_outputs(self, stack: Stack) -> None:
        """Retrieve outputs from the deployed CloudFormation stack."""
        if stack.deployed_stack_name is None:  # Guard
            ui.warning(
                "Output retrieval skipped",
                f"Stack '{stack.id}' has no deployed name set",
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

            self.logger.debug(
                f"Retrieved outputs for stack '{stack.id}': {stack.outputs}"
            )

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

        logger.debug(
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

    def _get_effective_env(
        self, stack_region: Optional[str], stack_profile: Optional[str]
    ) -> Dict[str, str]:
        """Prepares a copy of the current environment, updated with stack-specific AWS region/profile and color forcing."""
        effective_env = os.environ.copy()

        final_region = stack_region or self.pipeline_settings.get("default_region")
        final_profile = stack_profile or self.pipeline_settings.get("default_profile")

        if final_region:
            effective_env["AWS_DEFAULT_REGION"] = final_region
            self.logger.debug(
                f"Setting AWS_DEFAULT_REGION={final_region} for subprocess env."
            )
        # If not set by samstacks, existing AWS_DEFAULT_REGION from os.environ will be used.

        if final_profile:
            effective_env["AWS_PROFILE"] = final_profile
            self.logger.debug(
                f"Setting AWS_PROFILE={final_profile} for subprocess env."
            )
        # If not set by samstacks, existing AWS_PROFILE from os.environ will be used.

        effective_env["FORCE_COLOR"] = "1"
        effective_env["CLICOLOR_FORCE"] = "1"
        self.logger.debug("Adding FORCE_COLOR=1, CLICOLOR_FORCE=1 to subprocess env.")

        return effective_env

    def delete(self, no_prompts: bool = False, dry_run: bool = False) -> None:
        """Delete all stacks in the pipeline in reverse dependency order."""
        ui.header(f"Deleting pipeline: {self.name}")

        # Display pipeline description if available
        if self.description and self.description.strip():
            ui.info("Pipeline Description", self.description.strip())
            console.print()  # Add visual separation

        # Validate pipeline first
        self.validate()

        # Determine deletion order (reverse of deployment order)
        deletion_order = self._get_deletion_order()

        if not deletion_order:
            ui.info("No stacks to delete", "Pipeline contains no stacks")
            return

        # Show what will be deleted
        ui.subheader("Stacks to be deleted (in order):")
        stacks_with_deployment_info = []

        for i, stack in enumerate(deletion_order, 1):
            # Try to get the actual deployed stack name from samconfig.yaml
            deployed_stack_name = _read_deployed_stack_name_from_samconfig(
                stack.dir, stack.id
            )

            if deployed_stack_name:
                # Show the actual deployed stack name from samconfig.yaml
                ui.detail(
                    f"{i}. {stack.id}", f"CloudFormation stack: {deployed_stack_name}"
                )
                stacks_with_deployment_info.append((stack, deployed_stack_name, True))
            else:
                # Fallback: compute the expected name but mark as not deployed
                global_prefix = self.pipeline_settings.get("stack_name_prefix", "")
                global_suffix = self.pipeline_settings.get("stack_name_suffix", "")

                # Resolve template expressions for display purposes
                if global_prefix:
                    global_prefix = self.template_processor.process_string(
                        global_prefix
                    )
                if global_suffix:
                    global_suffix = self.template_processor.process_string(
                        global_suffix
                    )

                computed_stack_name = stack.get_stack_name(global_prefix, global_suffix)
                ui.detail(
                    f"{i}. {stack.id}",
                    f"Expected stack: {computed_stack_name} (not deployed)",
                )
                stacks_with_deployment_info.append((stack, computed_stack_name, False))

        # Count how many stacks are actually deployed
        deployed_count = sum(
            1 for _, _, is_deployed in stacks_with_deployment_info if is_deployed
        )
        not_deployed_count = len(stacks_with_deployment_info) - deployed_count

        if deployed_count == 0:
            ui.info(
                "No deployed stacks to delete",
                "All stacks in the pipeline are not deployed",
            )
            return

        if not_deployed_count > 0:
            ui.info(
                f"Found {not_deployed_count} stack(s) not yet deployed",
                "These will be skipped during deletion",
            )

        # Handle dry-run mode
        if dry_run:
            ui.info("Dry run complete", "No stacks were actually deleted")
            return

        # Interactive confirmation unless no_prompts is set
        if not no_prompts:
            ui.warning(
                "Destructive operation",
                "This will permanently delete all CloudFormation stacks and their resources",
            )
            if not click.confirm("Do you want to proceed with deletion?"):
                ui.info("Deletion cancelled", "No stacks were deleted")
                return

        # Perform actual deletion
        failed_deletions = []
        successful_deletions = []
        skipped_deletions = []

        for stack, stack_name, is_deployed in stacks_with_deployment_info:
            if not is_deployed:
                # Skip stacks that were never deployed
                skipped_deletions.append(stack.id)
                ui.info(
                    f"Skipping stack '{stack.id}'",
                    "Not deployed (no samconfig.yaml found)",
                )
                continue

            try:
                self._delete_stack(stack)
                successful_deletions.append(stack.id)
            except Exception as e:
                self.logger.error(f"Failed to delete stack '{stack.id}': {e}")
                failed_deletions.append((stack.id, str(e)))
                # Continue with remaining stacks
                ui.warning(
                    f"Stack deletion failed: {stack.id}",
                    f"Error: {e}. Continuing with remaining stacks...",
                )

        # Summary report
        ui.subheader("Deletion Summary")
        if successful_deletions:
            ui.info(
                f"Successfully deleted ({len(successful_deletions)})",
                ", ".join(successful_deletions),
            )
        if skipped_deletions:
            ui.info(
                f"Skipped ({len(skipped_deletions)})",
                ", ".join(skipped_deletions) + " (not deployed)",
            )
        if failed_deletions:
            ui.error(
                f"Failed to delete ({len(failed_deletions)})",
                "; ".join([f"{stack}: {error}" for stack, error in failed_deletions]),
            )

        if failed_deletions:
            raise StackDeploymentError(
                f"Failed to delete {len(failed_deletions)} stack(s). See errors above."
            )

    def _get_deletion_order(self) -> List[Stack]:
        """Get stacks in deletion order (reverse of deployment dependency order).

        Stacks should be deleted in reverse dependency order:
        - Consumers (dependent stacks) first
        - Producers (stacks with outputs used by others) last
        """
        # Filter out stacks that shouldn't be deployed (due to 'if' conditions)
        deployable_stacks = []
        for stack in self.stacks:
            if stack.should_deploy(self.template_processor):
                deployable_stacks.append(stack)
            else:
                self.logger.debug(
                    f"Skipping stack '{stack.id}' from deletion order due to 'if' condition"
                )

        # For deletion, we want the reverse of deployment order
        # The deployment order follows dependencies (producers before consumers)
        # So deletion order should be consumers before producers
        return list(reversed(deployable_stacks))

    def _delete_stack(self, stack: Stack) -> None:
        """Delete a single stack using sam delete --no-prompts."""
        ui.subheader(f"Executing SAM Delete for '{stack.id}'")

        # Use sam delete with --no-prompts to avoid interactive confirmation
        cmd = ["sam", "delete", "--no-prompts"]
        self.logger.debug(
            f"Running: {' '.join(shlex.quote(str(s)) for s in cmd)} in {stack.dir}"
        )

        effective_env = self._get_effective_env(stack.region, stack.profile)

        try:
            # Use stderr capture only - stdout streams directly to terminal for real-time feedback
            return_code, stderr_output = _run_command_with_stderr_capture(
                cmd, cwd=str(stack.dir), env_dict=effective_env
            )

            if return_code != 0:
                error_detail = (
                    stderr_output.strip()
                    if stderr_output
                    else "Delete failed - check output above for details."
                )
                self.logger.debug(
                    f"sam delete failed for stack '{stack.id}'. RC: {return_code}"
                )
                ui.error(
                    "Deletion failed",
                    f"sam delete failed for stack '{stack.id}': {error_detail}",
                )
                raise StackDeploymentError(
                    f"sam delete failed for stack '{stack.id}': {error_detail}"
                )
            else:
                ui.info(
                    "Deletion completed", f"Successfully deleted stack '{stack.id}'"
                )

        except Exception as e:
            _handle_sam_command_exception(e, "sam delete", stack.id)
