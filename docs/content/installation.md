---
title: "Installation"
---

Recommended usage is via the [uv](https://docs.astral.sh/uv/) tool so you can run `samstacks` without installing:

```bash
uvx samstacks --help
uvx samstacks deploy pipeline.yml
```

To install with pip:

```bash
python -m venv .venv  # or uv venv
source .venv/bin/activate
pip install samstacks  # or uv pip install samstacks
samstacks --help
```

**Tip:** `uvx` provides the fastest way to get started with no virtual environment setup.
