"""
Tests for AWS utilities including account ID masking functionality.
"""

from samstacks.aws_utils import (
    mask_account_id,
    mask_api_endpoints,
    mask_database_endpoints,
    mask_load_balancer_dns,
    mask_cloudfront_domains,
    mask_s3_bucket_domains,
    mask_ip_addresses,
    mask_custom_patterns,
    mask_sensitive_data,
)


class TestMaskAccountId:
    """Test cases for the mask_account_id function."""

    def test_mask_lambda_arn(self):
        """Test masking account ID in Lambda function ARN."""
        arn = "arn:aws:lambda:us-west-2:123456789012:function:my-function"
        expected = "arn:aws:lambda:us-west-2:************:function:my-function"
        assert mask_account_id(arn) == expected

    def test_mask_sqs_arn(self):
        """Test masking account ID in SQS queue ARN."""
        arn = "arn:aws:sqs:us-west-2:123456789012:my-queue"
        expected = "arn:aws:sqs:us-west-2:************:my-queue"
        assert mask_account_id(arn) == expected

    def test_mask_s3_arn(self):
        """Test masking account ID in S3 bucket ARN."""
        arn = "arn:aws:s3:::my-bucket-123456789012"
        expected = "arn:aws:s3:::my-bucket-************"
        assert mask_account_id(arn) == expected

    def test_mask_sqs_url(self):
        """Test masking account ID in SQS queue URL."""
        url = "https://sqs.us-west-2.amazonaws.com/123456789012/my-queue"
        expected = "https://sqs.us-west-2.amazonaws.com/************/my-queue"
        assert mask_account_id(url) == expected

    def test_mask_multiple_account_ids(self):
        """Test masking multiple account IDs in the same string."""
        text = "arn:aws:lambda:us-west-2:123456789012:function:my-function and arn:aws:sqs:us-east-1:987654321098:another-queue"
        expected = "arn:aws:lambda:us-west-2:************:function:my-function and arn:aws:sqs:us-east-1:************:another-queue"
        assert mask_account_id(text) == expected

    def test_mask_bucket_name_with_account_id(self):
        """Test masking account ID in S3 bucket name."""
        bucket_name = "my-bucket-us-west-2-123456789012"
        expected = "my-bucket-us-west-2-************"
        assert mask_account_id(bucket_name) == expected

    def test_no_masking_when_no_account_id(self):
        """Test that strings without account IDs are unchanged."""
        text = "This is a normal string without account IDs"
        assert mask_account_id(text) == text

    def test_no_masking_short_numbers(self):
        """Test that short numbers are not masked."""
        text = "Port 8080 and ID 12345"
        assert mask_account_id(text) == text

    def test_no_masking_long_numbers(self):
        """Test that 13+ digit numbers are not masked."""
        text = "This number 1234567890123 has 13 digits"
        assert mask_account_id(text) == text

    def test_custom_mask_character(self):
        """Test using a custom masking character."""
        arn = "arn:aws:lambda:us-west-2:123456789012:function:my-function"
        expected = "arn:aws:lambda:us-west-2:XXXXXXXXXXXX:function:my-function"
        assert mask_account_id(arn, mask_char="X") == expected

    def test_non_string_input(self):
        """Test handling of non-string input."""
        assert mask_account_id(123) == "123"
        assert mask_account_id(None) == "None"

    def test_empty_string(self):
        """Test handling of empty string."""
        assert mask_account_id("") == ""

    def test_account_id_at_string_boundaries(self):
        """Test masking account IDs at the beginning and end of strings."""
        # At the beginning
        text = "123456789012 is the account ID"
        expected = "************ is the account ID"
        assert mask_account_id(text) == expected

        # At the end
        text = "Account ID is 123456789012"
        expected = "Account ID is ************"
        assert mask_account_id(text) == expected

    def test_account_id_with_separators(self):
        """Test masking account IDs surrounded by various separators."""
        test_cases = [
            ("account-123456789012-suffix", "account-************-suffix"),
            ("account_123456789012_suffix", "account_************_suffix"),
            ("account:123456789012:suffix", "account:************:suffix"),
            ("account/123456789012/suffix", "account/************/suffix"),
            ("account 123456789012 suffix", "account ************ suffix"),
        ]

        for input_text, expected in test_cases:
            assert mask_account_id(input_text) == expected

    def test_real_world_examples(self):
        """Test with real-world examples from the codebase."""
        # Example from the deployment.md file
        examples = [
            (
                "arn:aws:lambda:us-west-2:961341555982:function:samstacks-demo-dev-processor-processor",
                "arn:aws:lambda:us-west-2:************:function:samstacks-demo-dev-processor-processor",
            ),
            (
                "https://sqs.us-west-2.amazonaws.com/961341555982/samstacks-demo-dev-processor-notifications",
                "https://sqs.us-west-2.amazonaws.com/************/samstacks-demo-dev-processor-notifications",
            ),
            (
                "samstacks-demo-dev-storage-us-west-2-961341555982",
                "samstacks-demo-dev-storage-us-west-2-************",
            ),
        ]

        for input_text, expected in examples:
            assert mask_account_id(input_text) == expected


