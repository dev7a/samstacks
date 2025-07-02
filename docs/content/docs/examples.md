---
title: "Examples"
weight: 3
prev: installation
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

## Try the Example

```bash
# Clone and deploy the example
git clone https://github.com/dev7a/samstacks.git
cd samstacks

# Deploy the pipeline
uvx samstacks deploy examples/pipeline.yml
```

## Common Patterns

### Multi-Environment Deployment

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
