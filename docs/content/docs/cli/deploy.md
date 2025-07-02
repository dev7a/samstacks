---
title: "Deploy"
---

```bash
samstacks deploy <manifest-file> [OPTIONS]
```

Deploys all stacks defined in the manifest. Options include:

- `--input <name=value>` to provide values for pipeline inputs
- `--auto-delete-failed` to clean up failed stacks and changesets
- `--report-file <PATH>` to save a Markdown summary
- `--debug` for verbose logging
- `--quiet` to suppress output

Deployment reports include a console summary and optional Markdown file.
