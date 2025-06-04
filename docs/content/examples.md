---
title: "Examples"
---

The [`examples/`](https://github.com/dev7a/samstacks/tree/main/examples) directory contains a comprehensive pipeline manifest demonstrating all features. It includes:

- S3 bucket notifications to SQS
- Lambda processing of uploaded files
- Stack output dependencies
- Centralized SAM configuration
- Conditional deployment with `if`
- Post-deployment scripts via `run`
- Post-deployment summary output
- Mathematical and logical expressions

Try it with:

```bash
uvx samstacks deploy examples/pipeline.yml
# or if installed
samstacks deploy examples/pipeline.yml
```
