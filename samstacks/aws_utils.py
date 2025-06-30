"""
AWS utilities for samstacks.
"""

import logging
from typing import Dict, Optional, List, cast, Any
import re

import boto3
from botocore.exceptions import BotoCoreError, ClientError, WaiterError

from .exceptions import OutputRetrievalError, StackDeletionError

logger = logging.getLogger(__name__)


def mask_account_id(value: Any, mask_char: str = "*") -> str:
    """
    Mask AWS account IDs in ARNs and other AWS resource identifiers.

    This function identifies 12-digit AWS account IDs in various contexts and replaces
    them with masked characters for security purposes.

    Args:
        value: The string value that may contain AWS account IDs
        mask_char: Character to use for masking (default: "*")

    Returns:
        String with account IDs masked

    Examples:
        >>> mask_account_id("arn:aws:lambda:us-west-2:123456789012:function:my-function")
        "arn:aws:lambda:us-west-2:************:function:my-function"

        >>> mask_account_id("https://sqs.us-west-2.amazonaws.com/123456789012/my-queue")
        "https://sqs.us-west-2.amazonaws.com/************/my-queue"
    """
    if not isinstance(value, str):
        return str(value)

    # Pattern to match 12-digit AWS account IDs in various contexts
    # This covers:
    # - ARNs: arn:aws:service:region:123456789012:resource
    # - SQS URLs: https://sqs.region.amazonaws.com/123456789012/queue-name
    # - S3 bucket names with account IDs: bucket-name-123456789012
    # - Other AWS resource identifiers with account IDs
    patterns = [
        # ARN pattern: arn:aws:service:region:account-id:resource
        r"(arn:aws:[^:]+:[^:]*:)(\d{12})(:.*)",
        # SQS URL pattern: https://sqs.region.amazonaws.com/account-id/queue-name
        r"(https://sqs\.[^.]+\.amazonaws\.com/)(\d{12})(/.*)",
        # General pattern for standalone 12-digit numbers that look like account IDs
        # Only match if surrounded by non-digit characters or at string boundaries
        r"(?<!\d)(\d{12})(?!\d)",
    ]

    masked_value = value
    mask_replacement = mask_char * 12

    for pattern in patterns:
        if len(re.findall(pattern, masked_value)) > 0:
            # TODO: Consider using named pattern variables instead of array indices for better maintainability
            # This would make the code less fragile if pattern order changes
            if pattern == patterns[2]:  # General pattern - replace entire match
                masked_value = re.sub(pattern, mask_replacement, masked_value)
            else:  # ARN and SQS URL patterns - replace only the account ID part
                masked_value = re.sub(
                    pattern, r"\1" + mask_replacement + r"\3", masked_value
                )

    return masked_value


def mask_api_endpoints(value: Any, mask_char: str = "*") -> str:
    """
    Mask API Gateway URLs, Lambda Function URLs, and other API endpoints.

    Args:
        value: The string value that may contain API endpoints
        mask_char: Character to use for masking (default: "*")

    Returns:
        String with API endpoints masked

    Examples:
        >>> mask_api_endpoints("https://abc123.execute-api.us-west-2.amazonaws.com/prod")
        'https://******.execute-api.us-west-2.amazonaws.com/prod'

        >>> mask_api_endpoints("https://abc123def456.lambda-url.us-west-2.on.aws/")
        'https://************.lambda-url.us-west-2.on.aws/'
    """
    if not isinstance(value, str):
        return str(value)

    patterns = [
        # API Gateway URLs: https://abc123.execute-api.region.amazonaws.com
        (
            r"https://([a-zA-Z0-9]+)\.execute-api\.([\w-]+)\.amazonaws\.com",
            f"https://{mask_char * 6}.execute-api.\\2.amazonaws.com",
        ),
        # Lambda Function URLs: https://abc123def456.lambda-url.region.on.aws
        (
            r"https://([a-zA-Z0-9]+)\.lambda-url\.([\w-]+)\.on\.aws",
            f"https://{mask_char * 12}.lambda-url.\\2.on.aws",
        ),
        # API Gateway custom domain names: https://api.example.com/path
        (r"https://api\.([\w.-]+)(/.*)?", f"https://api.{mask_char * 8}\\2"),
    ]

    masked_value = value
    for pattern, replacement in patterns:
        masked_value = re.sub(pattern, replacement, masked_value)

    return masked_value


