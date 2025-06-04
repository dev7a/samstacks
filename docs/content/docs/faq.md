---
title: "FAQ"
weight: 6
prev: cli
---

Frequently asked questions about samstacks.

## General

### What is samstacks?

samstacks is a YAML-driven pipeline tool for deploying AWS SAM stacks. It allows you to define a sequence of stacks in a single manifest using a GitHub Actions-style syntax, with automatic dependency resolution and parameter passing.

### How is samstacks different from AWS SAM?

While AWS SAM deploys individual stacks, samstacks orchestrates multiple SAM stacks as a pipeline:

- **Multi-stack coordination** - Deploy related stacks in the correct order
- **Dependency management** - Automatic resolution of stack dependencies  
- **Parameter passing** - Use outputs from one stack as inputs to another
- **Conditional deployment** - Deploy stacks based on expressions
- **Pipeline-level configuration** - Shared settings across all stacks

## Installation & Setup

### Do I need to install samstacks locally?

No! The quickest way to use samstacks is with `uvx`:

```bash
uvx samstacks deploy pipeline.yml
```

This runs samstacks without any local installation or virtual environment setup.

### What are the prerequisites?

- **Python 3.8+** - For running samstacks
- **AWS CLI** - Configured with appropriate permissions
- **SAM CLI** - For template validation and deployment

### How do I configure AWS credentials?

samstacks uses the same AWS credentials as the AWS CLI and SAM CLI. Configure them using:

```bash
aws configure
# or
export AWS_PROFILE=my-profile
```

## Pipeline Configuration

### Can I use existing SAM templates?

Yes! samstacks works with existing SAM templates. Just point the `dir` field to the directory containing your `template.yml` file.

### How do I pass outputs between stacks?

Use the expression syntax to reference stack outputs:

```yaml
stacks:
  - id: network
    dir: ./network
    
  - id: app
    dir: ./app
    params:
      VpcId: ${{ stacks.network.outputs.VpcId }}
```

### Can I deploy only certain stacks?

Yes, use conditional expressions:

```yaml
stacks:
  - id: optional-stack
    dir: ./optional
    if: ${{ env.DEPLOY_OPTIONAL == 'true' }}
```

## Troubleshooting

### Stack deployment failed, what now?

1. **Check the error message** - samstacks shows detailed CloudFormation errors
2. **Review stack parameters** - Ensure all required parameters are provided
3. **Verify dependencies** - Make sure dependent stacks deployed successfully
4. **Check AWS permissions** - Ensure your credentials have the necessary permissions

### How do I debug expression evaluation?

Use the `--verbose` flag to see how expressions are evaluated:

```bash
uvx samstacks deploy pipeline.yml --verbose
```

### Stack is stuck in rollback state

If a CloudFormation stack is in a failed state, you may need to:

1. **Delete the stack** in the AWS Console
2. **Fix the template** or parameters causing the issue
3. **Redeploy** the pipeline

## Advanced Usage

### Can I use custom SAM configurations per stack?

Yes, define `sam_config` at the stack level:

```yaml
stacks:
  - id: my-stack
    dir: ./my-stack
    sam_config:
      version: 0.1
      default:
        deploy:
          parameters:
            capabilities: CAPABILITY_NAMED_IAM
```

### How do I run commands after deployment?

Use the `run` field:

```yaml
stacks:
  - id: api
    dir: ./api
    run: |-
      echo "API URL: ${{ stacks.api.outputs.ApiUrl }}"
      curl -f "${{ stacks.api.outputs.ApiUrl }}/health"
```

### Can I use samstacks in CI/CD?

Absolutely! samstacks works great in CI/CD pipelines. Use `uvx` for the simplest setup:

```yaml
# GitHub Actions example
- name: Deploy SAM stacks
  run: uvx samstacks deploy pipeline.yml
```

## Getting Help

Still have questions? Here are additional resources:

- [GitHub Repository](https://github.com/dev7a/samstacks) - Source code and issues
- [GitHub Discussions](https://github.com/dev7a/samstacks/discussions) - Community support
- [Report Issues](https://github.com/dev7a/samstacks/issues) - Bug reports and feature requests
