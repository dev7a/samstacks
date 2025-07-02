# samstacks

**Declarative infrastructure orchestration for AWS SAM deployments.**

[![PyPI version](https://img.shields.io/pypi/v/samstacks.svg)](https://pypi.org/project/samstacks/)
[![Build Status](https://img.shields.io/github/actions/workflow/status/dev7a/samstacks/ci.yml?branch=main)](https://github.com/dev7a/samstacks/actions/workflows/ci.yml)
[![Documentation](https://img.shields.io/badge/docs-website-blue)](https://dev7a.github.io/samstacks/)

Deploy multi-stack AWS SAM applications using YAML pipelines with GitHub Actions-style syntax and automatic dependency resolution.

> [!WARNING]
> **Alpha Software Notice**: samstacks is currently in alpha development. While functional and actively used, the API and configuration format may change between versions. We welcome feedback, bug reports, and contributions as we work toward a stable release.

## Why samstacks?

Managing multiple related AWS SAM stacks can be complex when you need to:
- Deploy stacks in the correct order based on dependencies
- Pass outputs from one stack as parameters to another
- Manage environment-specific configurations
- Coordinate deployments across teams

**samstacks** solves this by letting you define your entire multi-stack deployment as a single YAML pipeline.

## Quick Start

**1. Install and run immediately:**
```bash
uvx samstacks deploy pipeline.yml
```
> No installation required with [uvx](https://docs.astral.sh/uv/)!

**2. Create a pipeline manifest:**
```yaml
# pipeline.yml
pipeline_name: E-commerce Platform
pipeline_description: Backend API with user authentication

stacks:
  - id: auth-service
    dir: ./services/auth
    
  - id: product-api
    dir: ./services/products
    params:
      AuthServiceUrl: ${{ stacks.auth-service.outputs.ServiceUrl }}
      DatabaseUrl: ${{ env.DATABASE_URL }}
```

**3. Deploy your infrastructure:**
```bash
uvx samstacks deploy pipeline.yml
```

samstacks automatically:
- Analyzes dependencies between stacks
- Deploys `auth-service` first, then `product-api`
- Passes the auth service URL to the product API
- Provides detailed deployment reporting

## Key Features

- **Declarative pipeline configuration** - Define deployment sequences using YAML manifests
- **GitHub Actions compatibility** - Leverage familiar `${{ env.VAR }}` syntax and expressions
- **Intelligent dependency resolution** - Automatic stack ordering based on output dependencies
- **Multi-environment support** - Environment-specific parameters and conditional deployment
- **External configuration generation** - Generate standalone SAM config files for GitOps workflows and direct SAM CLI usage
- **Security-focused output masking** - Automatically mask sensitive data like AWS account IDs, API endpoints, and database URLs in deployment outputs
- **Comprehensive validation** - Catch configuration errors before deployment
- **Native AWS SAM integration** - Works with existing SAM templates and configurations

## External Configuration Support

samstacks can generate external SAM configuration files that work independently with the SAM CLI, enabling powerful multi-environment workflows while maintaining the "one directory, one stack" philosophy.

### Single Pipeline, Multiple Environments

Define one pipeline that generates environment-specific configurations:

```yaml
# multi-env-pipeline.yml
pipeline_name: Multi-Environment API
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
```

### Generated Directory Structure

```
project/
├── pipeline.yml                           # Single pipeline definition
├── stacks/
│   └── api/
│       ├── template.yaml                  # Your SAM template
│       └── src/                           # Application code
└── configs/                               # Generated external configs
    ├── dev/
    │   └── api/
    │       └── samconfig.yaml             # Dev-specific config
    ├── staging/
    │   └── api/
    │       └── samconfig.yaml             # Staging-specific config
    └── prod/
        └── api/
            └── samconfig.yaml             # Production-specific config
```

### Deploy to Multiple Environments

```bash
# Deploy to different environments using samstacks
samstacks deploy pipeline.yml --input environment=dev
samstacks deploy pipeline.yml --input environment=staging
samstacks deploy pipeline.yml --input environment=prod

# Or use SAM CLI directly with generated configs
cd configs/dev/api && sam deploy
cd configs/staging/api && sam deploy
cd configs/prod/api && sam deploy
```

### Delete Environment-Specific Deployments

```bash
# Delete specific environments using samstacks
samstacks delete pipeline.yml --input environment=dev
samstacks delete pipeline.yml --input environment=staging --dry-run

# Or use SAM CLI directly with external configs
cd configs/dev/api && sam delete --no-prompts
cd configs/staging/api && sam delete --no-prompts
```

### Benefits of External Configurations

- **Single Source of Truth**: One pipeline supports all environments
- **Standalone Configs**: Generated configs work independently with SAM CLI
- **Clean Repositories**: No generated files mixed with source code
- **GitOps Ready**: Commit generated configs for reproducible deployments
- **Direct SAM CLI Usage**: Skip orchestrator for quick deployments
- **Team Collaboration**: Different teams can use SAM CLI directly

## Installation Options

**Recommended** - Run without installing:
```bash
uvx samstacks --help
uvx samstacks deploy pipeline.yml
```

**Traditional installation:**
```bash
pip install samstacks
samstacks --help
```

## Common Use Cases

### Cross-Stack Dependencies
```yaml
stacks:
  - id: vpc-stack
    dir: ./infrastructure/vpc
    
  - id: database-stack  
    dir: ./infrastructure/database
    params:
      VpcId: ${{ stacks.vpc-stack.outputs.VpcId }}
      SubnetIds: ${{ stacks.vpc-stack.outputs.PrivateSubnetIds }}
      
  - id: api-stack
    dir: ./application/api
    params:
      DatabaseUrl: ${{ stacks.database-stack.outputs.ConnectionString }}
```

### Environment-Specific Deployment
```yaml
pipeline_settings:
  stack_name_prefix: ${{ env.ENVIRONMENT }}-myapp
  inputs:
    environment:
      type: string
      default: dev

stacks:
  - id: app-stack
    dir: ./app
    if: ${{ inputs.environment != 'local' }}
    params:
      Environment: ${{ inputs.environment }}
      InstanceType: ${{ inputs.environment == 'prod' && 't3.large' || 't3.micro' }}
```

### Security-Focused Output Masking
```yaml
pipeline_settings:
  # Enable comprehensive output masking for security (all categories enabled by default)
  output_masking:
    enabled: true

stacks:
  - id: lambda-stack
    dir: ./lambda
```

**Before masking:**
```
ProcessorFunctionArn: arn:aws:lambda:us-west-2:123456789012:function:my-function
```

**After masking:**
```
ProcessorFunctionArn: arn:aws:lambda:us-west-2:************:function:my-function
```

This feature protects sensitive data including AWS account IDs, API endpoints, database URLs, load balancer DNS, CloudFront domains, IP addresses, and custom patterns in:
- Console deployment outputs
- Markdown deployment reports
- Pipeline summaries
- CI/CD logs and artifacts

## CLI Commands

### Deploy Pipeline
```bash
# Deploy with default inputs
samstacks deploy pipeline.yml

# Deploy to specific environment
samstacks deploy pipeline.yml --input environment=prod
```

### Validate Configuration
```bash
samstacks validate pipeline.yml
```

### Delete All Stacks
```bash
# Delete with default inputs
samstacks delete pipeline.yml

# Delete specific environment (supports multi-environment pipelines)
samstacks delete pipeline.yml --input environment=staging

# Preview what would be deleted
samstacks delete pipeline.yml --input environment=dev --dry-run
```

### Bootstrap Existing Project
```bash
samstacks bootstrap ./my-sam-project
```

## Prerequisites

- **Python 3.8+** - Check with `python --version`
- **AWS CLI** - Configured with appropriate permissions (`aws sts get-caller-identity`)
- **SAM CLI** - For template validation and deployment (`sam --version`)

## Real-World Examples

Check out our [complete examples](https://github.com/dev7a/samstacks/tree/main/examples) showcasing:

### Basic Multi-Stack Example
- S3 bucket notifications to SQS
- Lambda processing with dependencies  
- Cross-stack parameter passing
- Conditional deployment logic
- Post-deployment automation

```bash
git clone https://github.com/dev7a/samstacks.git
cd samstacks/examples
uvx samstacks deploy pipeline.yml
```

### Multi-Environment External Config Example
- Single pipeline for multiple environments
- External SAM configuration generation
- Direct SAM CLI compatibility
- GitOps-ready workflow

```bash
cd samstacks/examples
uvx samstacks deploy multi-pipeline.yml --input environment=dev
# Or deploy with SAM CLI directly:
cd configs/dev/processor && sam deploy
```

All examples include comprehensive security masking enabled by default.

## Documentation

**[Complete Documentation](https://dev7a.github.io/samstacks/)**

Our comprehensive documentation includes:

- **[Quickstart Guide](https://dev7a.github.io/samstacks/docs/quickstart/)** - Deploy your first pipeline in 5 minutes
- **[Manifest Reference](https://dev7a.github.io/samstacks/docs/manifest-reference/)** - Complete configuration guide with examples
- **[CLI Reference](https://dev7a.github.io/samstacks/docs/cli/)** - All command-line options and usage
- **[Examples](https://dev7a.github.io/samstacks/docs/examples/)** - Real-world pipeline configurations
- **[FAQ](https://dev7a.github.io/samstacks/docs/faq/)** - Common questions and troubleshooting

## Contributing

Contributions are welcome! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.