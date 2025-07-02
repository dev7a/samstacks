---
title: "External Configuration"
weight: 50
description: "Generate standalone SAM config files for multi-environment deployments and direct SAM CLI usage"
---

# External Configuration

The external configuration feature allows samstacks to generate standalone SAM configuration files that work independently with the SAM CLI. This enables powerful multi-environment workflows, GitOps practices, and direct team collaboration while maintaining samstacks' orchestration benefits.

## Overview

By default, samstacks uses local `samconfig.yaml` files in each stack directory. External configurations change this behavior by generating SAM config files at specified paths outside the stack directories.

### Key Benefits

- **Single Source of Truth**: One pipeline definition supports multiple environments
- **Standalone Configs**: Generated configurations work independently with SAM CLI
- **Clean Repositories**: No generated files mixed with source code
- **GitOps Ready**: Commit generated configs for reproducible deployments
- **Direct SAM CLI Usage**: Skip orchestrator for quick individual stack deployments
- **Team Collaboration**: Different teams can use SAM CLI directly

## Basic Usage

Add a `config` field to any stack definition to enable external configuration:

```yaml
pipeline_name: My Application
stacks:
  - id: api
    dir: stacks/api/
    config: configs/production/api/  # External config directory
    params:
      Environment: production
```

When deployed, samstacks will:

1. **Generate** a complete SAM configuration file at `configs/production/api/samconfig.yaml`
2. **Deploy** the stack using the external configuration
3. **Create** all necessary directories automatically

> [!TIP]
> **Directory-Based Configs**: Using `config: configs/production/api/` (ending with `/`) automatically creates `samconfig.yaml` in that directory. This prevents conflicts with shared `.aws-sam` build directories and follows the "one directory, one stack" philosophy.

## Multi-Environment Deployment

The most powerful use case is deploying the same pipeline to multiple environments using template expressions:

```yaml
pipeline_name: Multi-Environment API
pipeline_settings:
  inputs:
    environment:
      type: string
      default: dev

stacks:
  - id: backend-api
    dir: stacks/api/
    config: configs/${{ inputs.environment }}/api/
    params:
      Environment: ${{ inputs.environment }}
      LogLevel: ${{ inputs.environment == 'prod' && 'WARN' || 'DEBUG' }}
      InstanceType: ${{ inputs.environment == 'prod' && 't3.large' || 't3.micro' }}
      
  - id: database
    dir: stacks/database/
    config: configs/${{ inputs.environment }}/database/
    params:
      Environment: ${{ inputs.environment }}
      BackupRetentionDays: ${{ inputs.environment == 'prod' && '365' || '7' }}
```

### Deploy to Multiple Environments

```bash
# Deploy to development
samstacks deploy pipeline.yml --input environment=dev

# Deploy to staging
samstacks deploy pipeline.yml --input environment=staging

# Deploy to production
samstacks deploy pipeline.yml --input environment=prod
```

### Delete Environment-Specific Deployments

The delete command supports the same multi-environment functionality:

```bash
# Delete development environment
samstacks delete pipeline.yml --input environment=dev

# Delete staging environment (with dry-run preview)
samstacks delete pipeline.yml --input environment=staging --dry-run

# Delete production environment
samstacks delete pipeline.yml --input environment=prod
```

For external configurations, the delete command will:
- Resolve template expressions in config paths based on input values
- Use the appropriate external config files with `sam delete --config-file`
- Fall back to local `samconfig.yaml` files when external configs aren't found

This creates the following structure:

```
project/
├── pipeline.yml
├── stacks/
│   ├── api/
│   │   ├── template.yaml
│   │   └── src/
│   └── database/
│       └── template.yaml
└── configs/                               # Generated external configs
    ├── dev/
    │   ├── api/
    │   │   └── samconfig.yaml             # Dev-specific API config
    │   └── database/
    │       └── samconfig.yaml             # Dev-specific DB config
    ├── staging/
    │   ├── api/
    │   │   └── samconfig.yaml
    │   └── database/
    │       └── samconfig.yaml
    └── prod/
        ├── api/
        │   └── samconfig.yaml
        └── database/
            └── samconfig.yaml
```