def mask_database_endpoints(value: Any, mask_char: str = "*") -> str:
    """
    Mask database connection endpoints for RDS, ElastiCache, DocumentDB, etc.

    Args:
        value: The string value that may contain database endpoints
        mask_char: Character to use for masking (default: "*")

    Returns:
        String with database endpoints masked

    Examples:
        >>> mask_database_endpoints("mydb.abc123.us-west-2.rds.amazonaws.com")
        'mydb.******.us-west-2.rds.amazonaws.com'

        >>> mask_database_endpoints("redis.abc123.cache.amazonaws.com")
        'redis.******.cache.amazonaws.com'
    """
    if not isinstance(value, str):
        return str(value)

    patterns = [
        # RDS endpoints: instance.identifier.region.rds.amazonaws.com
        (
            r"([\w.-]+)\.([a-zA-Z0-9]+)\.([\w-]+)\.rds\.amazonaws\.com",
            f"\\1.{mask_char * 6}.\\3.rds.amazonaws.com",
        ),
        # ElastiCache endpoints: cluster.identifier.cache.amazonaws.com
        (
            r"([\w.-]+)\.([a-zA-Z0-9]+)\.cache\.amazonaws\.com",
            f"\\1.{mask_char * 6}.cache.amazonaws.com",
        ),
        # DocumentDB endpoints: cluster.identifier.region.docdb.amazonaws.com
        (
            r"([\w.-]+)\.([a-zA-Z0-9]+)\.([\w-]+)\.docdb\.amazonaws\.com",
            f"\\1.{mask_char * 6}.\\3.docdb.amazonaws.com",
        ),
        # Neptune endpoints: cluster.identifier.region.neptune.amazonaws.com
        (
            r"([\w.-]+)\.([a-zA-Z0-9]+)\.([\w-]+)\.neptune\.amazonaws\.com",
            f"\\1.{mask_char * 6}.\\3.neptune.amazonaws.com",
        ),
    ]

    masked_value = value
    for pattern, replacement in patterns:
        masked_value = re.sub(pattern, replacement, masked_value)

    return masked_value


def mask_load_balancer_dns(value: Any, mask_char: str = "*") -> str:
    """
    Mask load balancer DNS names (ALB, NLB, CLB).

    Args:
        value: The string value that may contain load balancer DNS names
        mask_char: Character to use for masking (default: "*")

    Returns:
        String with load balancer DNS names masked

    Examples:
        >>> mask_load_balancer_dns("my-alb-123456789.us-west-2.elb.amazonaws.com")
        'my-alb-*********.us-west-2.elb.amazonaws.com'
    """
    if not isinstance(value, str):
        return str(value)

    patterns = [
        # Application/Network Load Balancers: name-hash.region.elb.amazonaws.com
        (
            r"([\w-]+)-([a-zA-Z0-9]+)\.([\w-]+)\.elb\.amazonaws\.com",
            f"\\1-{mask_char * 9}.\\3.elb.amazonaws.com",
        ),
        # Classic Load Balancers: name-hash.region.elb.amazonaws.com
        (
            r"([\w-]+)-([0-9]+)\.([\w-]+)\.elb\.amazonaws\.com",
            f"\\1-{mask_char * 9}.\\3.elb.amazonaws.com",
        ),
    ]

    masked_value = value
    for pattern, replacement in patterns:
        masked_value = re.sub(pattern, replacement, masked_value)

    return masked_value