class TestMaskApiEndpoints:
    """Test cases for the mask_api_endpoints function."""

    def test_mask_api_gateway_url(self):
        """Test masking API Gateway URL."""
        url = "https://abc123.execute-api.us-west-2.amazonaws.com/prod"
        expected = "https://******.execute-api.us-west-2.amazonaws.com/prod"
        assert mask_api_endpoints(url) == expected

    def test_mask_lambda_function_url(self):
        """Test masking Lambda Function URL."""
        url = "https://abc123def456.lambda-url.us-west-2.on.aws/"
        expected = "https://************.lambda-url.us-west-2.on.aws/"
        assert mask_api_endpoints(url) == expected

    def test_mask_api_custom_domain(self):
        """Test masking API custom domain."""
        url = "https://api.example.com/v1/users"
        expected = "https://api.********/v1/users"
        assert mask_api_endpoints(url) == expected

    def test_no_api_endpoints(self):
        """Test string with no API endpoints remains unchanged."""
        text = "No API endpoints here"
        assert mask_api_endpoints(text) == text

    def test_non_string_input(self):
        """Test non-string input is converted to string."""
        assert mask_api_endpoints(123) == "123"


class TestMaskDatabaseEndpoints:
    """Test cases for the mask_database_endpoints function."""

    def test_mask_rds_endpoint(self):
        """Test masking RDS endpoint."""
        endpoint = "mydb.abc123.us-west-2.rds.amazonaws.com"
        expected = "mydb.******.us-west-2.rds.amazonaws.com"
        assert mask_database_endpoints(endpoint) == expected

    def test_mask_elasticache_endpoint(self):
        """Test masking ElastiCache endpoint."""
        endpoint = "redis.abc123.cache.amazonaws.com"
        expected = "redis.******.cache.amazonaws.com"
        assert mask_database_endpoints(endpoint) == expected

    def test_mask_documentdb_endpoint(self):
        """Test masking DocumentDB endpoint."""
        endpoint = "docdb.abc123.us-west-2.docdb.amazonaws.com"
        expected = "docdb.******.us-west-2.docdb.amazonaws.com"
        assert mask_database_endpoints(endpoint) == expected

    def test_mask_neptune_endpoint(self):
        """Test masking Neptune endpoint."""
        endpoint = "neptune.abc123.us-west-2.neptune.amazonaws.com"
        expected = "neptune.******.us-west-2.neptune.amazonaws.com"
        assert mask_database_endpoints(endpoint) == expected

    def test_no_database_endpoints(self):
        """Test string with no database endpoints remains unchanged."""
        text = "No database endpoints here"
        assert mask_database_endpoints(text) == text


class TestMaskLoadBalancerDns:
    """Test cases for the mask_load_balancer_dns function."""

    def test_mask_alb_dns(self):
        """Test masking Application Load Balancer DNS."""
        dns = "my-alb-123456789.us-west-2.elb.amazonaws.com"
        expected = "my-alb-*********.us-west-2.elb.amazonaws.com"
        assert mask_load_balancer_dns(dns) == expected

    def test_mask_nlb_dns(self):
        """Test masking Network Load Balancer DNS."""
        dns = "my-nlb-abcdef123.us-east-1.elb.amazonaws.com"
        expected = "my-nlb-*********.us-east-1.elb.amazonaws.com"
        assert mask_load_balancer_dns(dns) == expected

    def test_mask_clb_dns(self):
        """Test masking Classic Load Balancer DNS."""
        dns = "my-clb-1234567890.us-west-2.elb.amazonaws.com"
        expected = "my-clb-*********.us-west-2.elb.amazonaws.com"
        assert mask_load_balancer_dns(dns) == expected

    def test_no_load_balancer_dns(self):
        """Test string with no load balancer DNS remains unchanged."""
        text = "No load balancer DNS here"
        assert mask_load_balancer_dns(text) == text