## Template Path Resolution

External SAM configurations automatically include proper template file references using relative paths:

### Generated Configuration Example

When you define:
```yaml
- id: api
  dir: stacks/api/
  config: configs/dev/api/
```

The generated `configs/dev/api/samconfig.yaml` contains:

```yaml
version: 0.1
default:
  global:
    parameters:
      beta_features: false
  build:
    parameters:
      template: ../../../stacks/api/template.yaml  # Relative path to template
  deploy:
    parameters:
      stack_name: my-app-dev-api
      region: us-west-2
      capabilities: CAPABILITY_IAM
      parameter_overrides:
        - Environment=dev
        - LogLevel=DEBUG
      template: ../../../stacks/api/template.yaml   # Relative path to template
```

The relative paths (`../../../stacks/api/template.yaml`) are automatically calculated to point from the config file location to the actual CloudFormation template.

## Config Path Formats

samstacks supports two config path formats with built-in validation:

### Directory-Based (Recommended)

```yaml
# Automatically creates samconfig.yaml in the specified directory
config: configs/${{ inputs.environment }}/api/
```

**Benefits:**
- **Isolated Build Artifacts**: Each config gets its own `.aws-sam/` directory
- **Clean SAM CLI Usage**: `cd configs/dev/api && sam deploy` works naturally
- **No File Conflicts**: Multiple stacks can't interfere with each other
- **Follows Best Practices**: Maintains "one directory, one stack" philosophy

### Explicit File Path

```yaml
# Use a specific filename
config: configs/${{ inputs.environment }}/api/samconfig.yaml
config: shared/environments/dev-api-config.yml
```

### Validation Rules

samstacks validates config paths to prevent common issues:

- **Ends with `/`**: Directory path → automatically appends `samconfig.yaml`
- **Ends with `.yaml` or `.yml`**: File path → used as-is
- **Anything else**: Validation error with helpful message

```yaml
# ✅ Valid configurations
config: configs/dev/api/                    # Directory-based
config: configs/dev/api/samconfig.yaml     # Explicit file
config: environments/dev/api-config.yml    # Custom filename

# ❌ Invalid configurations  
config: configs/dev/api                     # Missing trailing slash or extension
config: configs/dev/api/config.json        # Wrong file extension
```

## Direct SAM CLI Usage

Generated external configurations work seamlessly with the SAM CLI:

### Individual Stack Deployment

```bash
# Navigate to the config directory and deploy
cd configs/dev/api
sam deploy

# Or specify the config file explicitly
sam deploy --config-file configs/dev/api/samconfig.yaml

# Build and deploy in sequence
cd configs/dev/api
sam build && sam deploy
```

### Individual Stack Deletion

```bash
# Navigate to the config directory and delete
cd configs/dev/api
sam delete --no-prompts

# Or specify the config file explicitly
sam delete --config-file configs/dev/api/samconfig.yaml --no-prompts
```

### Team Workflows

Different team members can deploy and delete using their preferred tool:

```bash
# DevOps team uses samstacks for orchestration
samstacks deploy pipeline.yml --input environment=dev
samstacks delete pipeline.yml --input environment=dev

# Development team uses SAM CLI for quick iterations
cd configs/dev/api && sam deploy
cd configs/dev/api && sam delete --no-prompts

# CI/CD pipeline uses generated configs
sam deploy --config-file configs/prod/api/samconfig.yaml
sam delete --config-file configs/prod/api/samconfig.yaml --no-prompts
```

## Configuration Backup and Safety

External configurations include built-in safety features:

### Automatic Backups

When an external config file already exists, samstacks automatically creates a backup:

```
configs/dev/api/
├── samconfig.yaml       # New configuration
└── samconfig.yaml.bak   # Previous version backup
```

### Directory Creation

samstacks automatically creates all necessary parent directories:

```bash
# This works even if configs/ doesn't exist yet
config: configs/new-env/new-stack/samconfig.yaml
```