def mask_cloudfront_domains(value: Any, mask_char: str = "*") -> str:
    """
    Mask CloudFront distribution domain names.

    Args:
        value: The string value that may contain CloudFront domains
        mask_char: Character to use for masking (default: "*")

    Returns:
        String with CloudFront domains masked

    Examples:
        >>> mask_cloudfront_domains("d123456abcdef.cloudfront.net")
        'd************.cloudfront.net'
    """
    if not isinstance(value, str):
        return str(value)

    # CloudFront distribution domains: d123456abcdef.cloudfront.net
    pattern = r"d([a-zA-Z0-9]+)\.cloudfront\.net"
    replacement = f"d{mask_char * 12}.cloudfront.net"

    masked_value = re.sub(pattern, replacement, value)
    return masked_value


def mask_s3_bucket_domains(value: Any, mask_char: str = "*") -> str:
    """
    Mask S3 bucket website endpoints and transfer acceleration endpoints.

    Args:
        value: The string value that may contain S3 bucket domains
        mask_char: Character to use for masking (default: "*")

    Returns:
        String with S3 bucket domains masked

    Examples:
        >>> mask_s3_bucket_domains("mybucket.s3-website-us-west-2.amazonaws.com")
        '********.s3-website-us-west-2.amazonaws.com'
    """
    if not isinstance(value, str):
        return str(value)

    patterns = [
        # S3 website endpoints: bucket.s3-website-region.amazonaws.com
        (
            r"([a-zA-Z0-9.-]+)\.s3-website-([\w-]+)\.amazonaws\.com",
            f"{mask_char * 8}.s3-website-\\2.amazonaws.com",
        ),
        # S3 transfer acceleration: bucket.s3-accelerate.amazonaws.com
        (
            r"([a-zA-Z0-9.-]+)\.s3-accelerate\.amazonaws\.com",
            f"{mask_char * 8}.s3-accelerate.amazonaws.com",
        ),
        # S3 dual-stack endpoints: bucket.s3.dualstack.region.amazonaws.com
        (
            r"([a-zA-Z0-9.-]+)\.s3\.dualstack\.([\w-]+)\.amazonaws\.com",
            f"{mask_char * 8}.s3.dualstack.\\2.amazonaws.com",
        ),
    ]

    masked_value = value
    for pattern, replacement in patterns:
        masked_value = re.sub(pattern, replacement, masked_value)

    return masked_value


def mask_ip_addresses(value: Any, mask_char: str = "*") -> str:
    """
    Mask IPv4 and IPv6 addresses.

    Args:
        value: The string value that may contain IP addresses
        mask_char: Character to use for masking (default: "*")

    Returns:
        String with IP addresses masked

    Examples:
        >>> mask_ip_addresses("Connect to 192.168.1.100 on port 5432")
        'Connect to ***.***.***.*** on port 5432'

        >>> mask_ip_addresses("IPv6: 2001:0db8:85a3:0000:0000:8a2e:0370:7334")
        'IPv6: ****:****:****:****:****:****:****:****'
    """
    if not isinstance(value, str):
        return str(value)

    # TODO: Consider using a more comprehensive IPv6 regex or an IPv6 parsing library
    # Current patterns may not cover all valid IPv6 compressed forms (e.g., addresses starting with '::')
    patterns = [
        # IPv4 addresses: 192.168.1.100
        (
            r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
            f"{mask_char * 3}.{mask_char * 3}.{mask_char * 3}.{mask_char * 3}",
        ),
        # IPv6 addresses: 2001:0db8:85a3:0000:0000:8a2e:0370:7334
        (
            r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b",
            f"{mask_char * 4}:{mask_char * 4}:{mask_char * 4}:{mask_char * 4}:{mask_char * 4}:{mask_char * 4}:{mask_char * 4}:{mask_char * 4}",
        ),
        # IPv6 compressed notation: 2001:db8::1 and ::1
        (
            r"\b[0-9a-fA-F]{1,4}:[0-9a-fA-F]{1,4}::[0-9a-fA-F]{1,4}\b",
            f"{mask_char * 4}::{mask_char * 4}",
        ),
    ]

    masked_value = value
    for pattern, replacement in patterns:
        masked_value = re.sub(pattern, replacement, masked_value)

    return masked_value


