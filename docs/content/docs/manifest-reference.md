---
title: "Manifest Reference"
weight: 4
prev: examples
next: cli
---

Complete reference for pipeline manifest configuration.

## Pipeline Metadata

```yaml {filename="pipeline.yml"}
pipeline_name: My SAM Application Deployment
pipeline_description: Description of the pipeline
summary: |-
  Optional post-deployment summary shown in console
```

## Pipeline Settings

Configure global settings that apply to all stacks:

```yaml {filename="pipeline.yml"}
pipeline_settings:
  stack_name_prefix: myapp-        # Prefix for all stack names
  default_region: us-east-1        # Default AWS region
  default_sam_config:              # Shared SAM configuration
    version: 0.1
    default:
      deploy:
        parameters:
          capabilities: CAPABILITY_IAM
          confirm_changeset: false
  inputs:                          # Pipeline input parameters
    environment:
      type: string
      default: development
```

## Stack Configuration

Define your deployment stacks:

```yaml {filename="pipeline.yml"}
stacks:
  - id: network                    # Unique stack identifier
    dir: infrastructure/network    # Directory containing SAM template
    template: template.yml         # SAM template file (optional)
    depends_on: []                 # Stack dependencies
    if: ${{ env.DEPLOY_NETWORK }}  # Conditional deployment
    params:                        # Stack parameters
      Environment: ${{ inputs.environment }}
    post_deploy: |-               # Post-deployment actions
      echo "Network deployed successfully"
```

## Stack Properties

### Required Properties

| Property | Type | Description |
|----------|------|-------------|
| `id` | string | Unique identifier for the stack |
| `dir` | string | Directory containing the SAM template |

### Optional Properties

| Property | Type | Description |
|----------|------|-------------|
| `template` | string | SAM template filename (default: `template.yml`) |
| `depends_on` | array | List of stack IDs this stack depends on |
| `if` | string | Conditional expression for deployment |
| `params` | object | Parameters to pass to the stack |
| `post_deploy` | string | Commands to run after deployment |

## Expression Language

samstacks supports GitHub Actions-style expressions:

### Environment Variables
```yaml
params:
  Environment: ${{ env.ENVIRONMENT || 'development' }}
```

### Stack Outputs
```yaml
params:
  VpcId: ${{ stacks.network.outputs.VpcId }}
  DatabaseUrl: ${{ stacks.database.outputs.ConnectionString }}
```

### Input Parameters
```yaml
params:
  InstanceType: ${{ inputs.instance_type }}
```

### Conditional Logic
```yaml
if: ${{ env.ENVIRONMENT == 'production' }}
if: ${{ inputs.deploy_database == 'true' }}
```

### Mathematical Operations
```yaml
params:
  DesiredCapacity: ${{ inputs.base_capacity * 2 }}
  MaxSize: ${{ inputs.base_capacity + 10 }}
```

## Complete Example

```yaml {filename="pipeline.yml"}
pipeline_name: Multi-Tier Application
pipeline_description: Web application with database and API

pipeline_settings:
  stack_name_prefix: myapp-
  default_region: us-west-2
  inputs:
    environment:
      type: string
      default: development

stacks:
  - id: network
    dir: infrastructure/network
    params:
      Environment: ${{ inputs.environment }}
      
  - id: database
    dir: infrastructure/database
    depends_on: [network]
    if: ${{ inputs.environment != 'test' }}
    params:
      VpcId: ${{ stacks.network.outputs.VpcId }}
      SubnetIds: ${{ stacks.network.outputs.PrivateSubnetIds }}
      
  - id: api
    dir: application/api
    depends_on: [database]
    params:
      DatabaseUrl: ${{ stacks.database.outputs.ConnectionString }}
      Environment: ${{ inputs.environment }}
    post_deploy: |-
      echo "API deployed to: ${{ stacks.api.outputs.ApiUrl }}"
```

## Next Steps

- [CLI Reference](../cli) - Command-line interface guide
- [FAQ](../faq) - Frequently asked questions
