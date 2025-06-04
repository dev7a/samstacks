---
title: samstacks
toc: false
---

**samstacks** is a declarative infrastructure orchestration tool for AWS SAM deployments. It enables teams to define multi-stack deployment pipelines using familiar GitHub Actions syntax with automatic dependency resolution.

## Get Started

{{< cards >}}
  {{< card link="docs" title="Documentation" icon="book-open" >}}
  {{< card link="docs/quickstart" title="Quickstart" icon="play" >}}
  {{< card link="docs/examples" title="Examples" icon="code" >}}
{{< /cards >}}

## Key Capabilities

- **Declarative pipeline configuration** - Define deployment sequences using YAML manifests
- **GitHub Actions compatibility** - Leverage familiar workflow syntax and expressions
- **Native AWS SAM integration** - First-class support for SAM templates and configurations  
- **Intelligent dependency resolution** - Automatic stack ordering based on output dependencies
- **Multi-environment deployments** - Parameterized configuration for development lifecycle

## Quick Example

```yaml
pipeline_name: Deploy Application
pipeline_description: Multi-stack deployment pipeline

stacks:
  - id: vpc-stack
    dir: ./infrastructure/vpc
    
  - id: app-stack
    dir: ./application/app
    params:
      VpcId: ${{ stacks.vpc-stack.outputs.VpcId }}
      SubnetIds: ${{ stacks.vpc-stack.outputs.PrivateSubnetIds }}
```

For more information, visit the [documentation](/docs).
