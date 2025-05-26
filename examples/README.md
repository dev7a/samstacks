# Example `samstacks` Pipelines

This directory contains example `samstacks` pipeline manifest files to demonstrate various features.

## Prerequisites

Before running these examples, ensure you have:
1.  `samstacks` installed (`pip install samstacks`).
2.  AWS SAM CLI installed and configured.
3.  AWS CLI installed and configured with appropriate credentials and a default region, or be prepared to specify `--region` and `--profile` with the `samstacks deploy` command.

## `simple-pipeline.yml`

This is the original example pipeline, showcasing:
- S3 bucket with SQS notifications.
- Lambda function processing uploaded files.
- Stack output dependencies.
- Templating for parameters and `samconfig.toml`.
- Conditional deployment (`if`).
- Post-deployment testing scripts (`run`).

To run this example (ensure AWS credentials and region are configured):

```bash
# Set any environment variables used by the manifest if not using defaults
# export ENVIRONMENT=dev # (Example, if your manifest uses ${{ env.ENVIRONMENT }})
# export PROJECT_NAME=my-samstacks-project #(Example)

samstacks deploy examples/simple-pipeline.yml --auto-delete-failed
```

Refer to the main project `README.md` for more details on the features used in this example. 

## `inputs-pipeline.yml`

This example demonstrates the **Pipeline Inputs** feature. It defines inputs for deployment environment, message retention, and conditional stack deployment.

The stacks (`stacks/processor/` and `stacks/storage/`) are designed to create a basic S3 object processing setup (S3 bucket, SQS queue, Lambda function).

**Note:** The `run` script in the `storage` stack attempts to upload a file to the created S3 bucket using `aws s3 cp`. This command will only succeed if your AWS CLI is configured with credentials that have permission to write to the target S3 bucket.

### Running the Integration Tests

These test cases mirror the ones used to verify the inputs feature during development.

**Test Case 1: Deployment with Default Input Values**

This test checks if the pipeline deploys correctly using the default values specified for inputs in the manifest.

```bash
samstacks deploy examples/inputs-pipeline.yml --auto-delete-failed
```

*   **Expected Behavior:**
    *   Stacks named like `samstacks-demo-dev-processor` and `samstacks-demo-dev-storage`.
    *   The `processor` stack uses a `MessageRetentionPeriod` of `1209600`.
    *   The `storage` stack is deployed.
    *   The `run` script in the `storage` stack echoes messages related to the "dev" environment.

**Test Case 2: Override Inputs via CLI**

This test checks if CLI-provided inputs correctly override manifest defaults.

```bash
samstacks deploy examples/inputs-pipeline.yml -i deployment_env=prod -i message_retention_override=604800 --auto-delete-failed
```

*   **Expected Behavior:**
    *   Stacks named like `samstacks-demo-prod-processor` and `samstacks-demo-prod-storage`.
    *   The `processor` stack uses a `MessageRetentionPeriod` of `604800`.
    *   The `storage` stack is deployed.
    *   The `run` script in the `storage` stack echoes messages related to the "prod" environment.

**Test Case 3: Skip Stack using Boolean Input**

This test checks if a boolean input can conditionally skip a stack.

```bash
samstacks deploy examples/inputs-pipeline.yml -i deployment_env=test -i deploy_storage_stack=false --auto-delete-failed
```

*   **Expected Behavior:**
    *   The `processor` stack is named `samstacks-demo-test-processor`.
    *   The `storage` stack is skipped (logs should indicate "Skipping stack 'storage' | Due to 'if' condition.").

**Test Case 4: Required Input Missing (Requires Manifest Modification)**

This test verifies that `samstacks` correctly identifies and reports missing required inputs.

1.  **Modify `examples/inputs-pipeline.yml`:**
    Temporarily remove or comment out the `default: dev` line under the `deployment_env` input definition:
    ```yaml
    # ...
    inputs:
      deployment_env:
        type: string
        # default: dev  # <--- Comment this out
        description: "Target deployment environment (e.g., dev, staging, prod)"
    # ...
    ```

2.  **Run the command:**
    ```bash
    samstacks deploy examples/inputs-pipeline.yml --auto-delete-failed
    ```

3.  **Expected Behavior:**
    *   The command should fail with a `Pipeline error` (or `ManifestError`).
    *   The error message should indicate: `Required input 'deployment_env' not provided via CLI and has no default value.`

4.  **Important:** Remember to revert the change to `examples/inputs-pipeline.yml` (uncomment the `default: dev` line) after this test.
