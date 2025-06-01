# Example `samstacks` Pipeline

This directory contains a comprehensive example `samstacks` pipeline manifest to demonstrate all major features.

## Prerequisites

Before running this example, ensure you have:
1.  `samstacks` available - either installed (`pip install samstacks`) or run directly via `uvx samstacks` (recommended).
2.  AWS SAM CLI installed and configured.
3.  AWS CLI installed and configured with appropriate credentials and a default region. Region and profile configuration is managed through the `pipeline.yml` manifest using `default_region` and `default_profile` settings.

## `pipeline.yml`

This is a comprehensive "kitchen sink" example pipeline that demonstrates all major `samstacks` features in a single manifest:
- **Pipeline Inputs**: Typed inputs with defaults, validation, and CLI overrides
- **Template Expressions**: Complex mathematical, logical, and fallback expressions
- **SAM Configuration Management**: Centralized SAM CLI configuration
- **Stack Dependencies**: Automatic dependency resolution and output passing
- **Conditional Deployment**: Stack deployment based on input conditions
- **Environment Variable Integration**: Fallbacks and type conversion
- **Post-deployment Scripts**: Automated testing and verification
- **S3 + SQS + Lambda Architecture**: Real-world serverless processing pipeline

**Key Features Demonstrated:**
- `default_sam_config` for global SAM CLI settings (capabilities, region, etc.)
- Automatic generation of `samconfig.yaml` files in each stack directory
- Template expressions with environment variables and fallbacks
- Cross-stack parameter passing using stack outputs

To run this example (ensure AWS credentials and region are configured):

```bash
# Deploy with default inputs (using uvx - no installation required)
uvx samstacks deploy examples/pipeline.yml --auto-delete-failed

# Or override specific inputs
uvx samstacks deploy examples/pipeline.yml \
  -i environment=prod \
  -i expected_users=5000 \
  -i enable_storage_stack=true \
  --auto-delete-failed

# If you've installed samstacks, you can also use:
# samstacks deploy examples/pipeline.yml --auto-delete-failed
```

**What happens during deployment:**
1. `samstacks` generates `samconfig.yaml` files in each stack directory
2. Existing `samconfig.toml` files are automatically backed up to `.toml.bak`
3. SAM CLI uses the generated configurations for deployment
4. Stack outputs are passed between stacks automatically
5. Post-deployment script tests the pipeline by uploading a file

**Generated Configuration Example:**
After deployment, check `stacks/processor/samconfig.yaml` to see the generated configuration:
```yaml
version: 0.1
default:
  deploy:
    parameters:
      capabilities: CAPABILITY_IAM
      confirm_changeset: false
      resolve_s3: true
      region: us-east-1
      stack_name: samstacks-demo-dev-processor
      s3_prefix: samstacks-demo-dev-processor
      parameter_overrides: MessageRetentionPeriod=1209600 ReceiveMessageWaitTimeSeconds=20
```

**Testing SAM Configuration Management:**

After running the pipeline, you can test the individual stack deployment feature:

```bash
# Navigate to a stack directory
cd stacks/processor

# Deploy the individual stack using SAM CLI
# The generated samconfig.yaml contains all necessary configuration
sam deploy

# Check the generated configuration
cat samconfig.yaml

# Verify backup files were created (if any existed before)
ls -la *.bak
```

## Testing Different Scenarios

The pipeline supports various deployment scenarios through input overrides:

```bash
# Production deployment with high user load
uvx samstacks deploy examples/pipeline.yml \
  -i environment=prod \
  -i expected_users=10000 \
  -i message_retention_days=30 \
  --auto-delete-failed

# Development with monitoring disabled
uvx samstacks deploy examples/pipeline.yml \
  -i environment=dev \
  -i enable_storage_stack=false \
  --auto-delete-failed

# Staging environment with custom retention
uvx samstacks deploy examples/pipeline.yml \
  -i environment=staging \
  -i message_retention_days=7 \
  -i expected_users=500 \
  --auto-delete-failed
```

## Key Learning Points

This comprehensive example demonstrates:

1. **Input-driven Configuration**: How pipeline inputs can dynamically configure stack parameters and deployment behavior
2. **Complex Template Expressions**: Mathematical operations, conditional logic, and type conversions in template expressions
3. **Dependency Management**: Automatic resolution of stack dependencies through output references
4. **Environment-specific Deployment**: Using inputs and environment variables to customize deployments per environment
5. **Conditional Infrastructure**: Deploying or skipping stacks based on runtime conditions
6. **Real-world Architecture**: A complete serverless data processing pipeline with S3, SQS, and Lambda

This single pipeline file serves as both a functional example and a comprehensive reference for `samstacks` capabilities.
