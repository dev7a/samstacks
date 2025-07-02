---
title: "Examples"
weight: 40
prev: external-configs
next: manifest-reference
---

Real-world examples to help you get started with samstacks pipelines.

## Complete Application Pipeline

The [`examples/`](https://github.com/dev7a/samstacks/tree/main/examples) directory contains a comprehensive pipeline demonstrating all samstacks features including security-focused output masking:

### Features Demonstrated

- **S3 bucket notifications to SQS** - Event-driven architecture
- **Lambda processing** - Serverless file processing  
- **Stack output dependencies** - Dynamic parameter passing
- **Centralized SAM configuration** - Shared deployment settings
- **Conditional deployment** - Environment-based logic
- **Post-deployment scripts** - Custom automation
- **Summary reporting** - Deployment insights
- **Expression evaluation** - Mathematical and logical operations
- **Security-focused masking** - Protect sensitive data in outputs

### Pipeline Structure

```yaml {filename="examples/pipeline.yml"}
pipeline_name: File Processing System
pipeline_description: S3 → SQS → Lambda processing pipeline

stacks:
  - id: storage
    dir: stacks/storage/
    
  - id: processor  
    dir: stacks/processor/
    params:
      BucketName: ${{ stacks.storage.outputs.BucketName }}
      QueueUrl: ${{ stacks.storage.outputs.QueueUrl }}
```

## Try the Examples

### Basic Multi-Stack Pipeline

```bash
# Clone and deploy the basic example
git clone https://github.com/dev7a/samstacks.git
cd samstacks/examples

# Deploy the basic pipeline
uvx samstacks deploy pipeline.yml
```

### Multi-Environment External Configuration

```bash
# Deploy to different environments
uvx samstacks deploy multi-pipeline.yml --input environment=dev
uvx samstacks deploy multi-pipeline.yml --input environment=prod

# Or use SAM CLI directly with generated configs
cd configs/dev/processor && sam deploy
cd configs/prod/processor && sam deploy
```

## Common Patterns

### External Configuration for Multi-Environment

```yaml {filename="external-config.yml"}
pipeline_settings:
  inputs:
    environment:
      type: string
      default: dev

stacks:
  - id: api
    dir: stacks/api/
    config: configs/${{ inputs.environment }}/api/
    params:
      Environment: ${{ inputs.environment }}
      LogLevel: ${{ inputs.environment == 'prod' && 'WARN' || 'DEBUG' }}
      InstanceType: ${{ inputs.environment == 'prod' && 't3.large' || 't3.micro' }}
```

### Traditional Multi-Environment Deployment

```yaml {filename="multi-env.yml"}
stacks:
  - id: app
    dir: ./app
    if: ${{ env.ENVIRONMENT == 'production' }}
    params:
      InstanceType: t3.large
      
  - id: app-dev
    dir: ./app  
    if: ${{ env.ENVIRONMENT == 'development' }}
    params:
      InstanceType: t3.micro
```

### Cross-Stack References

```yaml {filename="cross-stack.yml"}
stacks:
  - id: network
    dir: ./infrastructure/network
    
  - id: database
    dir: ./infrastructure/database
    params:
      VpcId: ${{ stacks.network.outputs.VpcId }}
      SubnetIds: ${{ stacks.network.outputs.PrivateSubnetIds }}
```

### Secure Deployment with Masking

```yaml {filename="secure-pipeline.yml"}
pipeline_settings:
  output_masking:
    enabled: true
    categories:
      account_ids: true
      api_endpoints: true
      database_endpoints: true

stacks:
  - id: api
    dir: ./api
    # Account IDs, endpoints automatically masked in outputs
```

## Next Steps

- [Manifest Reference](../manifest-reference) - Complete configuration guide
- [CLI Reference](../cli) - Command-line options
