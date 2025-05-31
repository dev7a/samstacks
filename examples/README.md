# Example `samstacks` Pipelines

This directory contains example `samstacks` pipeline manifest files to demonstrate various features.

## Prerequisites

Before running these examples, ensure you have:
1.  `samstacks` installed (`pip install samstacks`).
2.  AWS SAM CLI installed and configured.
3.  AWS CLI installed and configured with appropriate credentials and a default region. Region and profile configuration is managed through the `pipeline.yml` manifest using `default_region` and `default_profile` settings.

## `simple-pipeline.yml`

This is the main example pipeline, showcasing:
- **SAM Configuration Management**: Centralized SAM CLI configuration through `pipeline.yml`
- **S3 bucket with SQS notifications**: Lambda function processing uploaded files
- **Stack output dependencies**: Passing outputs between stacks
- **Template expressions**: Environment variables with fallbacks
- **Conditional deployment** (`if`): Optional stack deployment
- **Post-deployment testing scripts** (`run`): Automated testing after deployment

**Key Features Demonstrated:**
- `default_sam_config` for global SAM CLI settings (capabilities, region, etc.)
- Automatic generation of `samconfig.yaml` files in each stack directory
- Template expressions with environment variables and fallbacks
- Cross-stack parameter passing using stack outputs

To run this example (ensure AWS credentials and region are configured):

```bash
# Set environment variable for deployment environment
export ENVIRONMENT=dev  # or staging, prod, etc.

samstacks deploy examples/simple-pipeline.yml --auto-delete-failed
```

**What happens during deployment:**
1. `samstacks` generates `samconfig.yaml` files in each stack directory
2. Existing `samconfig.toml` files are automatically backed up to `.toml.bak`
3. SAM CLI uses the generated configurations for deployment
4. Stack outputs are passed between stacks automatically
5. Post-deployment script tests the pipeline by uploading a file

**Generated Configuration Example:**
After deployment, check `stacks/processor/samconfig.yaml` to see the generated configuration:
```yaml
version: 0.1
default:
  deploy:
    parameters:
      capabilities: CAPABILITY_IAM
      confirm_changeset: false
      resolve_s3: true
      region: us-east-1
      stack_name: samstacks-demo-dev-processor
      s3_prefix: samstacks-demo-dev-processor
      parameter_overrides: MessageRetentionPeriod=1209600 ReceiveMessageWaitTimeSeconds=20
```

**Testing SAM Configuration Management:**

After running the pipeline, you can test the individual stack deployment feature:

```bash
# Navigate to a stack directory
cd stacks/processor

# Deploy the individual stack using SAM CLI
# The generated samconfig.yaml contains all necessary configuration
sam deploy

# Check the generated configuration
cat samconfig.yaml

# Verify backup files were created (if any existed before)
ls -la *.bak
```

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
