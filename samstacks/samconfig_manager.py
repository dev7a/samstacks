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

    def _deep_copy_dict(self, d: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if d is None:
            return {}
        # Using yaml load/dump for a deep copy that handles nested structures well.
        # More robust than manual recursion for complex Any types.
        return yaml.safe_load(yaml.safe_dump(d)) if d else {}

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
            # elif isinstance(value_updates, list): # If updates has a list, it replaces base
            #    merged[key] = self._deep_copy_dict(value_updates) # Ensure list elements are also deep copied if mutable
            else:  # Includes primitives, lists (direct replacement), or if key not in base
                merged[key] = (
                    self._deep_copy_dict(value_updates)
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
        Operates on a deep copy.
        """
        output_config = self._deep_copy_dict(config_dict)
        
        # Ensure the version key is present (required by SAM CLI)
        if "version" not in output_config:
            output_config["version"] = 0.1
        
        env_name = "default"  # Target environment for core settings
        cmd_name = "deploy"

        # Ensure path to parameters section exists
        env_config = output_config.setdefault(env_name, {})
        cmd_config = env_config.setdefault(cmd_name, {})
        params_section = cmd_config.setdefault("parameters", {})

        # Core overrides controlled by samstacks
        params_section["stack_name"] = deployed_stack_name
        params_section["s3_prefix"] = deployed_stack_name
        params_section.setdefault(
            "resolve_s3", True
        )  # Set if not present, otherwise keep user's value
        params_section.setdefault(
            "confirm_changeset", False
        )  # Set if not present, otherwise keep user's value

        if effective_region and "region" not in params_section:
            params_section["region"] = effective_region

        # Merge pipeline_driven_params into parameter_overrides
        existing_param_overrides = params_section.get("parameter_overrides", {})
        if not isinstance(existing_param_overrides, dict):
            logger.warning(
                f"'parameter_overrides' in samconfig for stack '{deployed_stack_name}' is not a dictionary. "
                f"It will be overwritten by pipeline-defined parameters."
            )
            existing_param_overrides = {}

        merged_param_overrides = {
            **existing_param_overrides,
            **pipeline_driven_params_map,
        }
        if merged_param_overrides:  # Only add/update if there are overrides
            # Format parameter_overrides as a single string with space-separated key=value pairs
            # as expected by SAM CLI (per AWS documentation)
            param_override_pairs = []
            for key, value in merged_param_overrides.items():
                # Ensure values are properly quoted if they contain spaces
                if ' ' in str(value):
                    param_override_pairs.append(f"{key}=\"{value}\"")
                else:
                    param_override_pairs.append(f"{key}={value}")
            params_section["parameter_overrides"] = " ".join(param_override_pairs)
        elif "parameter_overrides" in params_section and not existing_param_overrides:
            # If pipeline had no params and local had no params, ensure no empty key exists
            pass  # Keep it as is (likely empty or not present)

        return output_config

    def generate_samconfig_for_stack(
        self,
        stack_dir: Path,  # Resolved absolute path to stack directory
        stack_id: str,  # For logging
        pydantic_stack_model: PydanticStackModel,  # Parsed stack data from pipeline.yml
        deployed_stack_name: str,  # Final computed CloudFormation stack name
        effective_region: Optional[str],  # Resolved region for the stack
        resolved_stack_params: Dict[
            str, str
        ],  # Fully resolved params for parameter_overrides
    ) -> Path:
        """
        Generates and writes the samconfig.yaml for a given stack.
        Returns the path to the generated samconfig.yaml file.
        """
        target_samconfig_path = stack_dir / "samconfig.yaml"
        existing_toml_path = stack_dir / "samconfig.toml"
        backup_toml_path = stack_dir / "samconfig.toml.bak"
        backup_yaml_path = stack_dir / "samconfig.yaml.bak"

        if existing_toml_path.exists():
            logger.info(
                f"Existing samconfig.toml found in '{stack_dir}'. Backing up to '{backup_toml_path.name}'."
            )
            if backup_toml_path.exists():
                os.remove(backup_toml_path)
            shutil.move(str(existing_toml_path), str(backup_toml_path))
            # Content of backed-up TOML is not used for merging as per simplified plan.

        if target_samconfig_path.exists():
            logger.info(
                f"Existing samconfig.yaml found in '{stack_dir}'. Backing up to '{backup_yaml_path.name}'."
            )
            if backup_yaml_path.exists():
                os.remove(backup_yaml_path)
            shutil.move(str(target_samconfig_path), str(backup_yaml_path))

        # Derive Config_Pipeline_Base from defaults and stack-specific overrides
        config_pipeline_base = self._deep_copy_dict(
            self.default_sam_config_from_pipeline
        )
        if pydantic_stack_model.sam_config_overrides:
            config_pipeline_base = self._deep_merge_dicts(
                config_pipeline_base,
                pydantic_stack_model.sam_config_overrides,  # This is already a dict
            )

        # Materialize Config_Pipeline_Base (resolve env, inputs, pipeline templates)
        # This uses the main template_processor. Stack outputs are NOT available here.
        config_pipeline_base_materialized = self.template_processor.process_structure(
            config_pipeline_base,
            pipeline_name=self.pipeline_name,  # Pass context for ${{ pipeline.* }}
            pipeline_description=self.pipeline_description,
        )

        # Apply stack-specific computed values and merge resolved_stack_params
        final_config = self._apply_stack_specific_configs(
            config_pipeline_base_materialized,
            deployed_stack_name,
            effective_region,
            resolved_stack_params,
        )

        # Write Final_Config to samconfig.yaml
        try:
            with open(target_samconfig_path, "w", encoding="utf-8") as f_yaml:
                yaml.dump(
                    final_config,
                    f_yaml,
                    sort_keys=False,
                    default_flow_style=False,
                    indent=2,
                )
            logger.info(
                f"Generated samconfig.yaml for stack '{stack_id}' at '{target_samconfig_path}'."
            )
        except Exception as e:
            logger.error(f"Failed to write samconfig.yaml for stack '{stack_id}': {e}")
            raise ManifestError(
                f"Failed to write samconfig.yaml for stack '{stack_id}': {e}"
            ) from e

        return target_samconfig_path
