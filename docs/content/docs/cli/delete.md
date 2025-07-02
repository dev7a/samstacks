---
title: "Delete"
weight: 3
next: bootstrap
---

```bash
samstacks delete <manifest-file> [OPTIONS]
```

Deletes all stacks defined in the manifest in reverse dependency order. Useful options:

- `--input <name=value>` to provide pipeline input values for multi-environment deployments
- `--no-prompts` to skip confirmation
- `--dry-run` to preview deletions

## Multi-Environment Support

The delete command supports the same `--input` parameter as deploy for multi-environment pipelines:

```bash
# Delete dev environment
samstacks delete pipeline.yml --input environment=dev

# Delete production environment  
samstacks delete pipeline.yml --input environment=prod
```

For pipelines using external configurations, the delete command will:
- Resolve template expressions in config paths based on input values
- Use the appropriate external config files with `sam delete --config-file`
- Fall back to local `samconfig.yaml` files when external configs aren't found
