"""
Integration tests for comprehensive output masking functionality.
"""

from samstacks.reporting import (
    display_console_report,
    generate_markdown_report_string,
    _resolve_masking_config,
)
from samstacks.pipeline_models import (
    StackReportItem,
    PipelineSettingsModel,
    OutputMaskingModel,
    OutputMaskingCategoriesModel,
    CustomMaskingPatternModel,
)
from io import StringIO
from unittest.mock import patch
from typing import List


class TestComprehensiveMaskingIntegration:
    """Integration tests for the comprehensive masking system."""

    def test_console_report_with_account_id_masking(self):
        """Test that console report masks account IDs when enabled."""
        report_items: List[StackReportItem] = [
            {
                "stack_id_from_pipeline": "test-stack",
                "deployed_stack_name": "test-stack-deployed",
                "cfn_status": "CREATE_COMPLETE",
                "parameters": {"Environment": "test"},
                "outputs": {
                    "FunctionArn": "arn:aws:lambda:us-west-2:123456789012:function:test"
                },
            }
        ]

        # Enable only account ID masking
        categories = OutputMaskingCategoriesModel(account_ids=True)
        output_masking = OutputMaskingModel(enabled=True, categories=categories)
        settings = PipelineSettingsModel(output_masking=output_masking)

        # Capture console output
        captured_output = StringIO()
        with patch("sys.stdout", captured_output):
            display_console_report(report_items, settings)

        output = captured_output.getvalue()
        assert "************" in output  # Account ID should be masked

    def test_console_report_with_masking_disabled(self):
        """Test that console report doesn't mask when disabled."""
        report_items: List[StackReportItem] = [
            {
                "stack_id_from_pipeline": "test-stack",
                "deployed_stack_name": "test-stack-deployed",
                "cfn_status": "CREATE_COMPLETE",
                "parameters": {"Environment": "test"},
                "outputs": {
                    "FunctionArn": "arn:aws:lambda:us-west-2:123456789012:function:test"
                },
            }
        ]

        # Masking disabled
        output_masking = OutputMaskingModel(enabled=False)
        settings = PipelineSettingsModel(output_masking=output_masking)

        # Capture console output
        captured_output = StringIO()
        with patch("sys.stdout", captured_output):
            display_console_report(report_items, settings)

        output = captured_output.getvalue()
        assert "123456789012" in output  # Account ID should NOT be masked

    def test_markdown_report_with_account_id_masking(self):
        """Test that markdown report masks account IDs when enabled."""
        report_items: List[StackReportItem] = [
            {
                "stack_id_from_pipeline": "test-stack",
                "deployed_stack_name": "test-stack-deployed",
                "cfn_status": "CREATE_COMPLETE",
                "parameters": {"Environment": "test"},
                "outputs": {
                    "FunctionArn": "arn:aws:lambda:us-west-2:123456789012:function:test"
                },
            }
        ]

        # Enable only account ID masking
        categories = OutputMaskingCategoriesModel(account_ids=True)
        output_masking = OutputMaskingModel(enabled=True, categories=categories)
        settings = PipelineSettingsModel(output_masking=output_masking)

        report = generate_markdown_report_string(
            report_items, "Test Pipeline", pipeline_settings=settings
        )

        assert "************" in report  # Account ID should be masked
        assert "123456789012" not in report  # Original account ID should not appear

    def test_markdown_report_with_masking_disabled(self):
        """Test that markdown report doesn't mask when disabled."""
        report_items: List[StackReportItem] = [
            {
                "stack_id_from_pipeline": "test-stack",
                "deployed_stack_name": "test-stack-deployed",
                "cfn_status": "CREATE_COMPLETE",
                "parameters": {"Environment": "test"},
                "outputs": {
                    "FunctionArn": "arn:aws:lambda:us-west-2:123456789012:function:test"
                },
            }
        ]

        # Masking disabled
        output_masking = OutputMaskingModel(enabled=False)
        settings = PipelineSettingsModel(output_masking=output_masking)

        report = generate_markdown_report_string(
            report_items, "Test Pipeline", pipeline_settings=settings
        )

        assert "123456789012" in report  # Account ID should NOT be masked

    def test_comprehensive_masking_console_report(self):
        """Test console report with multiple masking categories enabled."""
        report_items: List[StackReportItem] = [
            {
                "stack_id_from_pipeline": "test-stack",
                "deployed_stack_name": "test-stack-deployed",
                "cfn_status": "CREATE_COMPLETE",
                "parameters": {"Environment": "test"},
                "outputs": {
                    "FunctionArn": "arn:aws:lambda:us-west-2:123456789012:function:test",
                    "ApiUrl": "https://abc123def.execute-api.us-west-2.amazonaws.com/prod",
                    "DatabaseEndpoint": "myapp.xyz789.us-west-2.rds.amazonaws.com",
                },
            }
        ]

        # Enable multiple categories
        categories = OutputMaskingCategoriesModel(
            account_ids=True, api_endpoints=True, database_endpoints=True
        )
        output_masking = OutputMaskingModel(enabled=True, categories=categories)
        settings = PipelineSettingsModel(output_masking=output_masking)

        # Capture console output
        captured_output = StringIO()
        with patch("sys.stdout", captured_output):
            display_console_report(report_items, settings)

        output = captured_output.getvalue()
        assert "************" in output  # Account ID masked
        assert "******" in output  # API endpoint masked

    def test_comprehensive_masking_markdown_report(self):
        """Test markdown report with multiple masking categories enabled."""
        report_items: List[StackReportItem] = [
            {
                "stack_id_from_pipeline": "test-stack",
                "deployed_stack_name": "test-stack-deployed",
                "cfn_status": "CREATE_COMPLETE",
                "parameters": {"Environment": "test"},
                "outputs": {
                    "FunctionArn": "arn:aws:lambda:us-west-2:123456789012:function:test",
                    "ApiUrl": "https://abc123def.execute-api.us-west-2.amazonaws.com/prod",
                    "DatabaseEndpoint": "myapp.xyz789.us-west-2.rds.amazonaws.com",
                },
            }
        ]

        # Enable multiple categories
        categories = OutputMaskingCategoriesModel(
            account_ids=True, api_endpoints=True, database_endpoints=True
        )
        output_masking = OutputMaskingModel(enabled=True, categories=categories)
        settings = PipelineSettingsModel(output_masking=output_masking)

        report = generate_markdown_report_string(
            report_items, "Test Pipeline", pipeline_settings=settings
        )

        assert "************" in report  # Account ID masked
        assert "******" in report  # API endpoint and database endpoint masked

    def test_custom_patterns_integration(self):
        """Test that custom patterns work in reports."""
        report_items: List[StackReportItem] = [
            {
                "stack_id_from_pipeline": "test-stack",
                "deployed_stack_name": "test-stack-deployed",
                "cfn_status": "CREATE_COMPLETE",
                "parameters": {"SecretKey": "secret-abc123"},
                "outputs": {"ApiKey": "key-456789"},
            }
        ]

        # Configure custom patterns
        custom_patterns = [
            CustomMaskingPatternModel(
                pattern="secret-[a-zA-Z0-9]+", replacement="secret-***"
            ),
            CustomMaskingPatternModel(pattern="key-[0-9]+", replacement="key-***"),
        ]
        output_masking = OutputMaskingModel(
            enabled=True, custom_patterns=custom_patterns
        )
        settings = PipelineSettingsModel(output_masking=output_masking)

        report = generate_markdown_report_string(
            report_items, "Test Pipeline", pipeline_settings=settings
        )

        assert "secret-***" in report
        assert "key-***" in report
        assert "secret-abc123" not in report
        assert "key-456789" not in report

    def test_summary_masking_integration(self):
        """Test that summary content is also masked."""
        report_items: List[StackReportItem] = []

        # Enable account ID masking
        categories = OutputMaskingCategoriesModel(account_ids=True)
        output_masking = OutputMaskingModel(enabled=True, categories=categories)
        settings = PipelineSettingsModel(output_masking=output_masking)

        # Summary with account ID
        summary_with_account_id = (
            "Function ARN: arn:aws:lambda:us-west-2:123456789012:function:test"
        )

        report = generate_markdown_report_string(
            report_items,
            "Test Pipeline",
            processed_summary=summary_with_account_id,
            pipeline_settings=settings,
        )

        assert "************" in report  # Account ID in summary should be masked
        assert "123456789012" not in report

    def test_masking_disabled_entirely(self):
        """Test behavior when masking is entirely disabled."""
        enabled, categories, patterns = _resolve_masking_config(None)

        assert enabled is False
        assert categories == {}
        assert patterns == []

    def test_no_pipeline_settings(self):
        """Test behavior when no pipeline settings provided."""
        enabled, categories, patterns = _resolve_masking_config(None)

        assert enabled is False
        assert categories == {}
        assert patterns == []

    def test_masking_enabled_without_specific_categories(self):
        """Test that when masking is enabled without specific categories, all categories are enabled by default."""
        # Just enable masking without specifying any categories
        output_masking = OutputMaskingModel(enabled=True)
        settings = PipelineSettingsModel(output_masking=output_masking)

        enabled, categories, patterns = _resolve_masking_config(settings)

        assert enabled is True
        # All categories should be enabled by default
        assert categories["account_ids"] is True
        assert categories["api_endpoints"] is True
        assert categories["database_endpoints"] is True
        assert categories["load_balancer_dns"] is True
        assert categories["cloudfront_domains"] is True
        assert categories["s3_bucket_domains"] is True
        assert categories["ip_addresses"] is True
        assert patterns == []

    def test_masking_enabled_with_specific_categories(self):
        """Test that when specific categories are provided, only those are enabled."""
        # Enable specific categories
        categories = OutputMaskingCategoriesModel(
            account_ids=True,
            api_endpoints=True,
            # Other categories remain False
        )
        output_masking = OutputMaskingModel(enabled=True, categories=categories)
        settings = PipelineSettingsModel(output_masking=output_masking)

        enabled, resolved_categories, patterns = _resolve_masking_config(settings)

        assert enabled is True
        # Only specified categories should be enabled
        assert resolved_categories["account_ids"] is True
        assert resolved_categories["api_endpoints"] is True
        assert resolved_categories["database_endpoints"] is False
        assert resolved_categories["load_balancer_dns"] is False
        assert resolved_categories["cloudfront_domains"] is False
        assert resolved_categories["s3_bucket_domains"] is False
        assert resolved_categories["ip_addresses"] is False
        assert patterns == []

    def test_masking_enabled_with_only_custom_patterns(self):
        """Test that when custom patterns are provided with enabled=true, built-in categories are also enabled by default."""
        # Only custom patterns, no explicitly configured built-in categories
        custom_patterns = [
            CustomMaskingPatternModel(
                pattern="secret-[a-zA-Z0-9]+", replacement="secret-***"
            )
        ]
        output_masking = OutputMaskingModel(
            enabled=True, custom_patterns=custom_patterns
        )
        settings = PipelineSettingsModel(output_masking=output_masking)

        enabled, categories, patterns = _resolve_masking_config(settings)

        assert enabled is True
        # All built-in categories should be True since enabled=true and no explicit categories
        assert categories["account_ids"] is True
        assert categories["api_endpoints"] is True
        assert categories["database_endpoints"] is True
        assert categories["load_balancer_dns"] is True
        assert categories["cloudfront_domains"] is True
        assert categories["s3_bucket_domains"] is True
        assert categories["ip_addresses"] is True
        # Custom patterns should be present
        assert len(patterns) == 1
        assert patterns[0]["pattern"] == "secret-[a-zA-Z0-9]+"
        assert patterns[0]["replacement"] == "secret-***"
