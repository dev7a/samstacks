---
title: Documentation
next: introduction
---

Welcome to the **samstacks** documentation hub!

Samstacks helps you build and deploy modular serverless applications on AWS with ease. 

- **New to samstacks?** Dive into our [**Introduction: The Case for Samstacks**](introduction.md) to understand the why and how.
- **Ready to build?** Head over to the [**Quickstart Guide**](quickstart.md) to deploy your first multi-stack pipeline.
- **Multi-environment deployment?** Learn about [**External Configuration**](external-configs.md) to generate standalone SAM configs for GitOps workflows.
- **Need security?** Check out [**Security-Focused Output Masking**](security-masking.md) to protect sensitive data in deployment outputs.

## Quick Example

Here's a glimpse of how samstacks simplifies multi-stack deployments:

```yaml {filename="pipeline.yml"}
pipeline_name: Deploy Application
pipeline_description: Multi-stack deployment pipeline

stacks:
  - id: vpc-stack # Defines the networking infrastructure
    dir: ./infrastructure/vpc

  - id: app-stack # Defines the application logic
    dir: ./application/app
    params: # Parameters for this stack
      # Dynamically uses an output from the 'vpc-stack'
      VpcId: ${{ stacks.vpc-stack.outputs.VpcId }}
```

This declarative approach allows you to manage complex dependencies and configurations with clarity and confidence. Explore the full documentation to learn more about advanced features and best practices. 