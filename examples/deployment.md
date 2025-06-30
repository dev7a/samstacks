# Deployment Report - S3 Object Processor

## Pipeline Description
Comprehensive example demonstrating all major samstacks features including
security-focused output masking. This pipeline deploys an S3 bucket with 
a Lambda processor triggered by object uploads via SQS notifications.

Features demonstrated:
- Security-focused output masking for production deployments
- Stack dependencies and output passing
- Pipeline inputs with typed parameters
- Conditional deployment logic
- Post-deployment automation scripts

## Stack Deployment Results

## processor
- **stack name**: `samstacks-demo-dev-processor`
- **CloudFormation Status**: `UPDATE_COMPLETE`
#### Parameters

| Key        | Value                |
|------------|----------------------|
| Environment | dev |
| EnableDetailedLogging | true |
| EnableXrayTracing | false |
#### Outputs

| Key        | Value                |
|------------|----------------------|
| ProcessorFunctionArn | arn:aws:lambda:us-west-2:************:function:samstacks-demo-dev-processor-processor |
| NotificationQueueUrl | https://sqs.us-west-2.amazonaws.com/************/samstacks-demo-dev-processor-notifications |
| Keywords | Keywords for the stack |
| DeadLetterQueueUrl | https://sqs.us-west-2.amazonaws.com/************/samstacks-demo-dev-processor-dlq |
| NotificationQueueArn | arn:aws:sqs:us-west-2:************:samstacks-demo-dev-processor-notifications |
| ProcessorFunctionName | samstacks-demo-dev-processor-processor |

---

## storage
- **stack name**: `samstacks-demo-dev-storage`
- **CloudFormation Status**: `CREATE_COMPLETE`
#### Parameters

| Key        | Value                |
|------------|----------------------|
| NotificationQueueArn | arn:aws:sqs:us-west-2:************:samstacks-demo-dev-processor-notifications |
| Keywords | Keywords for the stack |
| S3StorageClass | STANDARD_IA |
| EnableVersioning | false |
#### Outputs

| Key        | Value                |
|------------|----------------------|
| BucketArn | arn:aws:s3:::samstacks-demo-dev-storage-us-west-2-************ |
| BucketName | samstacks-demo-dev-storage-us-west-2-************ |

---

## Pipeline Summary
# S3 Object Processor - Deployment Complete!

Your **dev** environment has been successfully deployed with comprehensive security masking enabled.

## Deployment Configuration

| Setting | Value |
|---------|-------|
| **Environment** | `dev` |
| **AWS Region** | `` |
| **Storage Stack Enabled** | `true` |

## Infrastructure Deployed

### Processing Stack (`processor`)
- **Lambda Function**: `samstacks-demo-dev-processor-processor`
- **Function ARN**: `arn:aws:lambda:us-west-2:************:function:samstacks-demo-dev-processor-processor`
- **SQS Queue**: ``

### Storage Stack (`storage`)
- **S3 Bucket**: `samstacks-demo-dev-storage-us-west-2-************`
- **Bucket ARN**: `arn:aws:s3:::samstacks-demo-dev-storage-us-west-2-************`
- **Storage Class**: `STANDARD_IA`

## Security Features

This deployment includes comprehensive output masking to protect sensitive data:
- **Account IDs** - Masked in all ARNs and URLs
- **API Endpoints** - API Gateway and Lambda URLs protected
- **Database Endpoints** - Connection strings masked
- **Load Balancer DNS** - ALB/NLB domains protected
- **CloudFront Domains** - Distribution domains masked
- **IP Addresses** - IPv4 and IPv6 addresses protected
- **Custom Patterns** - Application-specific secrets masked

> **Note**: All sensitive data in the above outputs has been automatically 
> masked with asterisks (*) for security. This makes it safe to share 
> deployment reports, logs, and artifacts without exposing sensitive information.

## What's Next?

### 1. **Test Your Pipeline**
```bash
# Upload a test file to trigger processing
aws s3 cp my-file.txt s3://samstacks-demo-dev-storage-us-west-2-************/test-upload.txt
```

### 2. **Monitor Processing**
- **CloudWatch Logs**: Monitor Lambda execution logs
- **SQS Console**: Check queue metrics and dead letter queues
- **S3 Console**: Verify object uploads and lifecycle policies

### 3. **Environment Management**
Deploy to different environments:
```bash
# Production deployment with security masking
samstacks deploy examples/pipeline.yml \\
  --input environment=prod \\
  --report-file secure-deployment-report.md

# Development deployment
samstacks deploy examples/pipeline.yml \\
  --input environment=dev
```

---

**Congratulations!** Your serverless object processing pipeline is ready in the **dev** environment with comprehensive security protection!
