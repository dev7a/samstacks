---
title: "CLI Reference"
weight: 80
next: validate
---

Complete command-line interface reference for samstacks.

## Overview

samstacks provides several commands for deploying and managing pipelines:

- **[deploy](deploy)** - Deploy a pipeline
- **[validate](validate)** - Validate pipeline syntax  
- **[delete](delete)** - Delete deployed stacks
- **[bootstrap](bootstrap)** - Initialize AWS environment

## Quick Reference

```bash
# Deploy a pipeline
uvx samstacks deploy pipeline.yml

# Deploy with inputs (multi-environment support)
uvx samstacks deploy pipeline.yml --input environment=prod

# Validate pipeline syntax
uvx samstacks validate pipeline.yml

# Delete all stacks in a pipeline
uvx samstacks delete pipeline.yml

# Delete specific environment (multi-environment support)
uvx samstacks delete pipeline.yml --input environment=staging

# Preview deletion without actually deleting
uvx samstacks delete pipeline.yml --input environment=dev --dry-run

# Bootstrap AWS environment
uvx samstacks bootstrap --region us-east-1
```

## Global Options

All commands support these global options:

| Option | Description |
|--------|-------------|
| `--help` | Show help information |
| `--verbose` | Enable verbose output |
| `--version` | Show version information |