class TestMaskCloudfrontDomains:
    """Test cases for the mask_cloudfront_domains function."""

    def test_mask_cloudfront_domain(self):
        """Test masking CloudFront distribution domain."""
        domain = "d123456abcdef.cloudfront.net"
        expected = "d************.cloudfront.net"
        assert mask_cloudfront_domains(domain) == expected

    def test_no_cloudfront_domains(self):
        """Test string with no CloudFront domains remains unchanged."""
        text = "No CloudFront domains here"
        assert mask_cloudfront_domains(text) == text


class TestMaskS3BucketDomains:
    """Test cases for the mask_s3_bucket_domains function."""

    def test_mask_s3_website_endpoint(self):
        """Test masking S3 website endpoint."""
        endpoint = "mybucket.s3-website-us-west-2.amazonaws.com"
        expected = "********.s3-website-us-west-2.amazonaws.com"
        assert mask_s3_bucket_domains(endpoint) == expected

    def test_mask_s3_accelerate_endpoint(self):
        """Test masking S3 transfer acceleration endpoint."""
        endpoint = "mybucket.s3-accelerate.amazonaws.com"
        expected = "********.s3-accelerate.amazonaws.com"
        assert mask_s3_bucket_domains(endpoint) == expected

    def test_mask_s3_dualstack_endpoint(self):
        """Test masking S3 dual-stack endpoint."""
        endpoint = "mybucket.s3.dualstack.us-west-2.amazonaws.com"
        expected = "********.s3.dualstack.us-west-2.amazonaws.com"
        assert mask_s3_bucket_domains(endpoint) == expected

    def test_no_s3_bucket_domains(self):
        """Test string with no S3 bucket domains remains unchanged."""
        text = "No S3 bucket domains here"
        assert mask_s3_bucket_domains(text) == text


class TestMaskIpAddresses:
    """Test cases for the mask_ip_addresses function."""

    def test_mask_ipv4_address(self):
        """Test masking IPv4 address."""
        text = "Connect to 192.168.1.100 on port 5432"
        expected = "Connect to ***.***.***.*** on port 5432"
        assert mask_ip_addresses(text) == expected

    def test_mask_ipv6_address(self):
        """Test masking IPv6 address."""
        text = "IPv6: 2001:0db8:85a3:0000:0000:8a2e:0370:7334"
        expected = "IPv6: ****:****:****:****:****:****:****:****"
        assert mask_ip_addresses(text) == expected

    def test_mask_ipv6_compressed(self):
        """Test masking compressed IPv6 address."""
        text = "IPv6 compressed: 2001:db8::1"
        expected = "IPv6 compressed: ****::****"
        assert mask_ip_addresses(text) == expected

    def test_multiple_ip_addresses(self):
        """Test masking multiple IP addresses."""
        text = "Primary: 10.0.1.5 and Secondary: 172.16.0.100"
        expected = "Primary: ***.***.***.*** and Secondary: ***.***.***.***"
        assert mask_ip_addresses(text) == expected

    def test_no_ip_addresses(self):
        """Test string with no IP addresses remains unchanged."""
        text = "No IP addresses here"
        assert mask_ip_addresses(text) == text


class TestMaskCustomPatterns:
    """Test cases for the mask_custom_patterns function."""

    def test_single_custom_pattern(self):
        """Test masking with a single custom pattern."""
        text = "secret-abc123"
        patterns = [{"pattern": r"secret-[a-zA-Z0-9]+", "replacement": "secret-***"}]
        expected = "secret-***"
        assert mask_custom_patterns(text, patterns) == expected

    def test_multiple_custom_patterns(self):
        """Test masking with multiple custom patterns."""
        text = "secret-abc123 and token-xyz789"
        patterns = [
            {"pattern": r"secret-[a-zA-Z0-9]+", "replacement": "secret-***"},
            {"pattern": r"token-[a-zA-Z0-9]+", "replacement": "token-***"},
        ]
        expected = "secret-*** and token-***"
        assert mask_custom_patterns(text, patterns) == expected

    def test_invalid_regex_pattern(self):
        """Test that invalid regex patterns are skipped."""
        text = "secret-abc123"
        patterns = [{"pattern": "[invalid", "replacement": "***"}]  # Invalid regex
        # Should return original text since invalid pattern is skipped
        assert mask_custom_patterns(text, patterns) == text

    def test_empty_patterns_list(self):
        """Test that empty patterns list returns original text."""
        text = "secret-abc123"
        patterns = []
        assert mask_custom_patterns(text, patterns) == text

    def test_pattern_without_replacement(self):
        """Test pattern without explicit replacement uses default."""
        text = "secret-abc123"
        patterns = [{"pattern": r"secret-[a-zA-Z0-9]+"}]  # No replacement specified
        expected = "***"  # Default replacement
        assert mask_custom_patterns(text, patterns) == expected


