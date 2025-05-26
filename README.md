# samstacks

**samstacks – A YAML driven pipeline of AWS SAM stacks inspired by GitHub Actions.**

[![PyPI version](https://img.shields.io/pypi/v/samstacks.svg)](https://pypi.org/project/samstacks/)
[![Build Status](https://img.shields.io/github/actions/workflow/status/dev7a/samstacks/ci.yml?branch=main)](https://github.com/dev7a/samstacks/actions/workflows/ci.yml)

Deploy a pipeline of AWS SAM stacks using a YAML manifest with GitHub Actions-style syntax.

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Examples](#examples)
- [CLI Commands](#cli-commands)
  - [Advanced Validation Features](#advanced-validation-features)
- [Manifest Reference](#manifest-reference) (Detailed)
- [Troubleshooting / FAQ](#troubleshooting--faq)
- [Development](#development)

## Installation

Install `samstacks` using pip:

```bash
# Recommended to install in a virtual environment
python -m venv .venv
source .venv/bin/activate # or .venv\Scripts\activate on Windows
pip install samstacks
```

### Prerequisites

- Python 3.12 or higher
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) installed and configured (run `sam --version` to check).
- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured with appropriate credentials (run `aws sts get-caller-identity` to check).

## Quick Start

1.  **Install `samstacks`** (see [Installation](#installation) above).

2.  **Create a manifest file** (e.g., `pipeline.yml`):

    ```yaml
    # pipeline.yml
    pipeline_name: MySimpleApp

    stacks:
      - id: backend
        dir: my_sam_app/backend/ # Path relative to this pipeline.yml
        params:
          TableName: MyTable
      
      - id: frontend
        dir: my_sam_app/frontend/
        params:
          ApiEndpoint: ${{ stacks.backend.outputs.ApiUrl }} # Example of output passing
    ```
    *(This is a minimal example. See [Manifest Reference](#manifest-reference) for all options.)*

3.  **Deploy the pipeline**:

    ```bash
    # Ensure environment variables used in the manifest (if any) are set
    # export MY_ENV_VAR=some_value

    samstacks deploy pipeline.yml
    ```

## Examples

Want a full working demo? Check out the [S3 Object Processor example](examples/simple-pipeline.yml) in the `examples/` directory. It showcases:
- S3 bucket with SQS notifications
- Lambda function processing uploaded files
- Stack output dependencies
- Templating for parameters and `samconfig.toml`
- Conditional deployment (`if`)
- Post-deployment testing scripts (`run`)

To try it (ensure AWS credentials and region are configured, and you are in the project root):
```bash
export ENVIRONMENT=dev
export PROJECT_NAME=samstacks-demo 
samstacks deploy examples/simple-pipeline.yml
```

## CLI Commands

### Deploy a Pipeline

```bash
samstacks deploy <manifest-file> [OPTIONS]
```

Deploys the stacks defined in the manifest file. SAM CLI's `sam deploy` output is streamed in real-time. 
By default, if SAM reports "No changes to deploy" for a stack, `samstacks` will automatically attempt to delete the resultant 'FAILED' changeset.

**Options**:
- `--region <region>`: Override the default AWS region.
- `--profile <profile>`: Override the default AWS CLI profile.
- `--input <name=value>` / `-i <name=value>`: Provide input values for pipeline inputs defined in `pipeline_settings.inputs`. Can be used multiple times.
- `--auto-delete-failed`: Enables proactive cleanup. Before attempting to deploy a stack, this option will:
    1. Automatically delete the stack if it's found in `ROLLBACK_COMPLETE` state.
    2. Automatically delete any pre-existing 'FAILED' changesets for the stack that have the reason "No updates are to be performed."
- `--debug`: Enable debug logging.
- `--quiet`: Suppress all output except errors.

### Validate a Manifest

```bash
samstacks validate <manifest-file>
```

Validates the manifest file with comprehensive error checking and helpful suggestions.

**What gets validated:**
- **Schema validation**: Checks for unknown fields and provides suggestions for common typos
- **Template expression validation**: Validates `${{ ... }}` syntax and stack references
- **Input validation**: Validates input definitions and CLI-provided input values against types
- **Dependency validation**: Ensures stack outputs are only referenced from previously defined stacks
- **File existence**: Verifies that stack directories exist

**Example output:**
```bash
$ samstacks validate pipeline.yml
✗ Validation error | Found 3 validation errors:
  - manifest root: Unknown field 'unknown_field' (line 1)
  - stack at index 1: Unknown field 'parameterss', did you mean 'params'? (line 12)
  - stack 'api' param 'DatabaseUrl': Stack 'database' does not exist in the pipeline. Available stacks: ['auth']
```

### Advanced Validation Features

`samstacks` includes sophisticated validation to catch common errors early and provide helpful guidance:

#### Schema Validation

The validator checks all manifest fields against known valid options and provides intelligent suggestions:

- **Root level fields**: `pipeline_name`, `pipeline_description`, `pipeline_settings`, `stacks`
- **Pipeline settings**: `stack_name_prefix`, `stack_name_suffix`, `default_region`, `default_profile`  
- **Stack fields**: `id`, `name`, `description`, `dir`, `params`, `stack_name_suffix`, `region`, `profile`, `if`, `run`

**Common typo detection:**
```yaml
stacks:
  - id: api
    parameterss:  # ❌ Typo detected: suggests 'params'
      ApiKey: value
```

#### Template Expression Validation

All `${{ ... }}` expressions are validated for correct syntax and logical consistency:

**Environment variables** (always valid):
```yaml
params:
  ApiKey: ${{ env.API_KEY }}
  Region: ${{ env.AWS_REGION || 'us-east-1' }}
```

**Pipeline inputs** (validated against input definitions):
```yaml
params:
  Environment: ${{ inputs.environment }}
  InstanceCount: ${{ inputs.instance_count }}
  # Inputs work with fallback operators
  LogLevel: ${{ inputs.log_level || env.LOG_LEVEL || 'info' }}
```

**Stack output references** (validated for existence and order):
```yaml
stacks:
  - id: database
    dir: ./database
    
  - id: api  
    dir: ./api
    params:
      # ✅ Valid: database stack defined earlier
      DatabaseUrl: ${{ stacks.database.outputs.DatabaseUrl }}
      
      # ❌ Invalid: frontend stack defined later  
      FrontendUrl: ${{ stacks.frontend.outputs.Url }}
      
      # ❌ Invalid: typo in 'stacks' (singular vs plural)
      TableName: ${{ stack.database.outputs.TableName }}
```

**Dependency order validation:**
- Stack outputs can only reference stacks defined **earlier** in the pipeline
- Forward references are caught and reported with helpful error messages
- Nonexistent stack references are detected with suggestions

#### Error Formatting and Line Numbers

Validation errors include precise line numbers when available and are formatted for easy scanning:

```bash
Found 4 validation errors:
  - manifest root: Unknown field 'typo_field' (line 2)
  - pipeline_settings: Unknown field 'invalid_setting' (line 8)  
  - stack at index 1: Unknown field 'parameterss', did you mean 'params'? (line 15)
  - stack 'api' param 'DatabaseUrl': Invalid expression 'stack.database.outputs.Url'. 
    Did you mean 'stacks.database.outputs.Url'? (note: 'stacks' is plural)
```

**Features:**
- **Line numbers**: Shown in parentheses when available for schema errors
- **Multiple errors**: All validation errors collected and shown together
- **Smart suggestions**: Typo detection with edit distance matching
- **Clear context**: Each error includes the specific location and field name

#### Validation Best Practices

1. **Run validation early**: Use `samstacks validate` before attempting deployment
2. **Fix schema errors first**: Unknown fields and typos are usually quick fixes
3. **Check stack order**: Ensure dependency stacks are defined before dependent stacks
4. **Verify expressions**: Test template expressions with actual environment variables
5. **Use meaningful stack IDs**: Clear names make dependency errors easier to understand

The validation system helps catch errors that would otherwise only surface during deployment, saving time and providing much clearer error messages than raw CloudFormation or SAM CLI errors.

---

## Manifest Reference

This tool uses a YAML manifest file (e.g., `pipeline.yml`) to define the pipeline of AWS SAM stacks to be deployed. The manifest allows for defining dependencies between stacks by piping outputs from one stack as parameters into another.

### Top-Level Structure

```yaml
pipeline_name: My SAM Application Deployment
pipeline_description: Deploys the backend and frontend for My SAM Application.

pipeline_settings: 
  # ... see below ...

stacks:
  - # ... see below ...
  - # ... see below ...
```

- **`pipeline_name`**: (String) The overall name for your deployment pipeline.
- **`pipeline_description`**: (String, Optional) A brief description of the pipeline's purpose.

### `pipeline_settings`

Global configurations that apply to all stacks in the pipeline, unless overridden at the stack level.

- **`stack_name_prefix`**: (String, Optional) A string prepended to each stack's `id` to form the CloudFormation stack name. Supports template substitution.
- **`stack_name_suffix`**: (String, Optional) A string appended after the stack `id` and any per-stack suffix. Supports template substitution.
- **`default_region`**: (String, Optional) Global AWS region for stack deployments. Can be overridden per stack or by the `--region` CLI option.
- **`default_profile`**: (String, Optional) Global AWS CLI profile for stack deployments. Can be overridden per stack or by the `--profile` CLI option.
- **`inputs`**: (Object, Optional) Define runtime inputs for the pipeline that can be provided via CLI and used in template expressions. See "Pipeline Inputs" below.

#### Pipeline Inputs

Pipeline inputs allow you to define typed, runtime parameters that can be provided via the CLI and used throughout your manifest. This feature is inspired by GitHub Actions workflow inputs and provides a clean way to parameterize deployments without relying solely on environment variables.

**Input Definition:**
```yaml
pipeline_settings:
  stack_name_prefix: ${{ inputs.environment }}-myapp
  
  inputs:
    environment:
      type: string
      default: dev
      description: "Deployment environment (dev, staging, prod)"
    
    instance_count:
      type: number
      default: 2
      description: "Number of application instances to deploy"
    
    enable_monitoring:
      type: boolean
      default: true
      description: "Enable CloudWatch monitoring and alerting"
```

**Input Properties:**
- **`type`**: (Required) The input type. Supported types: `string`, `number`, `boolean`
- **`default`**: (Optional) Default value if not provided via CLI. If no default is specified, the input is required
- **`description`**: (Optional) Human-readable description of the input's purpose

**CLI Usage:**
```bash
# Provide inputs via CLI
samstacks deploy pipeline.yml \
  --input environment=prod \
  --input instance_count=5 \
  --input enable_monitoring=false

# Short form
samstacks deploy pipeline.yml -i environment=prod -i instance_count=5

# Use defaults for unspecified inputs
samstacks deploy pipeline.yml -i environment=staging
```

**Template Usage:**
Inputs can be used in template expressions with the `${{ inputs.input_name }}` syntax:

```yaml
stacks:
  - id: api
    params:
      Environment: ${{ inputs.environment }}
      InstanceCount: ${{ inputs.instance_count }}
      MonitoringEnabled: ${{ inputs.enable_monitoring }}
      
      # Inputs work with fallback operators
      LogLevel: ${{ inputs.log_level || env.LOG_LEVEL || 'info' }}
```

**Type Validation:**
- **`string`**: Any text value
- **`number`**: Integer or decimal numbers (e.g., `42`, `3.14`)
- **`boolean`**: Accepts `true`, `false`, `yes`, `no`, `1`, `0` (case-insensitive)

**Input Precedence:**
When using inputs with fallback expressions, the evaluation order is:
1. CLI-provided input values (`--input name=value`)
2. Input default values (from manifest)
3. Environment variables (`env.VARIABLE`)
4. Stack outputs (`stacks.id.outputs.name`)
5. Literal fallbacks (`'default'`)

**Example with Complex Inputs:**
```yaml
pipeline_settings:
  stack_name_prefix: ${{ inputs.project_name }}-${{ inputs.environment }}
  
  inputs:
    project_name:
      type: string
      default: myapp
      description: "Project name for resource naming"
    
    environment:
      type: string
      description: "Target environment (required)"
    
    auto_scaling_min:
      type: number
      default: 1
      description: "Minimum number of instances"
    
    auto_scaling_max:
      type: number
      default: 10
      description: "Maximum number of instances"
    
    enable_https:
      type: boolean
      default: true
      description: "Enable HTTPS/SSL termination"

stacks:
  - id: infrastructure
    params:
      ProjectName: ${{ inputs.project_name }}
      Environment: ${{ inputs.environment }}
      MinInstances: ${{ inputs.auto_scaling_min }}
      MaxInstances: ${{ inputs.auto_scaling_max }}
      EnableHttps: ${{ inputs.enable_https }}
```

**Deployment:**
```bash
samstacks deploy pipeline.yml \
  -i environment=production \
  -i project_name=ecommerce \
  -i auto_scaling_min=3 \
  -i auto_scaling_max=20 \
  -i enable_https=true
```

This approach provides type safety, clear documentation, and a familiar interface for users coming from GitHub Actions or other CI/CD systems.

### `stacks`

A list of SAM stack definitions to be processed sequentially. Each item in the list is an object with the following keys:

- **`id`**: (String, Required) A unique identifier for the stack within the pipeline. Used for output referencing (e.g., `${{ stacks.<id>.outputs.OutputName }}`) and forms the core of the CloudFormation stack name.
- **`name`**: (String, Optional) A human-readable name for logging and display. Does not affect the deployed CloudFormation stack name. Defaults to the `id` if not provided.
- **`description`**: (String, Optional) A description for the stack.
- **`dir`**: (String, Required) Path to the directory containing the stack's `template.yaml` (or `template.yml`), `samconfig.toml` (optional), and source code. **This path is resolved relative to the location of the manifest file itself.**
- **`stack_name_suffix`**: (String, Optional) A stack-specific suffix, appended after the `id` and before any global suffix.
- **`region`**: (String, Optional) Overrides global/default AWS region for this specific stack.
- **`profile`**: (String, Optional) Overrides global/default AWS profile for this specific stack.
- **`params`**: (Object, Optional) Key-value map of parameters for `sam deploy --parameter-overrides`. Values support template substitution.
- **`if`**: (String, Optional) A condition to determine if the stack should be deployed. Supports template substitution. If omitted, the stack is always processed. See "Conditional Stack Deployment" below.
- **`run`**: (String, Optional) A shell script (can be multi-line using `|`) executed after successful deployment and output retrieval for this stack. Supports template substitution. Runs in the stack's `dir`. See "Post-deployment Scripts" below.

### Templating in Manifest Values

Several fields in the manifest support template substitution using the `${{ <expression> }}` syntax.

1.  **Environment Variables**: `${{ env.VARIABLE_NAME }}`
    *   Substitutes the value of the environment variable `VARIABLE_NAME`.
    *   If the variable is not set, it's treated as `None` (which is falsy for the `||` operator).

2.  **Pipeline Inputs**: `${{ inputs.input_name }}`
    *   Substitutes the value of the input provided via CLI (`--input input_name=value`) or the default value from the manifest.
    *   If the input is required (no default) and not provided via CLI, validation will fail.
    *   If the input has a default and is not provided via CLI, the default value is used.

3.  **Stack Outputs**: `${{ stacks.<source_stack_id>.outputs.<OutputName> }}`
    *   Substitutes the value of `<OutputName>` from the outputs of the stack identified by `<source_stack_id>` (which must have been deployed earlier in the pipeline).
    *   If the stack or the specific output is not found, it's treated as `None` (falsy for the `||` operator).

4.  **Default Value Fallback (`||`)**: The `||` operator can be used within an expression to provide a fallback value if the preceding part is falsy (e.g., an unset variable, an empty string from a resolved variable, or a non-existent stack output).
    *   Syntax: `${{ <expr1> || <expr2> || ... || 'literal_fallback' }}`
    *   It evaluates expressions from left to right and uses the first truthy (non-empty, resolved) value.
    *   **Literals**: String literals used as fallbacks **must be enclosed in single or double quotes** (e.g., `'default-value'`, `"another default"`).
    *   An empty string (`''` or `""`) from a resolved variable or as a literal fallback is considered falsy by `||`, meaning the next part of the chain will be evaluated.
    *   If all parts of a fallback chain are falsy, the expression resolves to the value of the *last* part in the chain. If the last part was an unresolvable variable/output (resolved to `None`), the final result is an empty string. If the last part was a literal empty string (`''`), the result is that empty string.

**Applicable fields for templating**: `pipeline_settings.stack_name_prefix`, `pipeline_settings.stack_name_suffix`, `stacks.params` values, `stacks.if` conditions, `stacks.run` script content, and `stacks.stack_name_suffix`.

### Execution Order and Stack Naming

- Stacks are deployed sequentially in the order they appear in the `stacks` list, provided their `if` condition (if present) evaluates to true.
- The actual CloudFormation stack name is constructed as: `[pipeline_settings.stack_name_prefix][stack.id][stack.stack_name_suffix][pipeline_settings.stack_name_suffix]`. Empty parts are omitted. 
  *(Example: `id: api`, global prefix `dev-`, stack suffix `-v2`, global suffix `-app` results in `dev-api-v2-app`)*
- This constructed name **always overrides** any `stack_name` defined in a stack's `samconfig.toml` when deploying via `samstacks`.

### SAM Deployment Parameters

When deploying each stack, `samstacks` automatically sets several SAM CLI parameters to ensure consistent and isolated deployments:

- **`--stack-name`**: Always set to the constructed stack name (as described above), overriding any `stack_name` in `samconfig.toml`.
- **`--s3-prefix`**: Automatically set to match the stack name, ensuring S3 deployment artifacts are organized by stack.
- **`--resolve-s3`**: Automatically enabled to let SAM create and manage the S3 bucket for deployment artifacts.

This means that even if your `samconfig.toml` files specify different values for these parameters, `samstacks` will override them to maintain consistency across the pipeline. Other `samconfig.toml` settings (like `capabilities`, `region`, `tags`, etc.) are still respected and can be templated with environment variables.

### `samconfig.toml` Preprocessing

`samstacks` supports preprocessing of `samconfig.toml` files found in a stack's `dir` before they are used by `sam build` and `sam deploy`.

- **Syntax**: `${{ env.VARIABLE_NAME }}` can be used within `samconfig.toml` values.
- **Behavior**: Placeholders are replaced with corresponding environment variable values. If an environment variable is not set, it will be replaced with an empty string.
- **Scope**: This templating is currently limited to `${{ env.VARIABLE_NAME }}`. It does **not** support `${{ stacks.<id>.outputs.<OutputName> }}` or the `||` fallback operator within `samconfig.toml` itself.
- **Use Case**: This allows for dynamic `samconfig.toml` settings (e.g., `s3_bucket`, `s3_prefix`, `image_repositories`, `tags`) based on the execution environment.

```toml
# Example: stacks/api/samconfig.toml
version = 0.1
[default.deploy.parameters]
  resolve_s3 = true
  s3_prefix = "${{ env.PROJECT_NAME }}/api-artifacts"
  capabilities = "CAPABILITY_IAM"
  region = "${{ env.AWS_TARGET_REGION }}" # Assumes AWS_TARGET_REGION is set
  tags = 'Project="${{ env.PROJECT_NAME || 'DefaultProject' }}" CostCenter="${{ env.COST_CENTER }}"'
```

### Conditional Stack Deployment (`if` field)

- Each stack definition can optionally include an `if: "<condition_string>"` field.
- The `<condition_string>` is processed using the templating engine (supporting `env` variables, `stack` outputs, and the `||` fallback operator).
- The stack is deployed if the final, substituted string evaluates to true (case-insensitive: `"true"`, `"1"`, `"yes"`, `"on"`).
- Otherwise, the stack is skipped, and its outputs will not be available for subsequent stacks.

### Post-deployment Scripts (`run` field)

- Each stack definition can optionally include a `run: "<shell_script_content>"` field.
- The script content is processed using the templating engine.
- It's executed after the stack has been successfully deployed and its outputs have been retrieved.
- The script runs with the stack's `dir` as its current working directory.
- A non-zero exit code from any command in the script will cause the `run` step to be considered failed, and the entire `samstacks` pipeline will halt.
- **Security Note**: Manifest files containing `run` scripts allow arbitrary shell command execution. Only use manifests from trusted sources.

### Automatic Cleanup of CloudFormation Artifacts

`samstacks` includes features to help manage CloudFormation artifacts automatically:

- **Default Behavior (Reactive Cleanup)**: If an attempt to deploy a stack with `sam deploy` results in SAM CLI reporting "No changes to deploy. Stack ... is up to date", `samstacks` will automatically try to delete the 'FAILED' changeset that SAM CLI creates in this specific situation. This helps keep the list of changesets for your stack clean.

- **`--auto-delete-failed` Flag (Proactive Cleanup)**: When you use this CLI flag, `samstacks` performs additional cleanup actions *before* attempting to deploy each stack:
    1.  **Deletes `ROLLBACK_COMPLETE` Stacks**: If a stack is found in the `ROLLBACK_COMPLETE` state (often indicating a failed initial creation with no resources provisioned), it will be deleted.
    2.  **Deletes Old "No Update" Changesets**: Any *pre-existing* 'FAILED' changesets associated with the stack that have the status reason "No updates are to be performed." will be deleted.

This combination helps maintain a cleaner CloudFormation environment, especially during iterative development.

---
## Troubleshooting / FAQ

- **Manifest Validation Errors:**
  - **Always run validation first**: Use `samstacks validate <manifest-file>` before deployment to catch errors early
  - **Schema errors**: Check for typos in field names - the validator provides suggestions for common mistakes
  - **Template expression errors**: Verify `${{ ... }}` syntax and ensure stack references use the correct format
  - **Dependency order**: Stack outputs can only reference stacks defined earlier in the pipeline
  - **Line numbers**: When available, line numbers help locate errors quickly in your manifest file
  - Ensure your YAML syntax is correct.
  - Check that all required fields (like `id` and `dir` for each stack) are present.
  - Verify that paths specified in `dir` exist relative to your manifest file.

- **Template Substitution Issues (`${{ ... }}`):**
  - **Unresolved `env` variables:** If `${{ env.MY_VAR }}` results in an empty string or an unexpected default, ensure `MY_VAR` is correctly set in your shell environment before running `samstacks`. The `||` operator can provide defaults: `${{ env.MY_VAR || 'default_value' }}`.
  - **Unresolved `inputs`:** If `${{ inputs.my_input }}` is not working:
    - Ensure the input is defined in `pipeline_settings.inputs`.
    - Check that you're providing the input via CLI: `--input my_input=value`.
    - Verify the input name matches exactly (case-sensitive).
    - For required inputs (no default), ensure you provide a value via CLI.
  - **Unresolved `stacks` outputs:** If `${{ stacks.some_stack.outputs.SomeOutput }}` is not working:
    - Confirm `some_stack` is defined *before* the current stack in the manifest.
    - Check that `some_stack` deployed successfully and actually produces `SomeOutput` (case-sensitive).
    - Ensure `some_stack` was not skipped due to an `if` condition.
  - **Literals in fallbacks**: Remember to quote string literals used with the `||` operator: `${{ env.VAR || 'this is a string' }}`.

- **`if:` Condition Not Behaving as Expected:**
  - The `if` condition evaluates the *final string value* after templating. For truthiness, it checks against `"true"`, `"1"`, `"yes"`, `"on"` (case-insensitive).
  - If you are checking an environment variable, ensure it's set to one of these values. For example, `if: ${{ env.SHOULD_DEPLOY || 'false' }}` means it deploys if `SHOULD_DEPLOY` is a truthy string, or defaults to not deploying if `SHOULD_DEPLOY` is unset/empty.

- **Stack in `ROLLBACK_COMPLETE`:**
  - This usually means the initial stack creation failed before any resources were provisioned. CloudFormation cannot update a stack in this state; it can only be deleted.
  - Use the `--auto-delete-failed` flag with `samstacks deploy` to automatically delete such stacks before retrying deployment.

- **"No updates are to be performed." FAILED Changesets Accumulating:**
  - `samstacks` automatically deletes the changeset created by SAM when it reports "No changes to deploy."
  - For older, similar FAILED changesets, use the `--auto-delete-failed` flag during deployment to clean them up proactively.

- **Path Resolution for `dir`:**
  - The `dir` specified for each stack in the manifest is always resolved *relative to the location of the manifest file itself*, not relative to where you run the `samstacks` command.

- **AWS Credentials or Region Issues:**
  - Ensure your AWS CLI is configured correctly (`aws configure` or environment variables like `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`).
  - You can specify region and profile via `pipeline_settings` in the manifest or via CLI options (`--region`, `--profile`).

---
## Development

### Setup Development Environment

1. Clone the repository:
```bash
git clone https://github.com/alessandro-bologna/samstacks.git
cd samstacks
```

2. Create a virtual environment using `uv` and install dependencies:
```bash
uv venv .venv 
# Or python -m venv .venv if you don't have uv integrated for venv creation yet
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e ".[dev]" # Installs in editable mode with dev dependencies
```

3. Run tests:
```bash
pytest
```

4. Run linting and formatting using `ruff`:
```bash
ruff format samstacks tests  # Format code
ruff check --fix --isolated samstacks tests # Lint and automatically fix issues, using only project config
# Optionally, run mypy for deeper static type checking if it's still part of your workflow:
# mypy samstacks 
```

### Project Structure

```
samstacks/
├── samstacks/           # Main package
│   ├── __init__.py
│   ├── cli.py          # Command-line interface (Click)
│   ├── core.py         # Core Pipeline and Stack classes
│   ├── templating.py   # Template processing engine
│   ├── aws_utils.py    # AWS SDK (boto3) utilities
│   └── exceptions.py   # Custom exception classes
├── tests/              # Pytest test suite
├── examples/           # Example manifest files and SAM stacks
│   ├── simple-pipeline.yml
│   └── stacks/
│       ├── processor/
│       └── storage/
├── .github/workflows/  # GitHub Actions CI workflows (if any)
├── pyproject.toml      # Project metadata, dependencies (Poetry/Hatch)
├── README.md           # This file
└── ...                 # Other config files (.gitignore, .editorconfig, etc.)
```


