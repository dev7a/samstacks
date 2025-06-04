---
title: "Quick Start"
---

Create a manifest file `pipeline.yml`:

```yaml
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

Deploy the pipeline:

```bash
uvx samstacks deploy pipeline.yml
# or if installed
samstacks deploy pipeline.yml
```

See the [Manifest Reference](/manifest-reference/) for more options.
