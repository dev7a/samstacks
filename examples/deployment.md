# Deployment Report - S3 Object Processor

## Pipeline Description
Comprehensive example demonstrating all major samstacks features:

Features demonstrated:
- Pipeline inputs (string, number, boolean types)
- Environment variable usage with fallbacks and type conversion
- Mathematical expressions (arithmetic, comparisons, boolean logic)
- Stack dependencies and output passing
- Conditional deployment based on complex expressions
- SAM configuration management
- Post-deployment testing scripts
- Template expressions in various contexts
- Capacity planning with dynamic calculations
- Environment-specific configuration scaling

This pipeline deploys an S3 bucket with a Lambda processor that's
triggered by object uploads via SQS notifications.

## Stack Deployment Results

## processor
- **stack name**: `samstacks-demo-dev-processor`
- **CloudFormation Status**: `UPDATE_COMPLETE`
#### Parameters

| Key        | Value                |
|------------|----------------------|
| MessageRetentionPeriod | 1209600 |
| ReceiveMessageWaitTimeSeconds | 20 |
| LambdaMemorySize | 512 |
| MaxConcurrentExecutions | 105 |
| BatchSize | 10 |
| TimeoutSeconds | 10 |
| EnableDetailedLogging | true |
| EnableXrayTracing | false |
#### Outputs

| Key        | Value                |
|------------|----------------------|
| ProcessorFunctionArn | arn:aws:lambda:us-west-2:961341555982:function:samstacks-demo-dev-processor-processor |
| NotificationQueueUrl | https://sqs.us-west-2.amazonaws.com/961341555982/samstacks-demo-dev-processor-notifications |
| Keywords | Keywords for the stack |
| DeadLetterQueueUrl | https://sqs.us-west-2.amazonaws.com/961341555982/samstacks-demo-dev-processor-dlq |
| NotificationQueueArn | arn:aws:sqs:us-west-2:961341555982:samstacks-demo-dev-processor-notifications |
| ProcessorFunctionName | samstacks-demo-dev-processor-processor |

---

## storage
- **stack name**: `samstacks-demo-dev-storage`
- **CloudFormation Status**: `CREATE_COMPLETE`
#### Parameters

| Key        | Value                |
|------------|----------------------|
| NotificationQueueArn | arn:aws:sqs:us-west-2:961341555982:samstacks-demo-dev-processor-notifications |
| Keywords | Keywords for the stack |
| S3StorageClass | STANDARD_IA |
| LifecycleDays | 90 |
| EnableVersioning | false |
| BackupRetentionDays | 7 |
#### Outputs

| Key        | Value                |
|------------|----------------------|
| BucketArn | arn:aws:s3:::samstacks-demo-dev-storage-us-west-2-961341555982 |
| BucketName | samstacks-demo-dev-storage-us-west-2-961341555982 |

---

## Pipeline Summary
# S3 Object Processor - Deployment Complete!

Your **dev** environment has been successfully deployed with a complete serverless object processing pipeline.

## Deployment Configuration

| Setting | Value |
|---------|-------|
| **Environment** | `dev` |
| **AWS Region** | `` |
| **Message Retention** | `14` days (`1209600` seconds) |
| **Expected Users** | `1000` |
| **Lambda Memory** | `512` MB |
| **Max Concurrent Executions** | `105` |
| **Notification Timeout** | `20` seconds |

## Infrastructure Deployed

### Processing Stack (`processor`)
- **Lambda Function**: `samstacks-demo-dev-processor-processor`
- **SQS Queue**: ``
- **Function ARN**: `arn:aws:lambda:us-west-2:961341555982:function:samstacks-demo-dev-processor-processor`

### Storage Stack (`storage`)
- **S3 Bucket**: `samstacks-demo-dev-storage-us-west-2-961341555982`
- **Bucket ARN**: `arn:aws:s3:::samstacks-demo-dev-storage-us-west-2-961341555982`
- **Storage Class**: `STANDARD_IA`
- **Lifecycle**: `90` days

## What's Next?

### 1. **Test Your Pipeline**
```bash
# Upload a test file to trigger processing
aws s3 cp my-file.txt s3://samstacks-demo-dev-storage-us-west-2-961341555982/test-upload.txt
```

### 2. **Monitor Processing**
- **CloudWatch Logs**: Monitor Lambda execution logs
- **SQS Console**: Check queue metrics and dead letter queues
- **S3 Console**: Verify object uploads and lifecycle policies

### 3. **Scale Your Infrastructure**
To adjust capacity for different user loads, redeploy with:
```bash
samstacks deploy examples/pipeline.yml --input expected_users=5000
```

### 4. **Environment Management**
Deploy to different environments:
```bash
# Production deployment
samstacks deploy examples/pipeline.yml \\
  --input environment=prod \\
  --input expected_users=10000 \\
  --input message_retention_days=30

# Development with reduced capacity
samstacks deploy examples/pipeline.yml \\
  --input environment=dev \\
  --input expected_users=100
```

## Useful Resources

- **[AWS Lambda Console](https://console.aws.amazon.com/lambda/)** - Monitor function performance
- **[CloudWatch Logs](https://console.aws.amazon.com/cloudwatch/home#logsV2:log-groups)** - View detailed execution logs
- **[S3 Console](https://console.aws.amazon.com/s3/)** - Manage your buckets and objects
- **[SQS Console](https://console.aws.amazon.com/sqs/)** - Monitor queue metrics

## Advanced Features Demonstrated

This example showcases advanced **samstacks** capabilities:

- **Mathematical Expressions**: Dynamic memory allocation based on user count
- **Conditional Logic**: Environment-specific configurations  
- **Type Conversion**: String to number conversion with `int()`
- **Template Expressions**: Complex boolean and arithmetic operations
- **Stack Dependencies**: Output passing between dependent stacks
- **Input Validation**: Typed inputs with defaults and environment variable fallbacks
- **Post-deployment Testing**: Automated testing via `run` scripts
- **SAM Configuration Management**: Centralized and stack-specific overrides

---

**Congratulations!** Your serverless object processing pipeline is ready to handle 1000 users in the **dev** environment!