def mask_custom_patterns(
    value: Any, patterns: List[Dict[str, str]], mask_char: str = "*"
) -> str:
    """
    Apply custom masking patterns to a value.

    Args:
        value: The string value to mask
        patterns: List of pattern dictionaries with 'pattern' and 'replacement' keys
        mask_char: Default character to use for masking (default: "*")

    Returns:
        String with custom patterns masked
    """
    if not isinstance(value, str) or not patterns:
        return str(value)

    masked_value = value
    for pattern_config in patterns:
        pattern = pattern_config.get("pattern", "")
        replacement = pattern_config.get("replacement", mask_char * 3)

        if pattern:
            try:
                masked_value = re.sub(pattern, replacement, masked_value)
            except re.error:
                # Skip invalid regex patterns
                continue

    return masked_value


def mask_sensitive_data(
    value: Any,
    categories: Optional[Dict[str, bool]] = None,
    custom_patterns: Optional[List[Dict[str, str]]] = None,
    mask_char: str = "*",
) -> str:
    """
    Comprehensive function to mask sensitive data based on enabled categories.

    This is the main function that should be used by the application to apply
    all configured masking rules to a value.

    Args:
        value: The value to mask (will be converted to string)
        categories: Dictionary of category names to boolean enabled flags
        custom_patterns: List of custom pattern configurations
        mask_char: Character to use for masking (default: "*")

    Returns:
        String with all enabled masking applied

    Examples:
        >>> categories = {'account_ids': True, 'api_endpoints': True}
        >>> mask_sensitive_data("arn:aws:lambda:us-west-2:123456789012:function:my-func", categories)
        'arn:aws:lambda:us-west-2:************:function:my-func'
    """
    if categories is None:
        categories = {}

    if custom_patterns is None:
        custom_patterns = []

    masked_value = str(value)

    # Apply category-based masking
    if categories.get("account_ids", False):
        masked_value = mask_account_id(masked_value, mask_char)

    if categories.get("api_endpoints", False):
        masked_value = mask_api_endpoints(masked_value, mask_char)

    if categories.get("database_endpoints", False):
        masked_value = mask_database_endpoints(masked_value, mask_char)

    if categories.get("load_balancer_dns", False):
        masked_value = mask_load_balancer_dns(masked_value, mask_char)

    if categories.get("cloudfront_domains", False):
        masked_value = mask_cloudfront_domains(masked_value, mask_char)

    if categories.get("s3_bucket_domains", False):
        masked_value = mask_s3_bucket_domains(masked_value, mask_char)

    if categories.get("ip_addresses", False):
        masked_value = mask_ip_addresses(masked_value, mask_char)

    # Apply custom patterns
    if custom_patterns:
        masked_value = mask_custom_patterns(masked_value, custom_patterns, mask_char)

    return masked_value


def get_stack_outputs(
    stack_name: str,
    region: Optional[str] = None,
    profile: Optional[str] = None,
) -> Dict[str, str]:
    """
    Retrieve outputs from a CloudFormation stack.

    Args:
        stack_name: Name of the CloudFormation stack
        region: AWS region (optional)
        profile: AWS profile (optional)

    Returns:
        Dictionary mapping output keys to their values

    Raises:
        OutputRetrievalError: If the stack outputs cannot be retrieved
    """
    try:
        # Create session with optional profile
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()

        # Create CloudFormation client
        cf_client = session.client("cloudformation", region_name=region)

        # Describe the stack to get its outputs
        response = cf_client.describe_stacks(StackName=stack_name)

        stacks = response.get("Stacks", [])
        if not stacks:
            raise OutputRetrievalError(f"Stack '{stack_name}' not found")

        stack = stacks[0]
        outputs = stack.get("Outputs", [])

        # Convert outputs list to dictionary
        output_dict = {}
        for output in outputs:
            key = output.get("OutputKey")
            value = output.get("OutputValue")
            if key and value is not None:
                output_dict[key] = value

        logger.debug(f"Retrieved {len(output_dict)} outputs from stack '{stack_name}'")
        return output_dict

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))

        if error_code == "ValidationError":
            raise OutputRetrievalError(
                f"Stack '{stack_name}' does not exist: {error_message}"
            )
        else:
            raise OutputRetrievalError(
                f"AWS error retrieving outputs from stack '{stack_name}': {error_message}"
            )

    except BotoCoreError as e:
        raise OutputRetrievalError(
            f"AWS configuration error retrieving outputs from stack '{stack_name}': {e}"
        )

    except Exception as e:
        raise OutputRetrievalError(
            f"Unexpected error retrieving outputs from stack '{stack_name}': {e}"
        )


