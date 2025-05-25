"""
AWS utilities for samstacks.
"""

import logging
from typing import Dict, Optional, List, cast

import boto3
from botocore.exceptions import BotoCoreError, ClientError, WaiterError

from .exceptions import OutputRetrievalError, StackDeletionError

logger = logging.getLogger(__name__)


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
