"""
Core logic for the `samstacks bootstrap` command.
"""

import os
import tomllib  # Use standard library tomllib for Python 3.11+
import yaml
from pathlib import Path
from typing import List, Dict, Any, Set, Optional, Tuple, cast
import logging

from . import ui  # Import UI module
from .exceptions import SamStacksError  # Or a new BootstrapError


# --- Add default constructor for unknown YAML tags ---
def default_yaml_constructor(
    loader: yaml.SafeLoader, tag_suffix: str, node: yaml.Node
) -> Any:
    """A default constructor for PyYAML to handle unknown tags like !Ref, !Sub.
    It attempts to construct the node as a standard Python type.
    """
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    elif isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    return None  # Or raise an error for unhandled node types if strictness is needed


# Register for any tag starting with '!'
# This allows parsing of CloudFormation intrinsic functions without defining each one.
yaml.add_multi_constructor("!", default_yaml_constructor, Loader=yaml.SafeLoader)
if hasattr(yaml, "CSafeLoader"):  # Also register for CSafeLoader if available
    yaml.add_multi_constructor("!", default_yaml_constructor, Loader=yaml.CSafeLoader)  # type: ignore
# --- End YAML tag handling ---

logger = logging.getLogger(__name__)


class DiscoveredStack:
    """Represents a discovered SAM stack with its details."""

    def __init__(
        self,
        abs_dir_path: Path,
        template_path: Path,
        samconfig_path: Optional[Path] = None,
    ):
        self.id: str = ""  # To be determined (e.g., from dir name)
        self.abs_dir_path: Path = abs_dir_path
        self.relative_dir_path: str = ""  # Relative to pipeline.yml location
        self.template_path: Path = template_path
        self.samconfig_path: Optional[Path] = samconfig_path

        self.template_data: Dict[str, Any] = {}
        self.samconfig_data: Optional[Dict[str, Any]] = None
        self.outputs: Set[str] = set()
        self.parameters: Dict[
            str, Dict[str, Any]
        ] = {}  # ParamName: {Type: ..., Default: ...}

    def __repr__(self) -> str:
        return f"DiscoveredStack(id='{self.id}', dir='{self.abs_dir_path.name}')"


