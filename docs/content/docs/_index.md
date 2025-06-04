---
title: Documentation
next: quickstart
---

Welcome to the **samstacks** documentation. This comprehensive guide covers everything needed to implement declarative AWS SAM deployment pipelines.

## Getting Started

New to samstacks? Begin with our [Quickstart Guide](quickstart) to deploy your first multi-stack pipeline.

## Core Concepts

```yaml {filename="pipeline.yml"}
name: Deploy Application
on:
  - stack: vpc-stack
    template: infrastructure/vpc.yml
  - stack: app-stack
    template: app/template.yml
    depends_on: [vpc-stack]
    parameters:
      VpcId: ${{ stacks.vpc-stack.outputs.VpcId }}
```

samstacks implements a GitHub Actions-compatible syntax for infrastructure orchestration with these characteristics:
- **Declarative configuration** - Infrastructure as code with intent-based definitions
- **Dependency graph resolution** - Automatic topological sorting of stack deployments
- **Environment parameterization** - Configuration-driven multi-environment support
- **Dynamic parameter binding** - Runtime resolution of cross-stack dependencies 