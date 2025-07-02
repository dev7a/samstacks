# samstacks Examples

This directory contains comprehensive examples demonstrating all major **samstacks** features including the new external configuration capabilities.

## Example Pipelines

### **`pipeline.yml`** - Basic Multi-Stack Features
A comprehensive S3 object processing pipeline that demonstrates:

### Core Features
- **Stack Dependencies** - Lambda processor → S3 storage with notification setup
- **Pipeline Inputs** - Typed parameters with environment variable fallbacks
- **Conditional Deployment** - Optional stacks based on input conditions
- **Template Expressions** - Dynamic parameter passing and logical operations
- **Post-deployment Scripts** - Automated testing and verification
- **SAM Configuration Management** - Centralized configuration with stack overrides

### Security Features
- **Comprehensive Output Masking** - Protects sensitive data by default
  - AWS account IDs masked in ARNs and URLs
  - API endpoints and Lambda URLs protected
  - Database connection strings masked
  - Load balancer DNS names protected
  - CloudFront domains masked
  - IP addresses hidden
  - Custom pattern support for application secrets

### **`multi-pipeline.yml`** - External Configuration Feature
A multi-environment pipeline that showcases the new external config capabilities:

#### External Config Features
- **Single Pipeline, Multiple Environments** - One pipeline supports dev, staging, and prod
- **Standalone SAM Configs** - Generated configs work independently with SAM CLI
- **Clean Stack Directories** - No generated files in your source code
- **Template Substitution in Config Paths** - Dynamic config generation based on inputs
- **GitOps Ready** - External configs can be committed and versioned

#### Multi-Environment Structure
```
Single pipeline → Multiple external configs
├── configs/dev/ (development settings)
├── configs/staging/ (staging settings) 
└── configs/prod/ (production settings)
```

#### Benefits
- **Reduced Duplication**: No need for separate pipeline files per environment
- **Direct SAM CLI Usage**: Use generated configs directly without samstacks
- **Environment Isolation**: Different configurations for different environments
- **CI/CD Integration**: Perfect for GitOps workflows

### Pipeline Structure

```
processor stack (Lambda + SQS)
    ↓ (outputs: NotificationQueueArn, Keywords)
storage stack (S3 bucket with notifications)
    ↓ (run: automated testing script)
```

## Quick Start

### Prerequisites
- **AWS CLI** configured with appropriate permissions
- **SAM CLI** installed and available
- **Python 3.8+** for samstacks

### Deploy the Complete Example (`pipeline.yml`)

```bash
# Clone the repository
git clone https://github.com/dev7a/samstacks.git
cd samstacks

# Deploy with default settings (dev environment)
uvx samstacks deploy examples/pipeline.yml

# Deploy to production with secure reporting
uvx samstacks deploy examples/pipeline.yml \
  --input environment=prod \
  --report-file secure-deployment-report.md

# Deploy with storage stack disabled
uvx samstacks deploy examples/pipeline.yml \
  --input enable_storage_stack=false
```

### Try the Multi-Environment Example (`multi-pipeline.yml`)

```bash
# Deploy to development (generates configs/dev/*.yaml)
uvx samstacks deploy examples/multi-pipeline.yml --input environment=dev

# Deploy to staging (generates configs/staging/*.yaml)
uvx samstacks deploy examples/multi-pipeline.yml --input environment=staging

# Deploy to production with custom settings
uvx samstacks deploy examples/multi-pipeline.yml \
  --input environment=prod \
  --input log_level=ERROR \
  --input enable_xray=true

# Use generated configs directly with SAM CLI
sam deploy --config-file examples/configs/dev/processor.yaml
sam deploy --config-file examples/configs/prod/storage.yaml
```

### Environment Variables (Optional)

You can use environment variables to customize the deployment:

```bash
# Set deployment environment
export ENVIRONMENT=staging
export AWS_REGION=eu-west-1

# Deploy using environment variables
uvx samstacks deploy examples/pipeline.yml
```

## What Gets Deployed

### Processing Stack (`processor`)
- **AWS Lambda Function** - Processes S3 object upload events
- **SQS Queue** - Receives S3 notifications for Lambda processing
- **IAM Roles** - Proper permissions for Lambda execution

### Storage Stack (`storage`) 
- **S3 Bucket** - Stores uploaded objects
- **S3 Event Notifications** - Triggers SQS messages on object uploads
- **Bucket Policies** - Security configurations

## Security & Masking

The example pipeline includes comprehensive output masking enabled by default:

```yaml
pipeline_settings:
  output_masking:
    enabled: true
    categories:
      account_ids: true
      api_endpoints: true
      database_endpoints: true
      load_balancer_dns: true
      cloudfront_domains: true
      s3_bucket_domains: true
      ip_addresses: true
    custom_patterns:
      - pattern: "secret-[a-zA-Z0-9]+"
        replacement: "secret-***"
      - pattern: "key-[0-9]+"
        replacement: "key-***"
```

This ensures that:
- Console outputs mask sensitive data
- Deployment reports are safe to share
- CI/CD logs don't expose account information
- Custom application secrets are protected

## Testing the Deployment

After deployment, the pipeline automatically:

1. **Uploads a test file** to the S3 bucket
2. **Triggers the Lambda function** via SQS notification
3. **Verifies processing** by checking CloudWatch logs
4. **Cleans up** the test file

You can also manually test:

```bash
# Upload a file to trigger processing
aws s3 cp my-test-file.txt s3://YOUR_BUCKET_NAME/uploads/

# Check Lambda logs
aws logs tail /aws/lambda/YOUR_FUNCTION_NAME --follow
```

## Understanding the Output

### Console Output (Masked)
```
ProcessorFunctionArn: arn:aws:lambda:us-west-2:************:function:processor
BucketName: samstacks-demo-dev-storage-bucket-xyz
```

### Deployment Report (Masked)
The `--report-file` option generates a markdown report with all sensitive data automatically masked, making it safe to share in:
- Team documentation
- Support tickets
- CI/CD artifacts
- Project wikis

## Clean Up

To remove all deployed resources:

```bash
# Delete all stacks in reverse order
uvx samstacks delete examples/pipeline.yml
```

## Next Steps

- **Learn More**: Visit the [samstacks documentation](https://dev7a.github.io/samstacks/)
- **Customize**: Modify the pipeline for your specific use case
- **Scale**: Add more stacks and dependencies
- **Secure**: Explore additional masking patterns for your application

## Support

For questions, issues, or contributions:
- **Documentation**: https://dev7a.github.io/samstacks/
- **GitHub Issues**: https://github.com/dev7a/samstacks/issues
- **Discussions**: https://github.com/dev7a/samstacks/discussions