## Advanced Use Cases

### GitOps Workflows

Commit generated configurations for reproducible deployments:

```bash
# Generate configs for all environments
samstacks deploy pipeline.yml --input environment=dev
samstacks deploy pipeline.yml --input environment=staging  
samstacks deploy pipeline.yml --input environment=prod

# Commit the generated configs
git add configs/
git commit -m "Update deployment configurations"
git push

# Deploy/delete in CI/CD using committed configs
sam deploy --config-file configs/prod/api/samconfig.yaml
sam delete --config-file configs/prod/api/samconfig.yaml --no-prompts
```

### Environment Isolation

Keep different environments completely isolated:

```yaml
stacks:
  - id: api
    dir: stacks/api/
    config: environments/${{ inputs.environment }}/api/
    if: ${{ inputs.environment != 'local' }}  # Skip for local development
```

### Cross-Stack Dependencies

External configs work perfectly with cross-stack dependencies:

```yaml
stacks:
  - id: vpc
    dir: stacks/vpc/
    config: configs/${{ inputs.environment }}/vpc/
    
  - id: app
    dir: stacks/app/
    config: configs/${{ inputs.environment }}/app/
    params:
      VpcId: ${{ stacks.vpc.outputs.VpcId }}  # Reference to previous stack
```

## Migration from Local Configs

Converting existing pipelines to use external configs is straightforward:

### Before (Local Configs)

```yaml
stacks:
  - id: api
    dir: stacks/api/  # Uses stacks/api/samconfig.yaml
    params:
      Environment: production
```

### After (External Configs)

```yaml
stacks:
  - id: api
    dir: stacks/api/
    config: configs/production/api/  # External config directory
    params:
      Environment: production
```

The functionality remains identical, but the configuration is now generated externally.

## Best Practices

### Directory Structure

Use consistent, predictable directory structures:

```
configs/
├── {environment}/
│   ├── {stack-name}/
│   │   └── samconfig.yaml
│   └── {another-stack}/
│       └── samconfig.yaml
└── {another-environment}/
    └── ...
```

### Environment Naming

Use standard environment names:

```yaml
# Good - Directory-based (recommended)
config: configs/${{ inputs.environment }}/api/

# Good - Explicit file path
config: configs/${{ inputs.environment }}/api/samconfig.yaml

# With validation
pipeline_settings:
  inputs:
    environment:
      type: string
      default: dev
      allowed_values: [dev, staging, prod]
```

### Template Expressions

Leverage template expressions for environment-specific behavior:

```yaml
params:
  LogLevel: ${{ inputs.environment == 'prod' && 'WARN' || 'DEBUG' }}
  InstanceType: ${{ inputs.environment == 'prod' && 't3.large' || 't3.micro' }}
  EnableMonitoring: ${{ inputs.environment == 'prod' }}
  BackupRetentionDays: ${{ inputs.environment == 'prod' && '365' || '7' }}
```

## Troubleshooting

### Template File Not Found

If you see "Template file not found" errors:

1. **Check relative paths**: Ensure the generated config can find the template
2. **Verify directory structure**: Make sure stack directories exist
3. **Review working directory**: SAM CLI runs from the config file's directory

### Permission Issues

If directories cannot be created:

1. **Check write permissions** for the config path parent directories
2. **Avoid system directories** like `/etc` or `/usr` (blocked for security)
3. **Use relative paths** for better portability

### Missing Parameters

If CloudFormation validation fails:

1. **Check parameter mapping** in the pipeline definition
2. **Verify template requirements** match provided parameters
3. **Review cross-stack dependencies** are properly defined

## Examples

For complete working examples, see:

- **[Multi-Environment Example](https://github.com/dev7a/samstacks/blob/main/examples/multi-pipeline.yml)** - Single pipeline supporting multiple environments
- **[Generated Configs](https://github.com/dev7a/samstacks/tree/main/examples/configs)** - Example external configuration outputs
- **[Configuration README](https://github.com/dev7a/samstacks/blob/main/examples/configs/README.md)** - Detailed explanation of the example structure 