# S3 Object Processor Example

This example demonstrates a complete serverless pipeline using `samstacks` that processes files uploaded to an S3 bucket.

## Architecture

The pipeline consists of two stacks:

1. **Storage Stack** (`stacks/storage/`):
   - S3 bucket for file uploads
   - SQS queue for S3 event notifications
   - Dead letter queue for failed messages

2. **Processor Stack** (`stacks/processor/`):
   - Lambda function triggered by SQS messages
   - Processes different file types (images, text, JSON)
   - CloudWatch logs for monitoring

## Prerequisites

- AWS CLI configured with appropriate credentials
- AWS SAM CLI installed
- Python 3.8+ and `samstacks` installed

## Deployment

1. Set required environment variables:
```bash
export ENVIRONMENT=dev
export PROJECT_NAME=my-project
```

2. Deploy the pipeline:
```bash
samstacks deploy examples/simple-pipeline.yml
```

## What Gets Created

### Storage Stack Resources
- **S3 Bucket**: `{PROJECT_NAME}-{ENVIRONMENT}-{ACCOUNT_ID}`
- **SQS Queue**: `{PROJECT_NAME}-{ENVIRONMENT}-notifications`
- **Dead Letter Queue**: `{PROJECT_NAME}-{ENVIRONMENT}-dlq`

### Processor Stack Resources
- **Lambda Function**: `{ENVIRONMENT}-processor-processor`
- **CloudWatch Log Group**: `/aws/lambda/{ENVIRONMENT}-processor-processor`

## Testing the Pipeline

After deployment, the pipeline automatically tests itself by uploading a test file. You can also manually test:

1. Upload a file to the S3 bucket:
```bash
# Get the bucket name from the stack outputs
BUCKET_NAME=$(aws cloudformation describe-stacks \
  --stack-name "${ENVIRONMENT}-storage" \
  --query 'Stacks[0].Outputs[?OutputKey==`BucketName`].OutputValue' \
  --output text)

# Upload a test file
echo "Hello from samstacks!" > test.txt
aws s3 cp test.txt "s3://${BUCKET_NAME}/test.txt"
```

2. Check the Lambda function logs:
```bash
# Get the function name
FUNCTION_NAME=$(aws cloudformation describe-stacks \
  --stack-name "${ENVIRONMENT}-processor" \
  --query 'Stacks[0].Outputs[?OutputKey==`ProcessorFunctionName`].OutputValue' \
  --output text)

# View recent logs
aws logs tail "/aws/lambda/${FUNCTION_NAME}" --follow
```

## File Processing Logic

The Lambda function processes different file types:

- **Images** (`image/*`): Logs processing and categorizes by size
- **Text files** (`text/*`): Analyzes word and line count for small files
- **JSON files** (`application/json`): Validates JSON and counts keys
- **Other files**: Simply logs the upload

## Customization

### Adding New File Types

Edit `examples/stacks/processor/src/processor.py` and add new processing functions in the `perform_object_processing` function.

### Modifying S3 Events

Edit the `NotificationConfiguration` in `examples/stacks/storage/template.yaml` to change which S3 events trigger processing.

### Scaling Configuration

Modify the SQS event source configuration in `examples/stacks/processor/template.yaml`:
- `BatchSize`: Number of messages processed per Lambda invocation
- `MaximumBatchingWindowInSeconds`: How long to wait for a full batch

## Cleanup

To remove all resources:

```bash
# Delete the stacks in reverse order
aws cloudformation delete-stack --stack-name "${ENVIRONMENT}-processor"
aws cloudformation delete-stack --stack-name "${ENVIRONMENT}-storage"

# Wait for deletion to complete
aws cloudformation wait stack-delete-complete --stack-name "${ENVIRONMENT}-processor"
aws cloudformation wait stack-delete-complete --stack-name "${ENVIRONMENT}-storage"
```

## Cost Considerations

This example uses AWS Free Tier eligible services where possible:
- S3: First 5GB of storage free
- Lambda: First 1M requests and 400,000 GB-seconds free per month
- SQS: First 1M requests free per month
- CloudWatch Logs: First 5GB of ingestion free per month

## Troubleshooting

### Lambda Function Not Triggered

1. Check SQS queue for messages:
```bash
QUEUE_URL=$(aws cloudformation describe-stacks \
  --stack-name "${ENVIRONMENT}-storage" \
  --query 'Stacks[0].Outputs[?OutputKey==`NotificationQueueUrl`].OutputValue' \
  --output text)

aws sqs get-queue-attributes --queue-url "${QUEUE_URL}" --attribute-names ApproximateNumberOfMessages
```

2. Check Lambda function event source mapping:
```bash
aws lambda list-event-source-mappings --function-name "${FUNCTION_NAME}"
```

### Permission Issues

Ensure your AWS credentials have the necessary permissions for:
- CloudFormation stack operations
- S3 bucket operations
- Lambda function management
- SQS queue operations
- IAM role creation 