# samstacks/samconfig_manager.py
"""
Manages the generation and persistence of samconfig.yaml for individual stacks.
"""

import yaml
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional
import logging
import tomllib

from . import ui  # Import UI module
from .pipeline_models import SamConfigContentType, StackModel as PydanticStackModel
from .templating import TemplateProcessor
from .exceptions import ManifestError  # Or a more specific SamConfigError

logger = logging.getLogger(__name__)


class SamConfigManager:
    """
    Handles the creation and management of samconfig.yaml files for stacks
    based on pipeline configurations.
    """

    def __init__(
        self,
        pipeline_name: str,
        pipeline_description: Optional[str],
        default_sam_config_from_pipeline: Optional[SamConfigContentType],
        template_processor: TemplateProcessor,
    ):
        self.pipeline_name = pipeline_name
        self.pipeline_description = pipeline_description
        # Ensure default_sam_config is always a dict for easier processing
        self.default_sam_config_from_pipeline = (
            self._deep_copy_dict(default_sam_config_from_pipeline)
            if default_sam_config_from_pipeline
            else {}
        )
        self.template_processor = template_processor
        self.logger = logger

    def _deep_copy(self, obj: Any) -> Any:
        """Deep copy any object using YAML serialization."""
        if obj is None:
            return None
        # Using yaml load/dump for a deep copy that handles nested structures well.
        # More robust than manual recursion for complex Any types.
        return yaml.safe_load(yaml.safe_dump(obj))

    def _deep_copy_dict(self, d: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Deep copy a dictionary, returning empty dict if None."""
        if d is None:
            return {}
        result = self._deep_copy(d)
        # Type cast since we know input was a dict and YAML round-trip preserves dict type
        return result if isinstance(result, dict) else {}

    def _deep_copy_any(self, obj: Any) -> Any:
        """Deep copy any object (dict, list, or primitive) using the unified helper."""
        return self._deep_copy(obj)

    def _deep_merge_dicts(
        self, base: Dict[str, Any], updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Recursively merges 'updates' dict into 'base' dict.
        'updates' values take precedence for conflicting keys.
        Lists from 'updates' replace lists in 'base' entirely.
        """
        merged = self._deep_copy_dict(base)
        for key, value_updates in updates.items():
            value_base = merged.get(key)
            if isinstance(value_base, dict) and isinstance(value_updates, dict):
                merged[key] = self._deep_merge_dicts(value_base, value_updates)
            else:
                # For lists, primitives, or type mismatches: replace entirely with deep copy
                # Lists from updates replace lists in base completely (no element-wise merging)
                merged[key] = (
                    self._deep_copy_any(value_updates)
                    if isinstance(value_updates, (dict, list))
                    else value_updates
                )
        return merged

    def _apply_stack_specific_configs(
        self,
        config_dict: Dict[str, Any],
        deployed_stack_name: str,
        effective_region: Optional[str],
        pipeline_driven_params_map: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Ensures essential overrides like stack_name, s3_prefix, region,
        and merges pipeline-driven parameters into parameter_overrides.
        Also ensures critical defaults like beta_features are set if not present.
        Operates on a deep copy.
        """
        output_config = self._deep_copy_dict(config_dict)

        if "version" not in output_config:
            output_config["version"] = 0.1

        # Ensure default.global.parameters.beta_features is set to prevent prompts
        # This needs to be applied carefully to the correct environment and command section.
        # For SAM CLI, global parameters are typically under an environment (e.g., "default")
        # and a "global" command key.
        env_name_for_global = "default"  # Or determine from context if multi-env is more deeply supported here
        global_cmd_key = "global"

        env_config_for_global = output_config.setdefault(env_name_for_global, {})
        if not isinstance(env_config_for_global, dict):  # Should be a dict
            env_config_for_global = {}
            output_config[env_name_for_global] = env_config_for_global

        global_settings = env_config_for_global.setdefault(global_cmd_key, {})
        if not isinstance(global_settings, dict):
            global_settings = {}
            env_config_for_global[global_cmd_key] = global_settings

        global_params = global_settings.setdefault("parameters", {})
        if not isinstance(global_params, dict):
            global_params = {}
            global_settings["parameters"] = global_params

        # Coerce beta_features to boolean if it exists and is a string like 'yes'/'no'
        if "beta_features" in global_params:
            val = global_params["beta_features"]
            if isinstance(val, str):
                if val.lower() in ["true", "yes", "1", "on"]:
                    global_params["beta_features"] = True
                elif val.lower() in ["false", "no", "0", "off"]:
                    global_params["beta_features"] = False
                else:
                    # If it's a string but not a recognizable boolean, remove or warn, then default
                    self.logger.warning(
                        f"Unrecognized string value '{val}' for 'beta_features' in samconfig. Will default to False."
                    )
                    del global_params[
                        "beta_features"
                    ]  # Remove to allow defaulting below
            elif not isinstance(val, bool):
                self.logger.warning(
                    f"Non-boolean, non-string value '{val}' for 'beta_features' in samconfig. Will default to False."
                )
                del global_params["beta_features"]  # Remove to allow defaulting below

        # Ensure beta_features is present and a boolean, defaulting to False
        if "beta_features" not in global_params or not isinstance(
            global_params["beta_features"], bool
        ):
            self.logger.debug(
                "Setting/ensuring 'beta_features: False' in default.global.parameters to avoid SAM CLI prompts or use valid boolean."
            )
            global_params["beta_features"] = False

        # --- Standard deploy parameters handling ---
        env_name_for_deploy = "default"  # Target environment for core deploy settings
        cmd_name_for_deploy = "deploy"

        env_config_for_deploy = output_config.setdefault(env_name_for_deploy, {})
        if not isinstance(env_config_for_deploy, dict):
            env_config_for_deploy = {}
            output_config[env_name_for_deploy] = env_config_for_deploy

        cmd_config_for_deploy = env_config_for_deploy.setdefault(
            cmd_name_for_deploy, {}
        )
        if not isinstance(cmd_config_for_deploy, dict):
            cmd_config_for_deploy = {}
            env_config_for_deploy[cmd_name_for_deploy] = cmd_config_for_deploy

        params_section = cmd_config_for_deploy.setdefault("parameters", {})
        if not isinstance(params_section, dict):
            params_section = {}
            cmd_config_for_deploy["parameters"] = params_section

        params_section["stack_name"] = deployed_stack_name
        params_section["s3_prefix"] = deployed_stack_name
        params_section.setdefault("resolve_s3", True)
        params_section.setdefault("confirm_changeset", False)

        # Pipeline region settings (default_region or stack-specific region) always override local config
        if effective_region:
            params_section["region"] = effective_region

        # Parameter overrides are driven *only* by pipeline_driven_params_map (from stack.params)
        # Any "parameter_overrides" key from samconfig.toml or default_sam_config is ignored here,
        # as stack.params is the explicit way to set these for samstacks.
        if pipeline_driven_params_map:
            param_override_pairs = []
            for key, value in pipeline_driven_params_map.items():
                str_value = str(value)
                # SAM CLI parameter override values require specific quoting:
                # - Empty strings must be `Key=\"\"`
                # - Values with spaces or equals signs must be `Key=\"Value With Space\"`
                # - Other values can be `Key=Value`
                if str_value == "":
                    formatted_pair = f'{key}=""'
                elif " " in str_value or "=" in str_value:
                    processed_value = str_value.replace(
                        '"', '\\"'
                    )  # Escape existing double quotes
                    formatted_pair = f'{key}="{processed_value}"'
                else:
                    formatted_pair = f"{key}={str_value}"
                param_override_pairs.append(formatted_pair)
            params_section["parameter_overrides"] = param_override_pairs
            self.logger.debug(
                f"Set parameter_overrides for {deployed_stack_name}: {params_section['parameter_overrides']}"
            )
        elif "parameter_overrides" in params_section:
            # If pipeline_driven_params_map is empty, remove any pre-existing parameter_overrides from config_dict
            self.logger.debug(
                f"No pipeline-driven params for {deployed_stack_name}, removing pre-existing 'parameter_overrides' from samconfig."
            )
            del params_section["parameter_overrides"]

        # Convert tags from string format to array format if needed
        if "tags" in params_section:
            tags_value = params_section["tags"]
            if isinstance(tags_value, str) and "\n" in tags_value:
                # Convert newline-separated string to array
                tag_list = [
                    tag.strip() for tag in tags_value.split("\n") if tag.strip()
                ]
                params_section["tags"] = tag_list
                self.logger.debug(
                    f"Converted tags from string to array for {deployed_stack_name}: {tag_list}"
                )

        return output_config

    def generate_samconfig_for_stack(
        self,
        stack_dir: Path,
        stack_id: str,
        pydantic_stack_model: PydanticStackModel,
        deployed_stack_name: str,
        effective_region: Optional[str],
        resolved_stack_params: Dict[str, str],
    ) -> Path:
        """
        Generates and writes the samconfig.yaml for a given stack.
        Prioritizes .toml, then .yaml, then .yml for existing local config.
        Returns the path to the generated samconfig.yaml file.
        """
        target_samconfig_path = stack_dir / "samconfig.yaml"

        existing_toml_path = stack_dir / "samconfig.toml"
        backup_toml_path = stack_dir / "samconfig.toml.bak"

        existing_yaml_path = (
            stack_dir / "samconfig.yaml"
        )  # This is also target_samconfig_path
        backup_yaml_path = stack_dir / "samconfig.yaml.bak"

        existing_yml_path = stack_dir / "samconfig.yml"
        backup_yml_path = stack_dir / "samconfig.yml.bak"

        config_local_base: Dict[str, Any] = {}
        loaded_from_local = False

        # 1. Backup existing files and load local config if present
        # Priority: .toml, then .yaml, then .yml
        if existing_toml_path.is_file():
            ui.info("Existing samconfig.toml found", "Backing up.")
            if backup_toml_path.exists():
                os.remove(backup_toml_path)
            shutil.move(str(existing_toml_path), str(backup_toml_path))
            try:
                with open(backup_toml_path, "rb") as f_local_bak:
                    config_local_base = tomllib.load(f_local_bak)
                self.logger.debug(f"Loaded base config from {backup_toml_path.name}")
                loaded_from_local = True
            except Exception as e:
                self.logger.warning(
                    f"Could not parse {backup_toml_path.name}: {e}. Starting with empty base."
                )

        # If a .yaml/.yml exists and no .toml was processed, it might be the source or a leftover.
        # We always generate fresh, but need to back up what would be overwritten.
        if (
            existing_yaml_path.is_file()
            and existing_yaml_path.resolve() == target_samconfig_path.resolve()
        ):
            ui.info("Existing samconfig.yaml found", "Backing up.")
            if backup_yaml_path.exists():
                os.remove(backup_yaml_path)
            shutil.move(str(target_samconfig_path), str(backup_yaml_path))
            if (
                not loaded_from_local
            ):  # If .toml wasn't found, try to load this .yaml.bak as base
                try:
                    with open(backup_yaml_path, "r", encoding="utf-8") as f_local_bak:
                        config_local_base = yaml.safe_load(f_local_bak) or {}
                    self.logger.debug(
                        f"Loaded base config from {backup_yaml_path.name}"
                    )
                    loaded_from_local = True
                except Exception as e:
                    self.logger.warning(
                        f"Could not parse {backup_yaml_path.name}: {e}. Starting with empty base."
                    )
                    config_local_base = {}

        if (
            existing_yml_path.is_file()
        ):  # Check for .yml if .yaml wasn't the target and not loaded
            if (
                not loaded_from_local
                or existing_yml_path.resolve() == target_samconfig_path.resolve()
            ):  # if target happens to be .yml
                ui.info("Existing samconfig.yml found", "Backing up.")
                if backup_yml_path.exists():
                    os.remove(backup_yml_path)
                shutil.move(str(existing_yml_path), str(backup_yml_path))
                if not loaded_from_local:
                    try:
                        with open(
                            backup_yml_path, "r", encoding="utf-8"
                        ) as f_local_bak:
                            config_local_base = yaml.safe_load(f_local_bak) or {}
                        self.logger.debug(
                            f"Loaded base config from {backup_yml_path.name}"
                        )
                        loaded_from_local = (
                            True  # Mark as successfully loaded from local
                        )
                    except Exception as e:
                        self.logger.warning(
                            f"Could not parse {backup_yml_path.name}: {e}. Starting with empty base."
                        )
                        config_local_base = {}

        # 2. Derive Config_Pipeline_Defined from pipeline.yml settings
        config_pipeline_defined = self._deep_copy_dict(
            self.default_sam_config_from_pipeline
        )
        if pydantic_stack_model.sam_config_overrides:
            config_pipeline_defined = self._deep_merge_dicts(
                config_pipeline_defined,
                pydantic_stack_model.sam_config_overrides,
            )

        # 3. Deep Merge local base with pipeline-defined (pipeline takes precedence)
        merged_config_base = self._deep_merge_dicts(
            config_local_base, config_pipeline_defined
        )
        if not merged_config_base and (config_local_base or config_pipeline_defined):
            self.logger.debug(
                "Merge result is empty, but sources were not. Check merge logic or inputs."
            )

        # 4. Materialize merged_config_base (resolve env, inputs, pipeline templates)
        merged_config_materialized = self.template_processor.process_structure(
            merged_config_base,
            pipeline_name=self.pipeline_name,
            pipeline_description=self.pipeline_description,
        )

        # 5. Apply stack-specific computed values and merge resolved_stack_params
        final_config = self._apply_stack_specific_configs(
            merged_config_materialized,
            deployed_stack_name,
            effective_region,
            resolved_stack_params,
        )

        # 6. Write Final_Config to target_samconfig_path (which is always samconfig.yaml)
        try:
            with open(target_samconfig_path, "w", encoding="utf-8") as f_yaml:
                yaml.dump(
                    final_config,
                    f_yaml,
                    sort_keys=False,
                    default_flow_style=False,
                    indent=2,
                )
            self.logger.debug(
                f"Generated {target_samconfig_path.name} for stack '{stack_id}' at '{target_samconfig_path}'."
            )
        except Exception as e:
            self.logger.error(
                f"Failed to write {target_samconfig_path.name} for stack '{stack_id}': {e}"
            )
            raise ManifestError(
                f"Failed to write {target_samconfig_path.name} for stack '{stack_id}': {e}"
            ) from e

        return target_samconfig_path

    def generate_external_config_file(
        self,
        config_path: Path,
        stack_dir: Path,
        stack_id: str,
        pydantic_stack_model: PydanticStackModel,
        deployed_stack_name: str,
        effective_region: Optional[str],
        resolved_stack_params: Dict[str, str],
    ) -> Path:
        """
        Generates and writes an external SAM configuration file at the specified path.
        This does NOT touch any local samconfig files in stack directories.
        Returns the path to the generated external config file.
        """
        # Ensure the target directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Backup existing external config file if it exists
        if config_path.exists():
            backup_path = config_path.with_suffix(config_path.suffix + ".bak")
            ui.info(
                "Existing external config found", f"Backing up to {backup_path.name}"
            )
            if backup_path.exists():
                backup_path.unlink()  # Remove old backup
            shutil.move(str(config_path), str(backup_path))

        # Start with pipeline-defined config (no local config merging for external files)
        config_pipeline_defined = self._deep_copy_dict(
            self.default_sam_config_from_pipeline
        )
        if pydantic_stack_model.sam_config_overrides:
            config_pipeline_defined = self._deep_merge_dicts(
                config_pipeline_defined,
                pydantic_stack_model.sam_config_overrides,
            )

        # Materialize the config (resolve template expressions)
        materialized_config = self.template_processor.process_structure(
            config_pipeline_defined,
            pipeline_name=self.pipeline_name,
            pipeline_description=self.pipeline_description,
        )

        # Apply stack-specific configs and parameters
        final_config = self._apply_stack_specific_configs(
            materialized_config,
            deployed_stack_name,
            effective_region,
            resolved_stack_params,
        )

        # Add template references for both build and deploy
        final_config = self._add_template_references(
            final_config, config_path, stack_dir
        )

        # Write the external config file
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    final_config,
                    f,
                    sort_keys=False,
                    default_flow_style=False,
                    indent=2,
                )
            self.logger.debug(
                f"Generated external config for stack '{stack_id}' at '{config_path}'"
            )
            ui.info("External config generated", f"Created {config_path}")
        except Exception as e:
            self.logger.error(
                f"Failed to write external config for stack '{stack_id}': {e}"
            )
            raise ManifestError(
                f"Failed to write external config for stack '{stack_id}': {e}"
            ) from e

        return config_path

    def _add_template_references(
        self, config: Dict[str, Any], config_path: Path, stack_dir: Path
    ) -> Dict[str, Any]:
        """
        Add template file references to the config for external config files.
        Calculates relative path from config location to stack template.
        Supports bootstrapping where template files don't exist yet.
        """
        try:
            # Find the template file in the stack directory (or default to template.yaml)
            template_candidates = [
                stack_dir / "template.yaml",
                stack_dir / "template.yml",
                stack_dir / "template.json",
            ]

            template_file = None
            for candidate in template_candidates:
                if candidate.exists():
                    template_file = candidate
                    break

            if not template_file:
                # Default to template.yaml even if it doesn't exist (supports bootstrapping)
                template_file = stack_dir / "template.yaml"
                self.logger.debug(
                    f"Template file not found in stack directory, defaulting to {template_file} for bootstrapping"
                )

            # Calculate relative path from config file to template
            # Convert absolute paths to relative paths from current working directory
            # This ensures the paths work correctly when SAM CLI is run
            try:
                cwd = Path.cwd()
                config_relative_to_cwd = config_path.relative_to(cwd)
                template_relative_to_cwd = template_file.relative_to(cwd)

                # Calculate relative path from config directory to template
                relative_template_path = os.path.relpath(
                    template_relative_to_cwd, config_relative_to_cwd.parent
                )

                self.logger.debug(
                    f"Calculated template path from working directory: {template_relative_to_cwd} -> {relative_template_path}"
                )
            except ValueError:
                # Fallback to original method if paths are not relative to cwd
                relative_template_path = os.path.relpath(
                    template_file, config_path.parent
                )
                self.logger.debug(
                    f"Using absolute path calculation fallback: {relative_template_path}"
                )

            # Ensure we have the default environment structure
            default_env = config.setdefault("default", {})

            # Add template reference to build command
            build_params = default_env.setdefault("build", {}).setdefault(
                "parameters", {}
            )
            build_params["template"] = relative_template_path

            # Add template reference to deploy command
            deploy_params = default_env.setdefault("deploy", {}).setdefault(
                "parameters", {}
            )
            deploy_params["template"] = relative_template_path

            self.logger.debug(
                f"Added template reference '{relative_template_path}' to external config"
            )

        except Exception as e:
            self.logger.warning(
                f"Failed to calculate template path for external config: {e}. "
                "External config may need manual template path correction."
            )

        return config
