"""
Lambda function to process S3 object upload notifications.
"""

import json
import logging
import os
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client("s3")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Process SQS messages containing S3 object upload notifications.

    Args:
        event: SQS event containing S3 notification messages
        context: Lambda context object

    Returns:
        Dictionary with processing results
    """
    queue_url = os.environ.get("QUEUE_URL")

    logger.info(f"Processing {len(event.get('Records', []))} SQS messages")
    logger.info(f"Queue: {queue_url}")

    processed_objects = []
    errors = []

    for record in event.get("Records", []):
        try:
            # Parse the SQS message body (which contains S3 event notification)
            message_body = json.loads(record["body"])

            # Handle S3 test events (sent when setting up notifications)
            if message_body.get("Event") == "s3:TestEvent":
                logger.info("Received S3 test event - ignoring")
                continue

            # Process S3 records within the message
            for s3_record in message_body.get("Records", []):
                if s3_record.get("eventSource") == "aws:s3":
                    result = process_s3_object(s3_record)
                    if result:
                        processed_objects.append(result)

        except Exception as e:
            error_msg = f"Error processing SQS record: {str(e)}"
            logger.error(error_msg)
            errors.append(error_msg)

    # Log summary
    logger.info(f"Successfully processed {len(processed_objects)} objects")
    if errors:
        logger.error(f"Encountered {len(errors)} errors: {errors}")

    return {
        "statusCode": 200,
        "processedObjects": len(processed_objects),
        "errors": len(errors),
        "objects": processed_objects,
    }


def process_s3_object(s3_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a single S3 object upload notification.

    Args:
        s3_record: S3 event record from the notification

    Returns:
        Dictionary with object processing information
    """
    try:
        # Extract S3 object information
        bucket_name = s3_record["s3"]["bucket"]["name"]
        object_key = s3_record["s3"]["object"]["key"]
        event_name = s3_record["eventName"]
        event_time = s3_record["eventTime"]
        object_size = s3_record["s3"]["object"]["size"]

        logger.info(f"Processing {event_name} for s3://{bucket_name}/{object_key}")

        # Get object metadata
        try:
            response = s3_client.head_object(Bucket=bucket_name, Key=object_key)
            content_type = response.get("ContentType", "unknown")
            last_modified = response.get("LastModified")
            etag = response.get("ETag", "").strip('"')

            logger.info(
                f"Object details - Size: {object_size} bytes, "
                f"Type: {content_type}, ETag: {etag}"
            )

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.warning(f"Object {object_key} no longer exists")
                content_type = "unknown"
                etag = "unknown"
            else:
                raise

        # Perform object processing based on file type
        processing_result = perform_object_processing(
            bucket_name, object_key, content_type, object_size
        )

        return {
            "bucket": bucket_name,
            "key": object_key,
            "event": event_name,
            "eventTime": event_time,
            "size": object_size,
            "contentType": content_type,
            "etag": etag,
            "processingResult": processing_result,
        }

    except Exception as e:
        logger.error(f"Error processing S3 object: {str(e)}")
        raise


def perform_object_processing(
    bucket_name: str, object_key: str, content_type: str, object_size: int
) -> Dict[str, Any]:
    """
    Perform actual processing on the uploaded object.

    This is where you would implement your business logic, such as:
    - Image processing/resizing
    - Document parsing
    - Data validation
    - Triggering downstream workflows

    Args:
        bucket_name: S3 bucket name
        object_key: S3 object key
        content_type: MIME type of the object
        object_size: Size of the object in bytes

    Returns:
        Dictionary with processing results
    """
    logger.info(f"Starting processing for {object_key}")

    # Example processing logic based on content type
    if content_type.startswith("image/"):
        result = process_image(bucket_name, object_key, object_size)
    elif content_type.startswith("text/"):
        result = process_text_file(bucket_name, object_key, object_size)
    elif content_type == "application/json":
        result = process_json_file(bucket_name, object_key, object_size)
    else:
        result = {
            "action": "logged",
            "message": f"Logged upload of {content_type} file ({object_size} bytes)",
        }

    logger.info(f"Processing completed for {object_key}: {result}")
    return result


def process_image(
    bucket_name: str, object_key: str, object_size: int
) -> Dict[str, Any]:
    """Process an image file."""
    return {
        "action": "image_processed",
        "message": f"Image {object_key} processed ({object_size} bytes)",
        "metadata": {
            "type": "image",
            "size_category": "large" if object_size > 1024 * 1024 else "small",
        },
    }


def process_text_file(
    bucket_name: str, object_key: str, object_size: int
) -> Dict[str, Any]:
    """Process a text file."""
    try:
        # Read the text file content (for small files only)
        if object_size < 1024 * 100:  # Only read files smaller than 100KB
            response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
            content = response["Body"].read().decode("utf-8")
            word_count = len(content.split())
            line_count = len(content.splitlines())

            return {
                "action": "text_analyzed",
                "message": f"Text file {object_key} analyzed",
                "metadata": {
                    "type": "text",
                    "word_count": word_count,
                    "line_count": line_count,
                    "size_bytes": object_size,
                },
            }
        else:
            return {
                "action": "text_logged",
                "message": f"Large text file {object_key} logged (too large to analyze)",
                "metadata": {"type": "text", "size_bytes": object_size},
            }

    except Exception as e:
        logger.error(f"Error processing text file {object_key}: {str(e)}")
        return {
            "action": "text_error",
            "message": f"Error processing text file {object_key}: {str(e)}",
        }


def process_json_file(
    bucket_name: str, object_key: str, object_size: int
) -> Dict[str, Any]:
    """Process a JSON file."""
    try:
        # Read and validate JSON content (for small files only)
        if object_size < 1024 * 100:  # Only read files smaller than 100KB
            response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
            content = response["Body"].read().decode("utf-8")
            data = json.loads(content)

            # Count keys if it's a JSON object
            key_count = len(data) if isinstance(data, dict) else "N/A"

            return {
                "action": "json_validated",
                "message": f"JSON file {object_key} validated and processed",
                "metadata": {
                    "type": "json",
                    "valid": True,
                    "key_count": key_count,
                    "size_bytes": object_size,
                },
            }
        else:
            return {
                "action": "json_logged",
                "message": f"Large JSON file {object_key} logged (too large to process)",
                "metadata": {"type": "json", "size_bytes": object_size},
            }

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in file {object_key}: {str(e)}")
        return {
            "action": "json_error",
            "message": f"Invalid JSON in file {object_key}: {str(e)}",
        }
    except Exception as e:
        logger.error(f"Error processing JSON file {object_key}: {str(e)}")
        return {
            "action": "json_error",
            "message": f"Error processing JSON file {object_key}: {str(e)}",
        }
