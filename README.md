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
  - [Deploy a Pipeline](#deploy-a-pipeline)
  - [Delete a Pipeline](#delete-a-pipeline)
  - [Validate a Manifest](#validate-a-manifest-without-deploying)
  - [Bootstrap an Existing Project](#bootstrap-an-existing-project)
  - [Advanced Validation Features](#advanced-validation-features)
- [Manifest Reference](#manifest-reference) (Detailed)
  - [Pipeline Inputs](#pipeline-inputs)
  - [SAM Configuration Management](#sam-configuration-management)
- [Troubleshooting / FAQ](#troubleshooting--faq)
- [Development](#development)

### Prerequisites

- Python 3.12 or higher
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) installed and configured (run `sam --version` to check).
- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured with appropriate credentials (run `aws sts get-caller-identity` to check).
- [uv](https://docs.astral.sh/uv/) (recommended) to run `samstacks` without installation via `uvx`

## Installation

**Recommended**: Run directly without installing using [uv](https://docs.astral.sh/uv/):

```bash
# No installation required! Just run it directly
uvx samstacks --help
uvx samstacks deploy pipeline.yml
```

Or install traditionally with pip:

```bash
# Install in a virtual environment
python -m venv .venv          # or uv venv
source .venv/bin/activate     
pip install samstacks          # or uv pip install samstacks
samstacks --help
```

> **💡 Tip**: Using `uvx` is the fastest way to get started - no virtual environment setup or package management needed!


## Quick Start

1.  **Create a manifest file** (e.g., `pipeline.yml`):

    ```yaml
    # pipeline.yml
    pipeline_name: My SAM Application Deployment
    pipeline_description: Deploys the backend and frontend for My SAM Application.

    pipeline_settings:
      # Optional: Define SAM CLI configuration for all stacks
      default_sam_config:
        version: 0.1
        default:
          deploy:
            parameters:
              capabilities: CAPABILITY_IAM
              confirm_changeset: false

    stacks:
      - id: backend
        dir: my_sam_app/backend/ # Path relative to this pipeline.yml file
        params:
          TableName: ${{ env.TABLE_NAME || 'MyTable' }} # use environment variables or fallback to default
      
      - id: frontend
        dir: my_sam_app/frontend/
        params:
          ApiEndpoint: ${{ stacks.backend.outputs.ApiUrl }} # Example of output passing to another stack
    ```
    *(This is a minimal example. See [Manifest Reference](#manifest-reference) for all options, including [SAM Configuration Management](#sam-configuration-management).)*

2.  **Deploy the pipeline**:

    ```bash
    # Ensure environment variables used in the manifest (if any) are set
    # export MY_ENV_VAR=some_value

    # Run directly without installing
    uvx samstacks deploy pipeline.yml
    
    # Or if you've installed it
    samstacks deploy pipeline.yml
    ```

## Examples

Want a full working demo? Check out the [comprehensive pipeline example](https://github.com/dev7a/samstacks/blob/main/examples/pipeline.yml) in the [`examples/`](https://github.com/dev7a/samstacks/tree/main/examples) directory. This "kitchen sink" example showcases:
- S3 bucket with SQS notifications
- Lambda function processing uploaded files
- Stack output dependencies
- SAM configuration management with centralized capabilities
- Conditional deployment (`if`)
- Post-deployment testing scripts (`run`)
- **Mathematical expressions for capacity planning** (e.g., `${{ inputs.retention_days * 86400 }}`)
- **Logical expressions for environment-specific configuration** (e.g., `${{ inputs.environment == 'prod' && 30 || 10 }}`)
- **Type conversion with environment variables** (e.g., `${{ int(env.BATCH_SIZE || '10') }}`)
- **Complex conditional deployment logic** based on environment and user count

To try it (ensure AWS credentials and region are configured, and you are in the project root):
```bash
# Run directly without installing
uvx samstacks deploy examples/pipeline.yml

# Or if you've installed it
samstacks deploy examples/pipeline.yml
```

## CLI Commands

### Deploy a Pipeline

```bash
samstacks deploy <manifest-file> [OPTIONS]
```

Deploys the stacks defined in the manifest file. SAM CLI's `sam deploy` output is streamed in real-time. 
By default, if SAM reports "No changes to deploy" for a stack, `samstacks` will automatically attempt to delete the resultant 'FAILED' changeset.

**Options**:
- `--input <name=value>` / `-i <name=value>`: Provide input values for pipeline inputs defined in `pipeline_settings.inputs`. Can be used multiple times.
- `--auto-delete-failed`: Enables proactive cleanup. Before attempting to deploy a stack, this option will:
    - Automatically delete the stack if it's found in `ROLLBACK_COMPLETE` state.
    - Automatically delete any pre-existing 'FAILED' changesets for the stack that have the reason "No updates are to be performed."
- `--debug`: Enable debug logging.
- `--quiet`: Suppress all output except errors.

**Note**: Region and profile configuration is now managed exclusively through the `pipeline.yml` manifest using `default_region`, `default_profile`, and per-stack overrides. CLI flags for `--region` and `--profile` have been removed to ensure deployment consistency and prevent configuration conflicts.

### Delete a Pipeline

```bash
samstacks delete <manifest-file> [OPTIONS]
```

Deletes all stacks in a pipeline in reverse dependency order (consumers first, then producers) using `sam delete`. This ensures that dependent stacks are removed before their dependencies, preventing CloudFormation deletion failures.

**Options**:
- `--no-prompts`: Skip confirmation prompts (useful for automation and CI/CD pipelines)
- `--dry-run`: Show what would be deleted without actually deleting anything

**Default Behavior**:
- Interactive confirmation is required before deletion proceeds
- Stacks are deleted in reverse order from how they appear in the pipeline
- Each stack deletion is attempted even if previous deletions fail
- A summary is provided at the end showing which stacks were successfully deleted

**Examples**:
```bash
# Interactive deletion with confirmation prompts
samstacks delete pipeline.yml

# Automated deletion for CI/CD (no prompts)
samstacks delete pipeline.yml --no-prompts

# Preview what would be deleted without actually deleting
samstacks delete pipeline.yml --dry-run
```

### Validate a Manifest (without deploying)

```bash
samstacks validate <manifest-file>
```

Validates the manifest file with comprehensive error checking and helpful suggestions.

**What gets validated:**
- **Schema validation**: Checks for unknown fields, valid data types (primarily via Pydantic for overall structure), and provides suggestions for common typos.
- **Template expression validation**: Validates `${{ ... }}` syntax and stack references (including within `default_sam_config` and `sam_config_overrides`).
- **Input validation**: Validates input definitions and CLI-provided input values against types.
- **Dependency validation**: Ensures stack outputs are only referenced from previously defined stacks.
- **File existence**: Verifies that stack directories and referenced template files exist.

**Example output:**
```bash
$ samstacks validate pipeline.yml
✗ Validation error | Found 3 validation errors:
  - manifest root: Unknown field 'unknown_field' (line 1)
  - stack at index 1: Unknown field 'parameterss', did you mean 'params'? (line 12)
  - stack 'api' param 'DatabaseUrl': Stack 'database' does not exist in the pipeline. Available stacks: ['auth']
```

### Bootstrap an Existing Project

```bash
samstacks bootstrap [PATH_TO_SCAN] [OPTIONS]
```

Scans a directory (defaulting to the current directory if `PATH_TO_SCAN` is omitted) for existing AWS SAM projects (directories containing `template.yaml` or `template.yml`) and generates an initial `pipeline.yml` file.

**Purpose:**
This command helps you quickly get started with `samstacks` if you have an existing multi-stack SAM application. It will:
- Discover your SAM stacks.
- Attempt to infer dependencies between them by matching CloudFormation Output names to Parameter names.
- Consolidate common settings from any `samconfig.toml` (or `samconfig.yaml`/`.yml` if `.toml` is not found) files into a `default_sam_config` in the generated pipeline.
- Create `sam_config_overrides` for stack-specific settings found in their samconfig files.
- Order the stacks in the pipeline based on inferred dependencies.

**Key Options:**
-   `PATH_TO_SCAN`: The directory to scan. Defaults to the current directory.
-   `--output-file <filename>` / `-o <filename>`: Name for the generated pipeline file (default: `pipeline.yml` in the root of the scanned path).
-   `--default-stack-id-source <dir|samconfig_stack_name>`: Strategy to derive initial stack IDs (default: `dir`). If `samconfig_stack_name` is chosen, it will try to use the `stack_name` from the stack's samconfig file.
-   `--pipeline-name <name>`: Specify a name for the generated pipeline (defaults to the scanned directory's name + "-pipeline").
-   `--stack-name-prefix <prefix>`: Specify a global `stack_name_prefix` for the generated pipeline settings.
-   `--overwrite`: Allow overwriting an existing output file if it already exists.

**Important Considerations:**
-   The generated `pipeline.yml` is a **best-effort starting point**. You will likely need to review and manually adjust it, especially for:
    -   Complex parameter dependencies not caught by simple name matching.
    -   Fine-tuning `default_sam_config` and `sam_config_overrides` (e.g., adding capabilities, tags, or specific deployment parameters that weren't in all original samconfig files).
    -   Reviewing `params` sections for each stack.
-   The bootstrap command currently **does not migrate `parameter_overrides` or `tags`** from existing `samconfig.toml`/`.yaml` files into the generated `pipeline_settings.default_sam_config` or `stacks.sam_config_overrides`. These should be manually configured in the `pipeline.yml` as needed.
-   If dependency cycles or ambiguous dependencies (where a parameter could be satisfied by multiple outputs of the same name) are detected, the command will fail with an error, guiding you to resolve these manually.
-   It excludes `.aws-sam` directories from scanning.

**Example Usage:**
```bash
# Scan the current directory and generate pipeline.yml
samstacks bootstrap

# Scan a specific project directory and output to a custom file
samstacks bootstrap ./my-existing-sam-app -o my-app-pipeline.yml --pipeline-name "MyAwesomeApp"
```

### Advanced Validation Features

`samstacks` includes sophisticated validation to catch common errors early and provide helpful guidance:

#### Schema Validation

The validator checks all manifest fields against the defined schema for known fields and correct data types (primarily using Pydantic). It provides intelligent suggestions for common issues:

- **Root level fields**: `pipeline_name`, `pipeline_description`, `pipeline_settings`, `stacks`.
- **Pipeline settings**: `stack_name_prefix`, `stack_name_suffix`, `default_region`, `default_profile`, `inputs`, `default_sam_config` (and its nested SAM CLI structure).
- **Stack fields**: `id`, `name`, `description`, `dir`, `params`, `stack_name_suffix`, `region`, `profile`, `if`, `run`, `sam_config_overrides` (and its nested SAM CLI structure).

**Common typo detection (example of Pydantic error for an unknown field):**
```yaml
pipeline_settings:
  default_regionn: us-east-1 # ❌ Pydantic would report 'default_regionn' as an unexpected field.
```
# Note: The previous custom typo suggestion (e.g. parameterss -> params) is now implicitly handled by Pydantic's strict field checking.

#### Template Expression Validation

All `${{ ... }}` expressions are validated for correct syntax and logical consistency. This now also applies to expressions within `default_sam_config` and `sam_config_overrides` values (for `${{ env... }}`, `${{ inputs... }}`, and `${{ pipeline... }}` templates).

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

**Example with multiline description:**

```yaml
pipeline_name: E-commerce Platform
pipeline_description: |
  This pipeline deploys a complete e-commerce platform on AWS.
  
  It includes:
  - User authentication service 
  - Product catalog API
  - Shopping cart functionality
  - Payment processing integration
  
  After deployment, configure the payment gateway API keys
  and update the frontend configuration with the API endpoints.

pipeline_settings:
  # ... configuration continues ...
```

- **`pipeline_name`**: (String) The overall name for your deployment pipeline.
- **`pipeline_description`**: (String, Optional) A brief description of the pipeline's purpose. This description will be displayed at the beginning of deploy and delete operations to provide context about what the pipeline does. Supports multiline text using YAML's `|` syntax for detailed explanations and instructions.

### `pipeline_settings`

Global configurations that apply to all stacks in the pipeline, unless overridden at the stack level.

- **`stack_name_prefix`**: (String, Optional) A string prepended to each stack's `id` to form the CloudFormation stack name. Supports template substitution.
- **`stack_name_suffix`**: (String, Optional) A string appended after the stack `id` and any per-stack suffix. Supports template substitution.
- **`default_region`**: (String, Optional) Global AWS region for stack deployments. Can be overridden per stack using the stack-level `region` field.
- **`default_profile`**: (String, Optional) Global AWS CLI profile for stack deployments. Can be overridden per stack using the stack-level `profile` field.
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
- **`default`**: (Optional) Default value if not provided via CLI. If no default is specified, the input is required.
    - The `default` value can be a literal (e.g., `dev`, `2`, `true`).
    - It can also be a template string using environment variables, allowing for dynamic defaults: 
      `${{ env.MY_DEFAULT_ENV_VAR || 'literal_fallback' }}`.
    - Currently, only `${{ env... }}` expressions (with optional `||` fallbacks to literals) are supported within default value templates. These are evaluated once when the pipeline starts.
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
- **`boolean`**: Accepts `true`, `false`, `yes`, `no`, `1`, `0`, `on`, `off` (case-insensitive)

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

#### SAM Configuration Management

`samstacks` provides centralized management of SAM CLI configurations through the pipeline manifest. This allows you to define SAM CLI settings (like capabilities, regions, tags, etc.) in your `pipeline.yml` and have them automatically applied to each stack's deployment.

**Key Benefits:**
- **Centralized Configuration**: Define SAM CLI settings once in `pipeline.yml` instead of maintaining separate `samconfig.toml` files
- **Template Support**: Use environment variables, inputs, and pipeline context in SAM configurations
- **Automatic Generation**: `samstacks` generates `samconfig.yaml` files for each stack automatically
- **Individual Stack Deployment**: Generated configs allow deploying individual stacks with `sam deploy` using pipeline context

**Configuration Structure:**

```yaml
pipeline_settings:
  # Global SAM CLI configuration applied to all stacks
  default_sam_config:
    version: 0.1
    default:
      deploy:
        parameters:
          capabilities: CAPABILITY_IAM
          confirm_changeset: false
          resolve_s3: true
          region: "${{ env.AWS_REGION || 'us-east-1' }}"
          tags:
            Project: "${{ inputs.project_name }}"
            Environment: "${{ inputs.environment }}"
            ManagedBy: "samstacks"
      build:
        parameters:
          cached: true
          parallel: true

stacks:
  - id: api
    dir: ./api-stack/
    params:
      DatabaseUrl: ${{ stacks.database.outputs.DatabaseUrl }}
    # Stack-specific SAM CLI configuration overrides
    sam_config_overrides:
      default:
        deploy:
          parameters:
            capabilities: CAPABILITY_NAMED_IAM  # Override global setting
            tags:
              ServiceType: "API"  # Merges with global tags
```

**Configuration Fields:**

- **`default_sam_config`** (Pipeline-level, Optional): Global SAM CLI configuration applied to all stacks
  - Follows the same structure as `samconfig.yaml` files
  - Supports template expressions (`${{ env... }}`, `${{ inputs... }}`, `${{ pipeline... }}`)
  - Common settings: `capabilities`, `region`, `tags`, `resolve_s3`, `confirm_changeset`

- **`sam_config_overrides`** (Per-stack, Optional): Stack-specific configuration that overrides or merges with global settings
  - Same structure as `default_sam_config`
  - Stack-specific settings take precedence over global settings
  - Useful for stacks requiring different capabilities or tags

**Automatic File Management:**

When deploying, `samstacks` automatically:

1. **Backs up existing configurations**: 
   - `samconfig.toml` → `samconfig.toml.bak`
   - `samconfig.yaml` → `samconfig.yaml.bak`

2. **Generates new `samconfig.yaml`**: 
   - Merges global and stack-specific configurations
   - Resolves all template expressions
   - Adds required SAM CLI parameters (`stack_name`, `s3_prefix`, etc.)
   - Formats `parameter_overrides` correctly for SAM CLI

3. **Enables individual stack deployment**: 
   - Each stack can be deployed independently with `sam deploy`
   - Generated configs include resolved pipeline context

**Example Generated `samconfig.yaml`:**

```yaml
version: 0.1
default:
  deploy:
    parameters:
      capabilities: CAPABILITY_IAM
      confirm_changeset: false
      resolve_s3: true
      region: us-east-1
      stack_name: myapp-prod-api
      s3_prefix: myapp-prod-api
      parameter_overrides: DatabaseUrl=arn:aws:rds:us-east-1:123456789012:db:prod-db
      tags:
        Project: myapp
        Environment: prod
        ManagedBy: samstacks
        ServiceType: API
```

**Migration from Existing Configurations:**

If you have existing `samconfig.toml` files:

1. **Automatic Backup**: `samstacks` backs up existing files to `.bak` extensions
2. **Manual Migration**: Review backed-up files and migrate desired settings to `pipeline.yml`
3. **No Automatic Merging**: The new approach prioritizes explicit configuration in `pipeline.yml`

**Common Configuration Examples:**

```yaml
# Basic configuration with capabilities
pipeline_settings:
  default_sam_config:
    version: 0.1
    default:
      deploy:
        parameters:
          capabilities: CAPABILITY_IAM
          confirm_changeset: false
          resolve_s3: true

# Environment-specific configuration
pipeline_settings:
  default_sam_config:
    version: 0.1
    default:
      deploy:
        parameters:
          capabilities: CAPABILITY_IAM
          region: "${{ env.AWS_REGION }}"
          tags:
            Environment: "${{ inputs.environment }}"
            CostCenter: "${{ env.COST_CENTER || 'default' }}"
    
    # Production-specific settings
    prod:
      deploy:
        parameters:
          confirm_changeset: true  # Require confirmation in prod

# Stack-specific overrides
stacks:
  - id: iam-roles
    dir: ./iam/
    sam_config_overrides:
      default:
        deploy:
          parameters:
            capabilities: CAPABILITY_NAMED_IAM  # More permissive for IAM stack
  
  - id: lambda-functions
    dir: ./lambda/
    sam_config_overrides:
      default:
        build:
          parameters:
            use_container: true  # Use container builds for Lambda
```

**Best Practices:**

1. **Start with Global Defaults**: Define common settings in `default_sam_config`
2. **Use Template Expressions**: Leverage environment variables and inputs for dynamic configuration
3. **Override Selectively**: Use `sam_config_overrides` only when stacks need different settings
4. **Review Backups**: Check `.bak` files when migrating from existing configurations
5. **Test Individual Deployment**: Verify that `sam deploy` works in each stack directory after pipeline deployment

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

### Mathematical and Logical Expressions

Template expressions support mathematical operations, logical comparisons, and boolean logic using the `simpleeval` library. This enables powerful runtime calculations and conditional logic within your manifest.

#### Mathematical Operations

```yaml
stacks:
  - id: processor
    params:
      # Convert days to seconds
      MessageRetentionPeriod: ${{ inputs.retention_days * 86400 }}
      
      # Calculate memory with overhead
      LambdaMemorySize: ${{ inputs.base_memory + 128 }}
      
      # Percentage calculations
      MaxConcurrency: ${{ inputs.total_capacity * 0.8 }}
      
      # Complex expressions with parentheses
      ComplexCalculation: ${{ (inputs.count + 5) * inputs.multiplier }}
```