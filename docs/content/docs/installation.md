---
title: "Installation"
weight: 2
prev: quickstart
next: examples
---

There are several ways to install and use samstacks. Choose the method that works best for your workflow.

## Quick Run (Recommended)

The fastest way to get started is with [uvx](https://docs.astral.sh/uv/), which runs samstacks without installing:

```bash
# Check if samstacks is working
uvx samstacks --help

# Deploy a pipeline directly
uvx samstacks deploy pipeline.yml
```

{{< callout type="info" >}}
**No setup required!** `uvx` automatically manages Python environments and dependencies.
{{< /callout >}}

## Local Installation

For regular use, install samstacks in a virtual environment:

### With uv (Recommended)

```bash
# Create virtual environment
uv venv

# Activate and install
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install samstacks

# Verify installation
samstacks --help
```

### With pip

```bash
# Create virtual environment
python -m venv .venv

# Activate and install
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install samstacks

# Verify installation
samstacks --help
```

## Prerequisites

- **Python 3.8+** - Check with `python --version`
- **AWS CLI** - Configured with appropriate permissions
- **SAM CLI** - For template validation and deployment

## Next Steps

- [Quickstart Guide](quickstart) - Deploy your first pipeline
- [Examples](examples) - See real-world configurations
