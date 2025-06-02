"""
Manages the generation and display of deployment reports.
"""

from pathlib import Path
from typing import List

from .pipeline_models import StackReportItem
from . import ui as ui_module  # Import the ui module directly


def display_console_report(report_items: List[StackReportItem]) -> None:
    """Displays the deployment report to the console using the UI module."""
    if not report_items:
        return

    ui_module.header("Deployment Report")
    for item in report_items:
        ui_module.subheader(
            f"Stack: {item['stack_id_from_pipeline']} (Deployed as: {item['deployed_stack_name']})"
        )
        ui_module.info("CloudFormation Status", item["cfn_status"] or "N/A")

        if item["parameters"]:
            ui_module.info("Parameters Applied:", "")
            for key, value in item["parameters"].items():
                ui_module.detail(f"  {key}", value)
        else:
            ui_module.info("Parameters Applied", "None")

        if item["outputs"]:
            ui_module.info("Stack Outputs:", "")
            for key, value in item["outputs"].items():
                ui_module.detail(f"  {key}", value)
        else:
            ui_module.info("Stack Outputs", "None")
        ui_module.separator()


def generate_markdown_report_string(
    report_items: List[StackReportItem], pipeline_name: str
) -> str:
    """Generates a Markdown formatted string for the deployment report."""
    if not report_items:
        return "# Deployment Report\n\nNo stacks processed or report items generated.\n"

    lines = [f"# Deployment Report - {pipeline_name}\n"]

    for item in report_items:
        lines.append(f"## {item['stack_id_from_pipeline']}")
        lines.append(f"- **stack name**: `{item['deployed_stack_name']}`")
        lines.append(f"- **CloudFormation Status**: `{item['cfn_status'] or 'N/A'}`")

        lines.append("#### Parameters")
        if item["parameters"]:
            lines.append("")  # Ensure a blank line before the table
            lines.append("| Key        | Value                |")
            lines.append("|------------|----------------------|")
            for key, value in item["parameters"].items():
                clean_key = str(key).strip()
                clean_value = str(value).strip().replace("|", "\\|")
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
                clean_value = str(value).strip().replace("|", "\\|")
                lines.append(f"| {clean_key} | {clean_value} |")
        else:
            lines.append("  _None_")
        lines.append("\n---\n")  # Horizontal rule for separation

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