class TestMaskSensitiveData:
    """Test cases for the unified mask_sensitive_data function."""

    def test_account_ids_only(self):
        """Test masking account IDs only."""
        text = "arn:aws:lambda:us-west-2:123456789012:function:my-function"
        categories = {"account_ids": True}
        expected = "arn:aws:lambda:us-west-2:************:function:my-function"
        assert mask_sensitive_data(text, categories) == expected

    def test_multiple_categories(self):
        """Test masking with multiple categories enabled."""
        text = "Account 123456789012 API: https://abc123.execute-api.us-west-2.amazonaws.com/prod IP: 192.168.1.100"
        categories = {"account_ids": True, "api_endpoints": True, "ip_addresses": True}
        expected = "Account ************ API: https://******.execute-api.us-west-2.amazonaws.com/prod IP: ***.***.***.***"
        assert mask_sensitive_data(text, categories) == expected

    def test_custom_patterns_only(self):
        """Test masking with custom patterns only."""
        text = "secret-abc123"
        categories = {}
        custom_patterns = [
            {"pattern": r"secret-[a-zA-Z0-9]+", "replacement": "secret-***"}
        ]
        expected = "secret-***"
        assert mask_sensitive_data(text, categories, custom_patterns) == expected

    def test_categories_and_custom_patterns(self):
        """Test masking with both categories and custom patterns."""
        text = "Account 123456789012 and secret-abc123"
        categories = {"account_ids": True}
        custom_patterns = [
            {"pattern": r"secret-[a-zA-Z0-9]+", "replacement": "secret-***"}
        ]
        expected = "Account ************ and secret-***"
        assert mask_sensitive_data(text, categories, custom_patterns) == expected

    def test_no_masking_enabled(self):
        """Test that no masking is applied when all categories are False."""
        text = "Account 123456789012 API: https://abc123.execute-api.us-west-2.amazonaws.com/prod"
        categories = {
            "account_ids": False,
            "api_endpoints": False,
            "database_endpoints": False,
            "load_balancer_dns": False,
            "cloudfront_domains": False,
            "s3_bucket_domains": False,
            "ip_addresses": False,
        }
        assert mask_sensitive_data(text, categories) == text

    def test_all_categories_enabled(self):
        """Test masking with all categories enabled."""
        text = (
            "Account: 123456789012, "
            "API: https://abc123.execute-api.us-west-2.amazonaws.com/prod, "
            "DB: mydb.abc123.us-west-2.rds.amazonaws.com, "
            "LB: my-alb-123456789.us-west-2.elb.amazonaws.com, "
            "CDN: d123456abcdef.cloudfront.net, "
            "S3: mybucket.s3-website-us-west-2.amazonaws.com, "
            "IP: 192.168.1.100"
        )
        categories = {
            "account_ids": True,
            "api_endpoints": True,
            "database_endpoints": True,
            "load_balancer_dns": True,
            "cloudfront_domains": True,
            "s3_bucket_domains": True,
            "ip_addresses": True,
        }
        result = mask_sensitive_data(text, categories)

        # Verify each type is masked
        assert "************" in result  # Account ID
        assert "******.execute-api" in result  # API Gateway
        assert "******.us-west-2.rds" in result  # RDS
        assert "*********." in result  # Load balancer
        assert "d************.cloudfront" in result  # CloudFront
        assert "********.s3-website" in result  # S3
        assert "***.***.***.***" in result  # IP address

    def test_empty_categories_dict(self):
        """Test with empty categories dictionary."""
        text = "Account 123456789012"
        categories = {}
        assert mask_sensitive_data(text, categories) == text

    def test_none_categories_dict(self):
        """Test with None categories dictionary."""
        text = "Account 123456789012"
        categories = None
        assert mask_sensitive_data(text, categories) == text

    def test_custom_mask_character(self):
        """Test using custom mask character."""
        text = "Account 123456789012"
        categories = {"account_ids": True}
        expected = "Account ############"
        assert mask_sensitive_data(text, categories, mask_char="#") == expected

    def test_non_string_input(self):
        """Test non-string input is converted to string."""
        categories = {"account_ids": True}
        assert mask_sensitive_data(123456789012, categories) == "************"
        assert mask_sensitive_data(None, categories) == "None"