class BootstrapManager:
    """Manages the bootstrapping process of generating a pipeline.yml from existing SAM projects."""

    def __init__(
        self,
        scan_path: str,
        output_file: str = "pipeline.yml",
        default_stack_id_source: str = "dir",
        pipeline_name: Optional[str] = None,
        stack_name_prefix: Optional[str] = None,
        overwrite: bool = False,
    ):
        self.scan_path: Path = Path(scan_path).resolve()
        self.output_file_path: Path = (
            self.scan_path / output_file
        )  # Default to scan_path root
        self.default_stack_id_source: str = default_stack_id_source
        self.pipeline_name: str = pipeline_name or self.scan_path.name + "-pipeline"
        self.stack_name_prefix: Optional[str] = stack_name_prefix
        self.overwrite: bool = overwrite

        self.discovered_stacks: List[DiscoveredStack] = []
        self.logger = logger  # Alias for convenience

    def bootstrap_pipeline(self) -> None:
        """Orchestrates the pipeline bootstrapping process."""
        # High-level start message for CLI can be handled by the CLI command itself.
        # self.logger.info(f"Starting bootstrap process for path: {self.scan_path}")

        if not self.scan_path.is_dir():
            raise SamStacksError(f"Scan path is not a directory: {self.scan_path}")

        if self.output_file_path.exists() and not self.overwrite:
            raise SamStacksError(
                f"Output file {self.output_file_path} already exists. Use --overwrite to replace it."
            )

        # 1. Discover stacks
        self._discover_stacks()
        if not self.discovered_stacks:
            self.logger.warning(
                "No SAM stacks found. Bootstrap process will not generate a pipeline file."
            )
            # Consider if ui.warning should be called from CLI layer based on a return status
            return
        ui.info(
            "Stack discovery",
            f"Discovered {len(self.discovered_stacks)} potential SAM stacks",
        )

        # 2. Analyze templates for outputs and parameters & load samconfig.toml
        self._analyze_stacks()

        # 3. Consolidate samconfig.toml settings
        default_sam_config, all_stack_specific_overrides = (
            self._consolidate_samconfigs()
        )

        # 4. Infer dependencies and determine order
        ordered_discovered_stacks, inferred_params_map = (
            self._infer_dependencies_and_order()
        )

        # 5. Generate pipeline.yml content
        pipeline_yaml_structure: Dict[str, Any] = {
            "pipeline_name": self.pipeline_name,
            "pipeline_settings": {},
            "stacks": [],
        }
        if self.stack_name_prefix:
            pipeline_yaml_structure["pipeline_settings"]["stack_name_prefix"] = (
                self.stack_name_prefix
            )
        if default_sam_config:
            pipeline_yaml_structure["pipeline_settings"]["default_sam_config"] = (
                default_sam_config
            )

        for stack_obj in ordered_discovered_stacks:
            stack_entry = {
                "id": stack_obj.id,
                "dir": stack_obj.relative_dir_path,
            }
            if (
                stack_obj.id in inferred_params_map
                and inferred_params_map[stack_obj.id]
            ):
                stack_entry["params"] = inferred_params_map[stack_obj.id]  # type: ignore

            if (
                stack_obj.id in all_stack_specific_overrides
                and all_stack_specific_overrides[stack_obj.id]
            ):
                stack_entry["sam_config_overrides"] = all_stack_specific_overrides[
                    stack_obj.id
                ]  # type: ignore

            pipeline_yaml_structure["stacks"].append(stack_entry)

        # 6. Write pipeline.yml
        # self.logger.info(f"Writing the following structure to {self.output_file_path}:\n{yaml.dump(pipeline_yaml_structure, indent=2, sort_keys=False, default_flow_style=False)}") # Too verbose for INFO
        self.logger.debug(
            f"Generated pipeline YAML structure:\n{yaml.dump(pipeline_yaml_structure, indent=2, sort_keys=False, default_flow_style=False)}"
        )  # Good for DEBUG
        self._write_pipeline_yaml(pipeline_yaml_structure)
        # Success message will be handled by the CLI layer
        # self.logger.info(f"Successfully generated pipeline manifest at: {self.output_file_path}")

    def _discover_stacks(self) -> None:
        """Scans the path for directories containing template.yaml or template.yml."""
        self.logger.debug(f"Scanning for SAM templates in {self.scan_path}...")
        self.discovered_stacks = []
        processed_dirs: Set[Path] = set()

        for pattern in ["template.yaml", "template.yml"]:
            for template_file_path in self.scan_path.rglob(f"**/{pattern}"):
                if any(part == ".aws-sam" for part in template_file_path.parts):
                    self.logger.debug(
                        f"Skipping template inside .aws-sam directory: {template_file_path}"
                    )
                    continue

                abs_stack_dir = template_file_path.parent.resolve()
                if abs_stack_dir in processed_dirs:
                    self.logger.debug(
                        f"Skipping already processed directory: {abs_stack_dir}"
                    )
                    continue

                self.logger.debug(
                    f"Found template: {template_file_path} in dir: {abs_stack_dir}"
                )

                # Discover samconfig file: .toml, then .yaml, then .yml
                samconfig_path_to_use: Optional[Path] = None
                samconfig_toml_path = abs_stack_dir / "samconfig.toml"
                samconfig_yaml_path = abs_stack_dir / "samconfig.yaml"
                samconfig_yml_path = abs_stack_dir / "samconfig.yml"

                if samconfig_toml_path.is_file():
                    samconfig_path_to_use = samconfig_toml_path
                    self.logger.debug(f"Found samconfig.toml: {samconfig_path_to_use}")
                elif samconfig_yaml_path.is_file():
                    samconfig_path_to_use = samconfig_yaml_path
                    self.logger.debug(f"Found samconfig.yaml: {samconfig_path_to_use}")
                elif samconfig_yml_path.is_file():
                    samconfig_path_to_use = samconfig_yml_path
                    self.logger.debug(f"Found samconfig.yml: {samconfig_path_to_use}")
                else:
                    self.logger.debug(
                        f"No samconfig file (.toml, .yaml, or .yml) found in {abs_stack_dir}"
                    )

                stack_obj = DiscoveredStack(
                    abs_dir_path=abs_stack_dir,
                    template_path=template_file_path,
                    samconfig_path=samconfig_path_to_use,  # Use the discovered one
                )

                # Determine stack ID based on strategy
                if self.default_stack_id_source == "dir":
                    stack_id_base = abs_stack_dir.name
                elif self.default_stack_id_source == "samconfig_stack_name":
                    # This part will be fleshed out when _analyze_stacks populates samconfig_data
                    # For now, fallback to dir name if samconfig parsing isn't done yet or lacks stack_name
                    # We will refine this logic later. For discovery, dir name is a safe start.
                    stack_id_base = abs_stack_dir.name
                else:
                    stack_id_base = (
                        abs_stack_dir.name
                    )  # Default to dir if strategy is unknown

                # Sanitize stack_id_base to be CloudFormation-compatible
                # CloudFormation stack names: letters, numbers, hyphens only (no underscores)
                # Replace invalid chars with hyphens, ensure starts with letter
                sanitized_id = "".join(c if c.isalnum() else "-" for c in stack_id_base)
                # Remove consecutive hyphens and leading/trailing hyphens
                sanitized_id = "-".join(
                    part for part in sanitized_id.split("-") if part
                )
                if not sanitized_id or not sanitized_id[0].isalpha():
                    sanitized_id = "stack-" + sanitized_id
                # Ensure uniqueness if multiple stacks might sanitize to the same ID
                # (simple counter for now, can be made more robust)
                temp_id = sanitized_id
                counter = 1
                while any(s.id == temp_id for s in self.discovered_stacks):
                    temp_id = f"{sanitized_id}-{counter}"
                    counter += 1
                stack_obj.id = temp_id

                # Determine relative_dir_path
                try:
                    # Path should be relative to the scan_path (project root where pipeline.yml is typically placed)
                    stack_obj.relative_dir_path = os.path.relpath(
                        abs_stack_dir, self.scan_path
                    )
                except ValueError as e:
                    # This can happen if scan_path and output_file_path are on different drives (Windows)
                    # or if output_file_path is not a child of scan_path in a way that allows relative path
                    # However, with scan_path as the base, this is less likely unless scan_path itself is odd.
                    self.logger.warning(
                        f"Could not determine relative path for {abs_stack_dir} from {self.scan_path}. "
                        f"Using directory name as fallback. Error: {e}"
                    )
                    stack_obj.relative_dir_path = (
                        abs_stack_dir.name
                    )  # Fallback to just the dir name

                self.discovered_stacks.append(stack_obj)
                processed_dirs.add(abs_stack_dir)
                self.logger.debug(
                    f"  + Discovered stack: '{stack_obj.id}' in '{stack_obj.relative_dir_path}'"
                )

        # Optionally, sort discovered_stacks by path or id for consistent ordering if needed before dependency sort
        self.discovered_stacks.sort(key=lambda s: s.id)

    def _analyze_stacks(self) -> None:
        """Parses template.yaml for outputs/params and loads samconfig.toml for each stack."""
        self.logger.debug(
            "Analyzing discovered stack templates and samconfig files..."
        )  # Changed to DEBUG
        for stack_obj in self.discovered_stacks:
            self.logger.debug(
                f"Analyzing stack: {stack_obj.id} at {stack_obj.abs_dir_path}"
            )
            # Parse template.yaml
            try:
                with open(stack_obj.template_path, "r", encoding="utf-8") as f_template:
                    template_content = cast(Dict[str, Any], yaml.safe_load(f_template))
                    if not isinstance(template_content, dict):
                        self.logger.warning(
                            f"Template file {stack_obj.template_path} for stack {stack_obj.id} is not a valid YAML mapping. Skipping parameter/output analysis."
                        )
                        template_content = {}  # Ensure it's a dict to avoid errors below
                    stack_obj.template_data = template_content

                # Extract Parameters
                parameters_section = stack_obj.template_data.get("Parameters")
                if isinstance(parameters_section, dict):
                    for param_name, param_def in parameters_section.items():
                        if isinstance(param_def, dict):
                            stack_obj.parameters[param_name] = {
                                "Type": param_def.get(
                                    "Type", "String"
                                ),  # Default to String if Type is missing
                                "Default": param_def.get("Default"),
                                # Could extract Description, AllowedValues etc. if needed later
                            }
                        else:
                            self.logger.warning(
                                f"Parameter '{param_name}' in {stack_obj.template_path} has an invalid definition."
                            )
                elif parameters_section is not None:
                    self.logger.warning(
                        f"'Parameters' section in {stack_obj.template_path} is not a valid mapping."
                    )

                # Extract Outputs
                outputs_section = stack_obj.template_data.get("Outputs")
                if isinstance(outputs_section, dict):
                    stack_obj.outputs = set(outputs_section.keys())
                elif outputs_section is not None:
                    self.logger.warning(
                        f"'Outputs' section in {stack_obj.template_path} is not a valid mapping."
                    )

                self.logger.debug(
                    f"  Stack {stack_obj.id}: Found {len(stack_obj.parameters)} params, {len(stack_obj.outputs)} outputs."
                )

            except FileNotFoundError:
                self.logger.error(
                    f"Template file not found for stack {stack_obj.id}: {stack_obj.template_path}"
                )
                # Decide if this should be a critical error or if the stack should be skipped/marked invalid
                continue  # Skip this stack for now
            except yaml.YAMLError as e:
                self.logger.error(
                    f"Error parsing YAML template for stack {stack_obj.id} at {stack_obj.template_path}: {e}"
                )
                continue  # Skip this stack
            except (
                Exception
            ) as e:  # Catch any other unexpected errors during template processing
                self.logger.error(
                    f"Unexpected error processing template for stack {stack_obj.id}: {e}"
                )
                continue

            # Parse samconfig file if it exists
            if stack_obj.samconfig_path and stack_obj.samconfig_path.is_file():
                file_to_parse = stack_obj.samconfig_path
                try:
                    self.logger.debug(
                        f"Attempting to parse samconfig file: {file_to_parse}"
                    )
                    with open(
                        file_to_parse, "rb"
                    ) as f_samconfig:  # Open in binary for tomllib
                        if file_to_parse.suffix == ".toml":
                            stack_obj.samconfig_data = tomllib.load(f_samconfig)
                            self.logger.debug(
                                f"  Successfully parsed as TOML: {file_to_parse}"
                            )
                        elif file_to_parse.suffix in [".yaml", ".yml"]:
                            # PyYAML needs text mode, so re-open or read then decode
                            # For simplicity, read bytes then decode for yaml.safe_load
                            file_content_bytes = f_samconfig.read()
                            stack_obj.samconfig_data = cast(
                                Dict[str, Any],
                                yaml.safe_load(file_content_bytes.decode("utf-8")),
                            )
                            self.logger.debug(
                                f"  Successfully parsed as YAML: {file_to_parse}"
                            )
                        else:
                            self.logger.warning(
                                f"Unrecognized samconfig file extension: {file_to_parse.suffix}. Skipping parse."
                            )
                            stack_obj.samconfig_data = None
                except FileNotFoundError:
                    self.logger.warning(
                        f"Samconfig file listed but not found during analysis: {file_to_parse}"
                    )
                    stack_obj.samconfig_path = None
                    stack_obj.samconfig_data = None
                except (tomllib.TOMLDecodeError, yaml.YAMLError) as e:
                    self.logger.error(
                        f"Error parsing samconfig file {file_to_parse}: {e}"
                    )
                    stack_obj.samconfig_data = None
                except Exception as e:
                    self.logger.error(
                        f"Unexpected error processing samconfig file {file_to_parse}: {e}"
                    )
                    stack_obj.samconfig_data = None
            else:
                if stack_obj.samconfig_path:
                    self.logger.debug(
                        f"Samconfig file at {stack_obj.samconfig_path} is not a valid file or was removed. Clearing path."
                    )
                    stack_obj.samconfig_path = None
                stack_obj.samconfig_data = None

        # Refine stack IDs if using samconfig_stack_name strategy (if samconfig_data was parsed)
        if self.default_stack_id_source == "samconfig_stack_name":
            self.logger.debug(
                "Refining stack IDs based on 'samconfig_stack_name' strategy..."
            )  # This can be DEBUG
            # This requires a more complex re-ID and uniqueness check, as IDs might change
            # For simplicity in this step, we are not re-running the full uniqueness logic from _discover_stacks
            # A more robust implementation might re-evaluate all IDs here.
            potential_new_ids: Dict[str, str] = {}
            current_ids = {s.id for s in self.discovered_stacks}

            for stack_obj in self.discovered_stacks:
                new_id_base = (
                    stack_obj.abs_dir_path.name
                )  # Default if samconfig doesn't provide
                if stack_obj.samconfig_data:
                    try:
                        # Path to stack_name: e.g., samconfig_data['default']['deploy']['parameters']['stack_name']
                        # This path can vary, so a robust lookup is needed. For MVP, assume a common path or skip if not found.
                        # For now, let's assume a simple direct lookup for a hypothetical top-level 'stack_name' for demo purposes.
                        # A real implementation needs to gracefully handle complex structures and missing keys.
                        cfg_stack_name = (
                            stack_obj.samconfig_data.get("default", {})
                            .get("deploy", {})
                            .get("parameters", {})
                            .get("stack_name")
                        )
                        if isinstance(cfg_stack_name, str) and cfg_stack_name.strip():
                            new_id_base = cfg_stack_name.strip()
                            self.logger.debug(
                                f"  Stack {stack_obj.id} (dir: {stack_obj.abs_dir_path.name}): Found stack_name '{new_id_base}' in samconfig."
                            )
                        else:
                            self.logger.debug(
                                f"  Stack {stack_obj.id}: No valid 'stack_name' found in samconfig.toml, using dir name '{new_id_base}'."
                            )
                    except Exception as e:
                        self.logger.warning(
                            f"Error accessing stack_name in samconfig for {stack_obj.id}: {e}. Using dir name."
                        )

                sanitized_new_id = "".join(
                    c if c.isalnum() else "-" for c in new_id_base
                )
                # Remove consecutive hyphens and leading/trailing hyphens
                sanitized_new_id = "-".join(
                    part for part in sanitized_new_id.split("-") if part
                )
                if not sanitized_new_id or not sanitized_new_id[0].isalpha():
                    sanitized_new_id = "stack-" + sanitized_new_id

                if (
                    sanitized_new_id != stack_obj.id
                ):  # Only update if different and needs uniqueness check
                    temp_new_id = sanitized_new_id
                    counter = 1
                    # Check against existing and other potential new IDs to ensure uniqueness
                    while (
                        temp_new_id in current_ids
                        or temp_new_id in potential_new_ids.values()
                    ):
                        temp_new_id = f"{sanitized_new_id}-{counter}"
                        counter += 1
                    potential_new_ids[stack_obj.id] = (
                        temp_new_id  # Store mapping from old_id to new_id
                    )

            for stack_obj in self.discovered_stacks:
                if stack_obj.id in potential_new_ids:
                    old_id = stack_obj.id
                    stack_obj.id = potential_new_ids[old_id]
                    self.logger.debug(
                        f"  Re-identified stack '{old_id}' as '{stack_obj.id}' based on samconfig."
                    )

            # Re-sort if IDs changed
            self.discovered_stacks.sort(key=lambda s: s.id)
            self.logger.debug("Finished refining stack IDs.")  # This can be DEBUG

    def _consolidate_samconfigs(
        self,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        """Consolidates samconfig.toml settings into default and stack-specific overrides."""
        self.logger.debug(
            "Consolidating samconfig.toml settings..."
        )  # Changed to DEBUG

        configs_to_process: List[
            Tuple[str, Dict[str, Any]]
        ] = []  # (stack_id, config_data)
        for stack_obj in self.discovered_stacks:
            if stack_obj.samconfig_data:
                configs_to_process.append((stack_obj.id, stack_obj.samconfig_data))
            else:
                pass  # Stack has no samconfig_data

        if not configs_to_process:
            self.logger.debug(
                "No samconfig.toml files found or parsed. No default_sam_config or overrides will be generated from them."
            )
            return None, {}

        # Fields to always skip for default_sam_config and sam_config_overrides consideration
        # as they are either handled by samstacks params, or too complex for auto-migration MVP.
        globally_skipped_fields = {
            "tags",
            "parameter_overrides",
            "stack_name",
            "s3_prefix",
        }

        def _sanitize_config(config: Dict[str, Any]) -> Dict[str, Any]:
            """Deep copies and removes globally skipped fields from a config structure."""
            if not isinstance(config, dict):
                return config  # Should not happen at top level

            copied_config = cast(
                Dict[str, Any], yaml.safe_load(yaml.safe_dump(config))
            )  # Deep copy

            # Remove globally skipped fields from all levels of parameters
            # e.g. default.deploy.parameters, prod.sync.parameters etc.
            for env_key, env_val in copied_config.items():
                if isinstance(env_val, dict):
                    for cmd_key, cmd_val in env_val.items():
                        if (
                            isinstance(cmd_val, dict)
                            and "parameters" in cmd_val
                            and isinstance(cmd_val["parameters"], dict)
                        ):
                            params_dict = cmd_val["parameters"]
                            for skip_key in globally_skipped_fields:
                                if skip_key in params_dict:
                                    del params_dict[skip_key]
            return copied_config

        sanitized_configs = [
            (sid, _sanitize_config(data)) for sid, data in configs_to_process
        ]

        if not sanitized_configs:
            return None, {}

        # Find common settings
        # Start with the first sanitized config as a candidate for common settings
        common_settings_candidate = cast(
            Dict[str, Any], yaml.safe_load(yaml.safe_dump(sanitized_configs[0][1]))
        )

        for _, other_config_data in sanitized_configs[1:]:
            common_settings_candidate = self._intersect_configs(
                common_settings_candidate, other_config_data
            )
            if not common_settings_candidate:  # No common ground left
                break

        default_sam_config: Optional[Dict[str, Any]] = (
            common_settings_candidate if common_settings_candidate else None
        )

        if default_sam_config:
            self.logger.debug(
                f"Derived common default_sam_config: {list(default_sam_config.keys()) if default_sam_config else 'None'}"
            )
        else:
            self.logger.debug(
                "No strictly common settings found across all samconfig.toml files to form default_sam_config."
            )

        # Determine stack-specific overrides
        all_stack_specific_overrides: Dict[str, Dict[str, Any]] = {}
        for stack_id, original_sanitized_config in sanitized_configs:
            current_overrides: Dict[str, Any] = {}  # Initialize to empty dict
            if default_sam_config:
                # Calculate what's in original_sanitized_config but not in (or different from) default_sam_config
                current_overrides = self._diff_configs(
                    original_sanitized_config, default_sam_config
                )
            else:
                # If no default_sam_config, then everything from the sanitized config is an override
                current_overrides = cast(
                    Dict[str, Any],
                    yaml.safe_load(yaml.safe_dump(original_sanitized_config)),
                )

            # Always store the result for the stack_id, even if current_overrides is empty.
            all_stack_specific_overrides[stack_id] = current_overrides

            if current_overrides:  # Log if there are actual overrides
                self.logger.debug(
                    f"  Stack {stack_id}: Found specific overrides: {list(current_overrides.keys())}"
                )
            else:
                self.logger.debug(
                    f"  Stack {stack_id}: No specific overrides found (or matches default_sam_config completely)."
                )

        return default_sam_config, all_stack_specific_overrides

    def _intersect_configs(
        self, config1: Dict[str, Any], config2: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Helper to find the intersection of two config dictionaries (recursive)."""
        intersection: Dict[str, Any] = {}
        for key, value1 in config1.items():
            if key in config2:
                value2 = config2[key]
                if isinstance(value1, dict) and isinstance(value2, dict):
                    nested_intersection = self._intersect_configs(value1, value2)
                    if (
                        nested_intersection
                    ):  # Only add if there's something common in nested dict
                        intersection[key] = nested_intersection
                elif value1 == value2:  # For non-dict types (str, list, int, bool)
                    intersection[key] = value1
        return intersection

    def _diff_configs(
        self, config_primary: Dict[str, Any], config_to_subtract: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Helper to find what's in config_primary that is not in or different from config_to_subtract (recursive)."""
        diff: Dict[str, Any] = {}
        for key, value_primary in config_primary.items():
            if key not in config_to_subtract:
                diff[key] = cast(
                    Any, yaml.safe_load(yaml.safe_dump(value_primary))
                )  # Deep copy new items
            else:
                value_to_subtract = config_to_subtract[key]
                if isinstance(value_primary, dict) and isinstance(
                    value_to_subtract, dict
                ):
                    nested_diff = self._diff_configs(value_primary, value_to_subtract)
                    if nested_diff:
                        diff[key] = nested_diff
                elif value_primary != value_to_subtract:
                    diff[key] = cast(
                        Any, yaml.safe_load(yaml.safe_dump(value_primary))
                    )  # Deep copy different items
        return diff

    def _infer_dependencies_and_order(
        self,
    ) -> Tuple[List[DiscoveredStack], Dict[str, Dict[str, str]]]:
        """Infers dependencies, orders stacks, and identifies parameter expressions."""
        self.logger.debug(
            "Inferring dependencies and determining stack order..."
        )  # Changed to DEBUG

        num_stacks = len(self.discovered_stacks)
        if num_stacks == 0:
            self.logger.debug("_infer_dependencies_and_order: No stacks to order.")
            return [], {}

        stacks_map: Dict[str, DiscoveredStack] = {
            s.id: s for s in self.discovered_stacks
        }
        stack_ids: List[str] = list(stacks_map.keys())

        adj: Dict[str, Set[str]] = {sid: set() for sid in stack_ids}
        in_degree: Dict[str, int] = {sid: 0 for sid in stack_ids}
        param_source_map: Dict[Tuple[str, str], str] = {}
        ambiguous_sources: Dict[Tuple[str, str], List[str]] = {}

        # Build the graph and in-degrees
        for i in range(num_stacks):
            consumer_stack = self.discovered_stacks[i]
            for consumer_param_name in consumer_stack.parameters.keys():
                potential_producers = []
                # Check all *other* stacks as potential producers
                for j in range(num_stacks):
                    # A stack cannot produce its own parameter via its output in this direct check
                    # and we must ensure producer_stack is actually different from consumer_stack
                    if self.discovered_stacks[j].id == consumer_stack.id:
                        continue

                    producer_stack = self.discovered_stacks[j]
                    if consumer_param_name in producer_stack.outputs:
                        potential_producers.append(producer_stack.id)

                if len(potential_producers) == 1:
                    producer_id = potential_producers[0]
                    # Edge: producer_stack -> consumer_stack (producer must come before consumer)
                    if (
                        consumer_stack.id not in adj[producer_id]
                    ):  # Add edge if not already present
                        adj[producer_id].add(consumer_stack.id)
                        in_degree[consumer_stack.id] += 1
                    param_source_map[(consumer_stack.id, consumer_param_name)] = (
                        producer_id
                    )
                    self.logger.debug(
                        f"  Dependency: {consumer_stack.id}.{consumer_param_name} <- {producer_id}.outputs.{consumer_param_name}"
                    )
                elif len(potential_producers) > 1:
                    self.logger.error(
                        f"Ambiguous dependency for parameter '{consumer_param_name}' in stack '{consumer_stack.id}'. "
                        f"It could be provided by outputs from stacks: {potential_producers}."
                    )
                    ambiguous_sources[(consumer_stack.id, consumer_param_name)] = (
                        potential_producers
                    )

        if ambiguous_sources:
            error_messages = []
            for (consumer_id, param), producers in ambiguous_sources.items():
                error_messages.append(
                    f"Parameter '{param}' in stack '{consumer_id}' has ambiguous sources: {producers}"
                )
            raise SamStacksError(
                "Failed to determine stack order due to ambiguous dependencies. Please resolve manually:\n"
                + "\n".join(error_messages)
            )

        # Topological Sort (Kahn's Algorithm)
        queue: List[str] = [sid for sid in stack_ids if in_degree[sid] == 0]
        topo_sorted_ids: List[
            str
        ] = []  # This will store the topologically sorted stack IDs

        self.logger.debug(f"Initial queue for topo sort: {queue}")
        self.logger.debug(f"Initial in-degrees: {in_degree}")
        self.logger.debug(f"Adjacency list: {adj}")

        while queue:
            u_id = queue.pop(0)  # Dequeue
            topo_sorted_ids.append(u_id)

            # For each neighbor v of u (i.e., for each stack v_id that u_id produces an output for)
            # Sort neighbors to process them in a consistent order (helps in deterministic output)
            sorted_neighbors = sorted(list(adj[u_id]))
            for v_id in sorted_neighbors:
                in_degree[v_id] -= 1
                if in_degree[v_id] == 0:
                    queue.append(v_id)  # Enqueue

        if len(topo_sorted_ids) != num_stacks:
            missing_stacks = set(stack_ids) - set(topo_sorted_ids)
            cycle_details = f"Could not determine a linear order. Stacks involved in or affected by cycles: {missing_stacks}"
            self.logger.error(f"Cycle detected in stack dependencies: {cycle_details}")
            raise SamStacksError(
                f"Failed to determine stack order due to circular dependencies. Please resolve manually. {cycle_details}"
            )

        self.logger.debug(
            f"Determined stack order: {topo_sorted_ids}"
        )  # This can be DEBUG

        # Create the final list of DiscoveredStack objects in the determined order
        final_ordered_stacks = [stacks_map[sid] for sid in topo_sorted_ids]

        # Construct inferred parameters map
        inferred_params_expressions: Dict[str, Dict[str, str]] = {
            sid: {} for sid in stack_ids
        }
        for (consumer_id, param_name), producer_id in param_source_map.items():
            expression = f"${{{{ stacks.{producer_id}.outputs.{param_name} }}}}"
            inferred_params_expressions[consumer_id][param_name] = expression
            self.logger.debug(
                f"  Generated param expression for {consumer_id}.{param_name}: {expression}"
            )

        self.logger.debug(
            f"_infer_dependencies_and_order returning ordered_stacks: {[s.id for s in final_ordered_stacks]}"
        )
        self.logger.debug(
            f"_infer_dependencies_and_order returning full ordered_stacks: {final_ordered_stacks}"
        )
        self.logger.debug(
            f"_infer_dependencies_and_order returning inferred_params: {inferred_params_expressions}"
        )
        return final_ordered_stacks, inferred_params_expressions

    def _write_pipeline_yaml(self, pipeline_content: Dict[str, Any]) -> None:
        """Writes the generated pipeline content to the output file."""
        try:
            with open(self.output_file_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    pipeline_content,
                    f,
                    sort_keys=False,
                    default_flow_style=False,
                    indent=2,
                )
            self.logger.debug(f"Pipeline manifest written to {self.output_file_path}")
        except IOError as e:
            raise SamStacksError(
                f"Failed to write pipeline manifest to {self.output_file_path}: {e}"
            )


# The __main__ block below was for initial development and testing.
# It is superseded by the unit and integration tests.
# It can be removed.
