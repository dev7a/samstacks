---
title: "Quickstart"
weight: 1
next: installation
---

Deploy your first multi-stack pipeline with samstacks in under 5 minutes.

## Create Your Pipeline

Create a manifest file `pipeline.yml`:

```yaml {filename="pipeline.yml"}
pipeline_name: My SAM Application Deployment
pipeline_description: Deploys the backend and frontend for My SAM Application.

pipeline_settings:
  default_sam_config:
    version: 0.1
    default:
      deploy:
        parameters:
          capabilities: CAPABILITY_IAM
          confirm_changeset: false

stacks:
  - id: backend
    dir: my_sam_app/backend/
    params:
      TableName: ${{ env.TABLE_NAME || 'MyTable' }}
  - id: frontend
    dir: my_sam_app/frontend/
    params:
      ApiEndpoint: ${{ stacks.backend.outputs.ApiUrl }}
```

## Deploy Your Pipeline

```bash
# Using uvx (recommended)
uvx samstacks deploy pipeline.yml

# Or if installed globally
samstacks deploy pipeline.yml
```

## Execution Flow

samstacks will:
1. **Dependency analysis** - Construct deployment dependency graph
2. **Backend stack deployment** - Provision API and database infrastructure
3. **Frontend stack deployment** - Resolve backend outputs as input parameters
4. **Status reporting** - Display deployment results and stack outputs

## Next Steps

- [Installation Guide](installation) - Install samstacks locally
- [Manifest Reference](manifest-reference) - Complete configuration options
- [Examples](examples) - Real-world use cases