def get_stack_status(
    stack_name: str,
    region: str | None = None,
    profile: str | None = None,
) -> str | None:
    """
    Retrieve the current status of a CloudFormation stack.

    Args:
        stack_name: Name of the CloudFormation stack.
        region: AWS region (optional).
        profile: AWS profile (optional).

    Returns:
        The stack status string, or None if the stack does not exist.

    Raises:
        SamStacksError: If there's an AWS or configuration error.
    """
    try:
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        cf_client = session.client("cloudformation", region_name=region)

        response = cf_client.describe_stacks(StackName=stack_name)
        stacks = response.get("Stacks", [])
        if not stacks:
            return None  # Stack does not exist
        # StackStatus is Optional[str] according to boto3-stubs for DescribeStacksOutputTypeDef
        status = stacks[0].get("StackStatus")
        return cast(str, status) if isinstance(status, str) else None

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        if "does not exist" in error_message or error_code == "ValidationError":
            logger.debug(
                f"Stack '{stack_name}' not found when checking status: {error_message}"
            )
            return None  # Stack does not exist
        else:
            raise OutputRetrievalError(  # Re-using OutputRetrievalError for AWS related errors
                f"AWS error checking status for stack '{stack_name}': {error_message}"
            )
    except BotoCoreError as e:
        raise OutputRetrievalError(
            f"AWS configuration error checking status for stack '{stack_name}': {e}"
        )
    except Exception as e:
        raise OutputRetrievalError(
            f"Unexpected error checking status for stack '{stack_name}': {e}"
        )


def delete_cloudformation_stack(
    stack_name: str,
    region: str | None = None,
    profile: str | None = None,
) -> None:
    """
    Deletes a CloudFormation stack.

    Args:
        stack_name: Name of the CloudFormation stack to delete.
        region: AWS region (optional).
        profile: AWS profile (optional).

    Raises:
        StackDeletionError: If deletion fails.
    """
    logger.info(f"Deleting CloudFormation stack: {stack_name}")
    try:
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        cf_client = session.client("cloudformation", region_name=region)
        cf_client.delete_stack(StackName=stack_name)
        logger.debug(f"Delete command issued for stack '{stack_name}'.")
    except Exception as e:
        raise StackDeletionError(
            f"Failed to issue delete for stack '{stack_name}': {e}"
        )


def wait_for_stack_delete_complete(
    stack_name: str,
    region: str | None = None,
    profile: str | None = None,
) -> None:
    """
    Waits for a CloudFormation stack to be deleted successfully.

    Args:
        stack_name: Name of the CloudFormation stack.
        region: AWS region (optional).
        profile: AWS profile (optional).

    Raises:
        StackDeletionError: If waiting fails or stack deletion results in an error.
    """
    logger.info(f"Waiting for stack '{stack_name}' to delete...")
    try:
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        cf_client = session.client("cloudformation", region_name=region)
        waiter = cf_client.get_waiter("stack_delete_complete")
        waiter.wait(
            StackName=stack_name,
            WaiterConfig={
                "Delay": 10,  # Poll every 10 seconds
                "MaxAttempts": 60,  # Wait for up to 10 minutes (60 * 10s)
            },
        )
        logger.info(f"Stack '{stack_name}' deleted successfully.")
    except WaiterError as e:
        # Check if the error is because the stack no longer exists (which is good)
        if "Waiter StackDeleteComplete failed: Max attempts exceeded" in str(
            e
        ) or "Waiter encountered a terminal failure state" in str(e):
            # Sometimes waiter fails if stack is already gone or delete failed in a specific way
            # Double check the status
            current_status = get_stack_status(stack_name, region, profile)
            if current_status is None:
                logger.info(
                    f"Stack '{stack_name}' confirmed deleted after waiter error."
                )
                return
            else:
                raise StackDeletionError(
                    f"Waiter error for stack '{stack_name}' deletion and stack still exists with status {current_status}: {e}"
                )
        raise StackDeletionError(
            f"Error waiting for stack '{stack_name}' to delete: {e}"
        )
    except Exception as e:
        raise StackDeletionError(
            f"Unexpected error waiting for stack '{stack_name}' deletion: {e}"
        )


