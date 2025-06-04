---
title: "Manifest Reference"
---

A pipeline is described in a YAML file. Key fields include:

```yaml
pipeline_name: My SAM Application Deployment
pipeline_description: Description of the pipeline
summary: |-
  Optional post deployment summary shown in console
pipeline_settings:
  stack_name_prefix: prefix-
  default_region: us-east-1
  inputs:
    environment:
      type: string
stacks:
  - id: backend
    dir: backend
```

See the README for full details on all fields and templating rules.
