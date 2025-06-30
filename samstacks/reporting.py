"""
Manages the generation and display of deployment reports.
"""

from pathlib import Path
from typing import List, Optional, Tuple, Dict

from .pipeline_models import StackReportItem, PipelineSettingsModel
from . import ui as ui_module  # Import the ui module directly
from .aws_utils import mask_sensitive_data


def _resolve_masking_config(
    pipeline_settings: Optional[PipelineSettingsModel] = None,
) -> Tuple[bool, Dict[str, bool], List[Dict[str, str]]]:
    """
    Resolve masking configuration from pipeline settings.

    Returns:
        Tuple of (masking_enabled, categories_dict, custom_patterns_list)
    """
    if not pipeline_settings:
        return False, {}, []

    output_masking = pipeline_settings.output_masking
    if not output_masking:
        return False, {}, []

    # Check if masking is explicitly enabled OR any categories/patterns are configured
    has_categories_enabled = any(
        [
            output_masking.categories.account_ids,
            output_masking.categories.api_endpoints,
            output_masking.categories.database_endpoints,
            output_masking.categories.load_balancer_dns,
            output_masking.categories.cloudfront_domains,
            output_masking.categories.s3_bucket_domains,
            output_masking.categories.ip_addresses,
        ]
    )
    has_custom_patterns = len(output_masking.custom_patterns) > 0

    # Enable masking if explicitly enabled OR any categories/patterns are configured
    masking_enabled = (
        output_masking.enabled or has_categories_enabled or has_custom_patterns
    )

    if masking_enabled:
        # If masking is enabled but no specific categories are configured,
        # enable all categories by default for convenience
        if output_masking.enabled and not has_categories_enabled:
            categories = {
                "account_ids": True,
                "api_endpoints": True,
                "database_endpoints": True,
                "load_balancer_dns": True,
                "cloudfront_domains": True,
                "s3_bucket_domains": True,
                "ip_addresses": True,
            }
        else:
            # Use explicitly configured categories
            categories = {
                "account_ids": output_masking.categories.account_ids,
                "api_endpoints": output_masking.categories.api_endpoints,
                "database_endpoints": output_masking.categories.database_endpoints,
                "load_balancer_dns": output_masking.categories.load_balancer_dns,
                "cloudfront_domains": output_masking.categories.cloudfront_domains,
                "s3_bucket_domains": output_masking.categories.s3_bucket_domains,
                "ip_addresses": output_masking.categories.ip_addresses,
            }

        # Convert custom patterns to dict format
        custom_patterns = []
        for pattern in output_masking.custom_patterns:
            custom_patterns.append(
                {"pattern": pattern.pattern, "replacement": pattern.replacement}
            )

        return True, categories, custom_patterns

    return False, {}, []


def _apply_masking(
    value: str,
    masking_enabled: bool,
    categories: Dict[str, bool],
    custom_patterns: List[Dict[str, str]],
) -> str:
    """
    Apply masking to a value if masking is enabled.

    Args:
        value: The value to potentially mask
        masking_enabled: Whether masking is enabled
        categories: Dictionary of masking categories
        custom_patterns: List of custom masking patterns

    Returns:
        The original value or masked value based on configuration
    """
    if masking_enabled:
        return mask_sensitive_data(str(value), categories, custom_patterns)
    else:
        return str(value)


def display_console_report(
    report_items: List[StackReportItem],
    pipeline_settings: Optional[PipelineSettingsModel] = None,
) -> None:
    """Displays the deployment report to the console using the UI module."""
    if not report_items:
        return

    # Resolve masking configuration
    masking_enabled, categories, custom_patterns = _resolve_masking_config(
        pipeline_settings
    )

    ui_module.header("Deployment Report")
    for item in report_items:
        ui_module.subheader(
            f"Stack: {item['stack_id_from_pipeline']} (Deployed as: {item['deployed_stack_name']})"
        )
        ui_module.info("CloudFormation Status", item["cfn_status"] or "N/A")

        if item["parameters"]:
            ui_module.info("Parameters Applied:", "")
            for key, value in item["parameters"].items():
                display_value = _apply_masking(
                    value, masking_enabled, categories, custom_patterns
                )
                ui_module.detail(f"  {key}", display_value)
        else:
            ui_module.info("Parameters Applied", "None")

        if item["outputs"]:
            ui_module.info("Stack Outputs:", "")
            for key, value in item["outputs"].items():
                display_value = _apply_masking(
                    value, masking_enabled, categories, custom_patterns
                )
                ui_module.detail(f"  {key}", display_value)
        else:
            ui_module.info("Stack Outputs", "None")
        ui_module.separator()


