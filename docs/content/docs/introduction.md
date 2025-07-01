---
title: "The what and the why"
weight: 10 # To make it appear early in the sidebar if not already ordered by filename
---

## The What and the Why

Modern cloud applications are increasingly built from a collection of interconnected, modular services rather than large, monolithic systems. This architectural style—often inspired by microservices—offers significant advantages: teams can develop, deploy, and scale their components independently, leading to faster innovation, improved resilience, and better resource utilization. Each module, or "stack" in AWS SAM terminology, can focus on a specific business capability, making the overall system easier to understand, maintain, and evolve.

However, managing a distributed system composed of many small, independent stacks introduces its own set of challenges. How do you ensure that stacks are deployed in the correct order, especially when they depend on each other's outputs? How do you manage configurations consistently across multiple environments? How do you get a clear overview of your entire application's deployment status?

This is where samstacks comes in.

> [!NOTE]
> **samstacks** is a declarative infrastructure orchestration tool specifically designed for AWS SAM (Serverless Application Model) deployments. It empowers you to define and manage complex, multi-stack serverless applications with the simplicity and power of a GitHub Actions-like workflow. Instead of manually coordinating deployments or wrestling with complex scripts, you can describe your entire application pipeline—including stack dependencies, parameters, and post-deployment actions—in a single, easy-to-understand YAML manifest.

A fundamental design principle of samstacks is that _each stack should be able to be deployed independently_. This is a key difference from other IaC tools that require you to define a single, monolithic template that includes all the resources for an entire application. Run the pipeline as a whole, commit the changes, and each stack can be deployed independently, with just `sam build && sam deploy`.

## Embrace Modularity with Confidence

With samstacks, you can fully embrace the benefits of modular architecture for your AWS SAM projects:

-   **Clear Dependency Management**: Explicitly define dependencies between your stacks. Samstacks automatically determines the correct deployment order, ensuring that producer stacks are deployed before their consumers.
-   **Simplified Orchestration**: Define your entire deployment pipeline in one place. No more juggling multiple `sam deploy` commands or custom scripts.
-   **Reusable Stacks**: Design your SAM templates as reusable building blocks that can be composed into different application pipelines.
-   **Consistent Environments**: Easily manage configurations for different environments (dev, staging, prod) using templated parameters and inputs.
-   **Improved Visibility**: Gain a clear overview of your application's structure and deployment status.

## Where Samstacks Fits In

The landscape of Infrastructure as Code (IaC) tools is rich, with powerful and comprehensive solutions like [AWS Cloud Development Kit (CDK)](https://aws.amazon.com/cdk/) and [HashiCorp Terraform](https://www.terraform.io/), or [Pulumi](https://www.pulumi.com/), all offering sophisticated ways to manage complex cloud environments. These tools provide extensive capabilities for defining and provisioning a wide array of cloud resources.

It's also true that AWS CloudFormation (and by extension, AWS SAM) offers its own native features for modularity, such as Nested Stacks, Cross-Stack References (Exports/Imports), CloudFormation Modules, and the ability to create Custom Resources and private or public Resource Types. These are powerful primitives for breaking down large templates and reusing common patterns.

However, each of these native CloudFormation mechanisms can introduce its own complexities or limitations when used for orchestrating application-level pipelines of multiple, independently-deployable SAM stacks:

-   **Nested Stacks**: While useful for composing a single, larger logical unit, they can become cumbersome to manage and update, especially with deep nesting or extensive parameter passing. Debugging issues within nested stacks can also be less straightforward.
-   **Cross-Stack References (Exports/Imports)**: The immutability of exported values is a significant constraint. Once an output is exported and consumed, the producing stack cannot easily modify or remove that export, which can hinder iterative development and refactoring. This can lead to a rigid infrastructure that's difficult to evolve.
-   **CloudFormation Modules**: These are excellent for encapsulating and reusing common resource configurations *within* a single CloudFormation template. They help create reusable components at the template level but don't directly address the orchestration of multiple, distinct stack deployments with interdependencies.
-   **Custom Resources & Resource Types**: These are powerful for extending CloudFormation's capabilities to manage new or third-party resources. However, developing, testing, and maintaining custom resources (often involving Lambda functions) adds a significant layer of complexity and is generally overkill for simply managing the deployment flow of standard SAM stacks.

**Samstacks is not intended to replace these broader IaC solutions or CloudFormation's native modularity features.** Instead, it focuses on a specific, common challenge: orchestrating pipelines of multiple, largely independent AWS SAM stacks. If your team is already leveraging AWS SAM for its streamlined approach to defining serverless applications, samstacks provides a lightweight, intuitive higher-level orchestration layer.

Think of samstacks as a focused orchestrator that complements your SAM development workflow by simplifying the *flow* and *data passing* between your SAM stacks. For instance, samstacks' `${{ stacks.<id>.outputs.<name> }}` templating offers a more flexible way to consume outputs during pipeline execution compared to the compile-time rigidity of CloudFormation exports, especially easing development and refactoring cycles. It allows each SAM stack to remain a more self-contained, independently deployable unit, while samstacks manages their assembly into a cohesive application.

It's ideal when:

-   You primarily use AWS SAM for defining your serverless components.
-   You need a simple, declarative way to manage dependencies and deployment order for multiple SAM stacks, avoiding the operational complexities of deeply nested stacks or the inflexibility of immutable exports for dynamic application composition.
-   You prefer a GitHub Actions-like syntax for pipeline definition without wanting to adopt a more comprehensive IaC tool for this specific orchestration task.
-   You want to maintain the simplicity of SAM while gaining better control over multi-stack deployments.

Samstacks helps bridge the gap between individual SAM stack deployments and a fully orchestrated application, keeping the focus on SAM's strengths for serverless development. 