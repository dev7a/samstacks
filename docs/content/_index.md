---
title: samstacks
toc: false
showTitle: false
---

<div class="hero-section" id="hero-parallax">
  <div class="hero-content">
    <div class="hero-cta">
      <a href="/samstacks/docs/quickstart" class="hero-button hero-button-primary">Get Started</a>
      <a href="/samstacks/docs" class="hero-button hero-button-secondary">Documentation</a>
    </div>
    <p class="hero-description">Declarative infrastructure orchestration for AWS SAM deployments.</p>
  </div>
</div>


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
- **Security-focused output masking** - Protect sensitive data like AWS account IDs and API endpoints
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
      SubnetIds: ${{ stacks.vpc-stack.outputs.Private
```
> [!NOTE]
> This is a work in progress, and the implementation is subject to change.

For more information, visit the [documentation]({{< relref "docs" >}}). 

<script src="/samstacks/js/parallax.js"></script>