def generate_markdown_report_string(
    report_items: List[StackReportItem],
    pipeline_name: str,
    pipeline_description: Optional[str] = None,
    processed_summary: Optional[str] = None,
    pipeline_settings: Optional[PipelineSettingsModel] = None,
) -> str:
    """Generates a Markdown formatted string for the deployment report."""
    # Resolve masking configuration
    masking_enabled, categories, custom_patterns = _resolve_masking_config(
        pipeline_settings
    )

    lines = [f"# Deployment Report - {pipeline_name}\n"]

    # Add pipeline description if provided
    if pipeline_description and pipeline_description.strip():
        lines.append("## Pipeline Description")
        lines.append(f"{pipeline_description.strip()}\n")

    # Add stack deployment results section header
    if not report_items:
        lines.append("## Stack Deployment Results\n")
        lines.append("No stacks processed or report items generated.\n")
    else:
        lines.append("## Stack Deployment Results\n")

        for item in report_items:
            lines.append(f"## {item['stack_id_from_pipeline']}")
            lines.append(f"- **stack name**: `{item['deployed_stack_name']}`")
            lines.append(
                f"- **CloudFormation Status**: `{item['cfn_status'] or 'N/A'}`"
            )

            lines.append("#### Parameters")
            if item["parameters"]:
                lines.append("")  # Ensure a blank line before the table
                lines.append("| Key        | Value                |")
                lines.append("|------------|----------------------|")
                for key, value in item["parameters"].items():
                    clean_key = str(key).strip()
                    display_value = _apply_masking(
                        value, masking_enabled, categories, custom_patterns
                    )
                    clean_value = display_value.strip().replace("|", "\\|")
                    lines.append(f"| {clean_key} | {clean_value} |")
            else:
                lines.append("  _None_")

            lines.append("#### Outputs")
            if item["outputs"]:
                lines.append("")  # Ensure a blank line before the table
                lines.append("| Key        | Value                |")
                lines.append("|------------|----------------------|")
                for key, value in item["outputs"].items():
                    clean_key = str(key).strip()
                    display_value = _apply_masking(
                        value, masking_enabled, categories, custom_patterns
                    )
                    clean_value = display_value.strip().replace("|", "\\|")
                    lines.append(f"| {clean_key} | {clean_value} |")
            else:
                lines.append("  _None_")
            lines.append("\n---\n")  # Horizontal rule for separation

    # Add summary at the end if provided
    if processed_summary and processed_summary.strip():
        lines.append("## Pipeline Summary")
        # Apply comprehensive masking to the summary as well if requested
        final_summary = _apply_masking(
            processed_summary.strip(), masking_enabled, categories, custom_patterns
        )
        lines.append(final_summary)
        lines.append("")  # Final empty line

    return "\n".join(lines)


def write_markdown_report_to_file(report_content: str, filepath: Path) -> None:
    """Writes the Markdown report content to the specified file."""

    if not isinstance(filepath, Path):
        try:
            filepath = Path(filepath)
            ui_module.debug(f"Converted filepath to Path object: {filepath}")
        except TypeError as te:
            ui_module.error(
                "Invalid filepath type for report",
                details=f"Cannot convert {type(filepath).__name__} to Path: {te}",
            )
            return

    resolved_path_str = "<unknown path after error>"
    try:
        resolved_path_str = str(filepath.resolve())
        filepath.write_text(report_content, encoding="utf-8")
        ui_module.info(
            "Deployment report generated", f"File saved to: {resolved_path_str}"
        )
    except Exception as e:
        ui_module.error(
            "Error writing deployment report to specified file path", details=str(e)
        )