def list_failed_no_update_changesets(
    stack_name: str,
    region: Optional[str] = None,
    profile: Optional[str] = None,
) -> List[str]:
    """
    Lists ARNs of FAILED changesets with reason "No updates are to be performed."

    Args:
        stack_name: Name of the CloudFormation stack.
        region: AWS region.
        profile: AWS profile.

    Returns:
        A list of changeset ARNs to be deleted.
    """
    changeset_arns = []
    try:
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        cf_client = session.client("cloudformation", region_name=region)

        paginator = cf_client.get_paginator("list_change_sets")
        for page in paginator.paginate(StackName=stack_name):
            for summary in page.get("Summaries", []):
                if (
                    summary.get("Status") == "FAILED"
                    and summary.get("StatusReason") == "No updates are to be performed."
                    and summary.get("ChangeSetId")
                ):
                    changeset_arns.append(summary["ChangeSetId"])

        if changeset_arns:
            logger.debug(
                f"Found {len(changeset_arns)} FAILED changesets with no updates for stack '{stack_name}'."
            )
        return changeset_arns
    except ClientError as e:
        # If stack doesn't exist, list_change_sets will fail. This is acceptable.
        if (
            "does not exist" in str(e)
            or e.response.get("Error", {}).get("Code") == "ValidationError"
        ):
            logger.debug(
                f"Stack '{stack_name}' not found when listing changesets, no cleanup needed."
            )
            return []
        logger.warning(
            f"Error listing changesets for stack '{stack_name}': {e}. Unable to cleanup 'No updates' changesets."
        )
        return []  # Don't block deployment for this type of cleanup error
    except Exception as e:
        logger.warning(
            f"Unexpected error listing changesets for stack '{stack_name}': {e}. Unable to cleanup 'No updates' changesets."
        )
        return []


def delete_changeset(
    changeset_name_or_arn: str,  # Can be ARN or Name
    stack_name: str,
    region: Optional[str] = None,
    profile: Optional[str] = None,
) -> None:
    """
    Deletes a specific CloudFormation changeset.

    Args:
        changeset_name_or_arn: Name or ARN of the changeset.
        stack_name: Name of the stack the changeset belongs to.
        region: AWS region.
        profile: AWS profile.
    """
    logger.debug(
        f"Deleting changeset '{changeset_name_or_arn}' for stack '{stack_name}'."
    )
    try:
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        cf_client = session.client("cloudformation", region_name=region)
        cf_client.delete_change_set(
            ChangeSetName=changeset_name_or_arn, StackName=stack_name
        )
        logger.debug(
            f"Successfully initiated deletion of changeset '{changeset_name_or_arn}'."
        )
    except ClientError as e:
        # If changeset already deleted, it might raise an error. Log and continue.
        logger.warning(
            f"Could not delete changeset '{changeset_name_or_arn}' for stack '{stack_name}': {e}. It might have been already deleted."
        )
    except Exception as e:
        # Catch other potential errors but don't let them stop the main deployment
        logger.error(
            f"Unexpected error deleting changeset '{changeset_name_or_arn}': {e}"
        )
