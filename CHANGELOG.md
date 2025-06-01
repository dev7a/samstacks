# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.1] - 2025-06-01

### Fixed
- **Documentation**: Improved README.md to include missing fields in the "Applicable fields for templating" section

## [0.4.0] - 2025-06-01

### Added
- **Mathematical and Logical Expressions**: Template expressions now support advanced mathematical operations and logical comparisons
  - **Mathematical Operations**: Support for arithmetic operators (`+`, `-`, `*`, `/`, `//`, `%`, `**`) with parentheses for grouping
  - **Logical Operations**: Support for comparison operators (`==`, `!=`, `<`, `<=`, `>`, `>=`) and boolean logic (`and`, `or`, `not`, `&&`, `||`, `!`)
  - **Type Conversion**: Built-in functions `int()`, `float()`, and `str()` for explicit type conversion in expressions
  - **Complex Expressions**: Enable sophisticated conditional logic and runtime calculations within manifests
  - **Environment Variable Math**: Support for mathematical operations with environment variables using explicit conversion (e.g., `int(env.COUNT) * 2`)
  - **Ternary-like Expressions**: JavaScript-style conditional expressions (e.g., `condition && value_if_true || value_if_false`)
  - **Expression Validation**: Smart validation system detects numeric environment variables in mathematical expressions and suggests explicit conversion
  - **Safety-first Design**: No implicit type conversion to prevent unexpected behavior like string concatenation instead of addition
  - **Graceful Fallback**: Works with or without the `simpleeval` library installed
- **SAM Configuration Management**: Centralized SAM CLI configuration through `pipeline.yml`
  - New `default_sam_config` field in `pipeline_settings` for global SAM CLI configuration
  - New `sam_config_overrides` field per stack for stack-specific configuration overrides
  - Automatic generation of `samconfig.yaml` files in each stack directory
  - Support for template expressions (`${{ env... }}`, `${{ inputs... }}`, `${{ pipeline... }}`) in SAM configurations
  - Automatic backup of existing `samconfig.toml` and `samconfig.yaml` files
- **`bootstrap` Command**: New CLI command `samstacks bootstrap` to automatically generate an initial `pipeline.yml` from existing SAM projects.
  - Scans for `template.yaml`/`.yml` and `samconfig.toml` (with fallback to `samconfig.yaml`/`.yml`).
  - Infers stack dependencies based on output-to-parameter name matching.
  - Consolidates common `samconfig` settings (excluding `tags` and `parameter_overrides`) into `pipeline_settings.default_sam_config`.
  - Creates `sam_config_overrides` for stack-specific settings (excluding `tags` and `parameter_overrides`).
  - Excludes `.aws-sam` directories from scan.
  - Errors out on dependency cycles or ambiguous dependencies, guiding manual resolution.
- **`delete` Command**: New CLI command `samstacks delete` to delete all stacks in a pipeline
  - Deletes stacks in reverse dependency order (consumers first, then producers)
  - Interactive confirmation by default with `--no-prompts` flag for automation
  - `--dry-run` option to preview what would be deleted without actually deleting
  - Uses `sam delete` for consistent behavior with SAM CLI
  - Provides detailed summary of deletion results
- Enhanced Pydantic V2 models for improved validation and type safety
- Comprehensive test suite with unit and integration tests for all major features (now 196 tests passing)
- Support for individual stack deployment using generated `samconfig.yaml` files

### Changed
- **Enhanced Template Processing**: Refactored templating engine to use a two-step process:
  1. Replace samstacks placeholders (`env.VAR`, `inputs.NAME`, `stacks.ID.outputs.NAME`) with actual values
  2. Evaluate resulting mathematical/logical expressions with simpleeval
- **Improved Validation**: Enhanced validation system to detect and warn about mathematical expressions that could benefit from explicit type conversion
- **BREAKING**: SAM CLI configuration is now managed centrally through `pipeline.yml` instead of individual `samconfig.toml` files
- **BREAKING**: Generated `samconfig.yaml` files replace existing configurations (with automatic backup)
- **BREAKING**: Removed `--region` and `--profile` CLI flags from `deploy` and `delete` commands
  - Region and profile configuration is now managed exclusively through `pipeline.yml` manifest
  - Use `default_region`/`default_profile` in `pipeline_settings` for global configuration
  - Use `region`/`profile` fields in individual stack definitions for per-stack overrides
  - This ensures deployment consistency and prevents configuration conflicts
- Improved parameter format compliance with SAM CLI requirements (parameter_overrides as space-separated strings)
- Enhanced template processing to support nested dictionary/list structures
- Simplified SAM CLI invocation by relying on auto-discovery of `samconfig.yaml`
- Fixed region override logic to ensure pipeline region settings always take precedence over local configuration

### Fixed
- **Critical Bootstrap Bug**: Fixed CloudFormation stack naming compliance
  - Bootstrap now generates stack names with hyphens instead of underscores
  - Ensures all generated stack names comply with CloudFormation naming rules (letters, numbers, hyphens only)
  - Updated all bootstrap tests to reflect correct naming conventions
- **Region Override Bug**: Fixed issue where `default_region` in pipeline.yml wasn't working correctly
  - Pipeline region settings now properly override local samconfig region settings
  - Ensures consistent region usage across all stacks in a pipeline

### Examples
```yaml
# Mathematical calculations
params:
  MessageRetentionPeriod: ${{ inputs.retention_days * 86400 }}  # Days to seconds
  LambdaMemorySize: ${{ inputs.base_memory + 128 }}            # Add overhead
  
# Conditional logic
if: ${{ inputs.environment == 'prod' || inputs.enable_testing }}

# Environment variable math (with explicit conversion)
params:
  ScaledCapacity: ${{ int(env.BASE_CAPACITY) * 2 }}
  
# Complex conditional expressions  
params:
  InstanceType: ${{ 
    inputs.user_count < 1000 && 'db.t3.micro' || 
    inputs.user_count < 10000 && 'db.t3.small' || 
    'db.t3.medium' 
  }}
```

### Migration Guide from v0.3.x

#### CLI Flag Changes (BREAKING)
**Before:**
```bash
samstacks deploy pipeline.yml --region us-east-1 --profile production
```

**After:**
```yaml
# In pipeline.yml
pipeline_settings:
  default_region: us-east-1
  default_profile: production
```
```bash
samstacks deploy pipeline.yml
```

**Why this change?**
- **Prevents configuration conflicts**: No more runtime overrides that could corrupt samconfig.yaml files
- **Ensures deployment coherence**: Pipeline.yml becomes single source of truth for all configuration
- **Eliminates cross-region issues**: No more mismatched resource dependencies between regions
- **Simplifies architecture**: Removes complex runtime configuration override logic

#### SAM Configuration Migration
If you have existing `samconfig.toml` files in your stack directories:

1. **Automatic Backup**: When you run `samstacks deploy`, existing files will be automatically backed up:
   - `samconfig.toml` → `samconfig.toml.bak`
   - `samconfig.yaml` → `samconfig.yaml.bak`

2. **Review Backed-up Configuration**: Check your `.bak` files to see what settings you had:
   ```bash
   # Example of reviewing backed-up configuration
   cat stacks/my-stack/samconfig.toml.bak
   ```

3. **Migrate to Pipeline Configuration**: Add equivalent settings to your `pipeline.yml`:

   **Before (samconfig.toml):**
   ```toml
   version = 0.1
   [default.deploy.parameters]
   capabilities = "CAPABILITY_IAM"
   resolve_s3 = true
   region = "us-east-1"
   tags = 'Project="MyApp" Environment="prod"'
   ```

   **After (pipeline.yml):**
   ```yaml
   pipeline_settings:
     default_region: us-east-1  # Global region setting
     default_sam_config:
       version: 0.1
       default:
         deploy:
           parameters:
             capabilities: CAPABILITY_IAM
             resolve_s3: true
             tags:
               Project: MyApp
               Environment: prod
   ```

4. **Stack-Specific Overrides**: If different stacks had different configurations, use `sam_config_overrides`:
   ```yaml
   stacks:
     - id: iam-stack
       dir: ./iam/
       sam_config_overrides:
         default:
           deploy:
             parameters:
               capabilities: CAPABILITY_NAMED_IAM  # More permissive for IAM resources
   ```

5. **Template Expression Migration**: Environment variable references are now more powerful:
   
   **Before:**
   ```toml
   region = "${{ env.AWS_REGION }}"
   ```
   
   **After:**
   ```yaml
   default_region: "${{ env.AWS_REGION || 'us-east-1' }}"  # Now supports fallbacks
   ```

6. **Verify Migration**: After updating your `pipeline.yml`, run:
   ```bash
   samstacks validate pipeline.yml  # Check for any configuration errors
   samstacks deploy pipeline.yml    # Deploy and verify generated samconfig.yaml files
   ```

### Benefits of the New Approach
- **Centralized Configuration**: Manage all deployment settings in one place
- **Better Template Support**: Use inputs, environment variables, and pipeline context
- **Individual Stack Deployment**: Generated configs enable `sam deploy` in any stack directory
- **Automatic Parameter Handling**: Pipeline-resolved parameters are automatically included
- **Type Safety**: Pydantic validation ensures configuration correctness
- **Deployment Consistency**: Same command produces same results regardless of runtime environment
- **Cross-region Safety**: No more dependency mismatches between regions

### Backward Compatibility
- Existing `samconfig.toml` files are automatically backed up but no longer used
- No automatic merging occurs - migration must be done manually to ensure explicit configuration
- The new system generates `samconfig.yaml` files that SAM CLI prefers over `.toml` files
- CLI interface remains the same except for removed `--region` and `--profile` flags

## [0.3.1] - 2025-05-26

### Added

- **Templated Default Values for Pipeline Inputs:**
  - Input `default` values can now use template expressions with environment variables.
  - Supports `${{ env.VARIABLE_NAME || 'fallback_literal' }}` syntax in input defaults.
  - Enables dynamic default values based on environment configuration.
  - Template expressions in defaults are evaluated once when the pipeline starts.
  - Provides a powerful way to define "variables" in the pipeline that can be reused across multiple stacks.

### Changed

- **Enhanced Input Processing:**
  - Input default values are now resolved and validated before the main template processor is initialized.
  - Template expressions in input defaults are restricted to environment variables only (no stack outputs or other inputs).
  - Improved error handling for malformed template expressions in input defaults.
  - Added validation to ensure templated defaults resolve to values compatible with their declared input type.

### Fixed

- **Template Processing Improvements:**
  - Fixed handling of unquoted literals in template expressions (e.g., numeric and boolean fallbacks).
  - Improved `TemplateProcessor._resolve_single_part` to correctly handle unrecognized expressions as literal strings.
  - Enhanced error specificity by catching `ManifestError` instead of generic `Exception` in template processing.

### Documentation

- **Updated README:**
  - Added comprehensive documentation for templated default values in pipeline inputs.
  - Enhanced examples showing environment variable usage in input defaults.
  - Clarified the evaluation order and restrictions for templated defaults.

## [0.2.0] - 2025-05-26

### Added

- **Pipeline Inputs Feature:**
  - Define typed runtime inputs for pipelines via `pipeline_settings.inputs` in the manifest.
    - Supported input types: `string`, `number`, `boolean`.
    - Each input can have a `description` and a `default` value.
    - Inputs without a default are considered required.
  - Provide input values via CLI using `--input <name=value>` or `-i <name=value>` (multiple allowed).
  - Use inputs in template expressions with `${{ inputs.input_name }}` syntax.
  - Inputs participate in the `||` fallback logic, with CLI values taking precedence over defaults.
  - **Validation:**
    - Manifest validation checks the structure and types of input definitions (e.g., `type` value, compatibility of `default` with `type`).
    - Runtime validation ensures required inputs are provided and CLI-supplied values match their defined types (`number`, `boolean`).
  - **Templating:**
    - `TemplateProcessor` now resolves `${{ inputs.<name> }}`, correctly handling CLI overrides, defaults, and type conversions for use in templates.
  - **Examples:**
    - Added `examples/inputs-pipeline.yml` demonstrating various uses of pipeline inputs, including conditional stack deployment and parameterization.
  - **Testing:**
    - Comprehensive unit tests for input validation in `ManifestValidator`.
    - Unit tests for runtime input checks in `Pipeline.validate()`.
    - Unit tests for `TemplateProcessor`'s handling of input resolution and fallbacks.

### Changed

- **CLI (`deploy` command):**
  - Added `--input`/`-i` option to accept pipeline input values.
- **Core:**
  - `Pipeline` class now manages defined inputs (from manifest) and CLI-provided inputs.
  - `TemplateProcessor` updated to support `${{ inputs.<name> }}` resolution.
- **Validation:**
  - `ManifestValidator` extended to validate the `pipeline_settings.inputs` schema.
  - `Pipeline.validate()` now checks for missing required inputs and type mismatches in CLI-provided inputs.
- **Input Handling Improvements:**
  - CLI input values are now automatically trimmed of leading/trailing whitespace.
  - Whitespace-only CLI input values are treated as not provided, allowing fallback to defaults.
  - Boolean input validation now consistently accepts `on`/`off` values in addition to `true`/`false`, `yes`/`no`, `1`/`0`.
  - Error messages for undefined inputs now display available inputs as comma-separated strings for better readability.
  - Unknown CLI input keys (not defined in `pipeline_settings.inputs`) are now rejected with clear error messages to prevent silent misconfiguration.
  - Refactored CLI input processing logic into a shared utility function (`input_utils.process_cli_input_value`) to reduce code duplication between validation and templating.
  - Enhanced CLI input parsing documentation to clarify that values containing '=' will only split on the first occurrence.
  - Improved validation error messages for input default values with more granular type checking and clearer error descriptions.

## [0.1.4] - 2025-05-26

### Added

- **Advanced Manifest Validation System:**
  - **Schema Validation:** Comprehensive validation of all manifest fields with intelligent typo detection and suggestions.
  - **Template Expression Validation:** Full validation of `${{ ... }}` expressions including syntax checking and dependency validation.
  - **Dependency Order Validation:** Ensures stack outputs only reference stacks defined earlier in the pipeline.
  - **Line Number Tracking:** Precise error reporting with line numbers when available for schema errors.
  - **Multiple Error Collection:** All validation errors are collected and presented together instead of failing on first error.
  - **Smart Suggestions:** Levenshtein distance-based suggestions for common field name typos (e.g., `parameterss` → `params`).

- **Enhanced Error Formatting:**
  - Clean unnumbered bullet list format for multiple errors.
  - Line numbers shown in parentheses at the end of error messages when available.
  - Context-aware error messages with specific field locations.
  - Helpful suggestions for common syntax errors (e.g., `stack.` vs `stacks.` in expressions).

- **Validation Features:**
  - Validates all known fields: pipeline root, pipeline_settings, and stack definitions.
  - Catches forward references in stack output expressions.
  - Validates environment variable and stack output expression syntax.
  - Provides available stack lists when referencing nonexistent stacks.
  - Comprehensive test coverage with 19 validation-specific tests.

### Changed

- **Improved `samstacks validate` Command:**
  - Now provides comprehensive validation instead of basic syntax checking.
  - Enhanced error messages with actionable suggestions.
  - Better user experience with clear, scannable error formatting.

### Fixed

- **Type System Improvements:**
  - Added missing return type annotations to resolve mypy errors.
  - Fixed module path conflicts in mypy configuration with `explicit_package_bases = true`.
  - Enhanced type safety across validation module.

### Documentation

- **Comprehensive Validation Documentation:**
  - Added new "Advanced Validation Features" section to README.
  - Documented schema validation, template expression validation, and error formatting.
  - Added validation best practices and troubleshooting guidance.
  - Enhanced CLI Commands section with detailed validation examples.
  - Updated Table of Contents and Troubleshooting sections.

## [0.1.3] - 2025-05-26

### Added

- **Enhanced SAM Deployment Parameters:**
  - Automatically sets `--s3-prefix` to match the stack name for consistent S3 artifact organization.
  - Automatically enables `--resolve-s3` to let SAM create and manage S3 buckets for deployment artifacts.
  - These parameters are now automatically applied alongside the existing `--stack-name` override.

### Changed

- **Improved Versioning System:**
  - Migrated from manual version management to Hatch's automatic version generation.
  - Version is now managed in a single source of truth: `pyproject.toml`.
  - Auto-generates `samstacks/version.py` during build process.
  - CI/CD workflow now reads version from generated file instead of `__init__.py`.
  - Added fallback version mechanism for development when `version.py` doesn't exist.

### Documentation

- **Enhanced README:**
  - Added new "SAM Deployment Parameters" section explaining automatic parameter handling.
  - Documented how `samstacks` overrides `samconfig.toml` settings for consistency.
  - Clarified which `samconfig.toml` settings are respected vs. overridden.

## [0.1.2] - 2025-05-26

### Documentation

- Minor documentation updates and improvements.

## [0.1.1] - 2025-05-26

### Documentation

- Documentation fixes and clarifications.

## [0.1.0] - 2025-05-25

### Added

- **Core Pipeline Engine:**
  - Deploy a pipeline of AWS SAM stacks defined in a YAML manifest.
  - Sequential stack deployment respecting manifest order.
  - Global pipeline settings: `stack_name_prefix`, `stack_name_suffix`, `default_region`, `default_profile`.
  - Per-stack settings: `id`, `name`, `description`, `dir` (relative to manifest), `params`, `stack_name_suffix`, `region`, `profile`.
- **Advanced Templating System:**
  - Support for `${{ env.VARIABLE_NAME }}` for environment variable substitution.
  - Support for `${{ stacks.<stack_id>.outputs.<OutputName> }}` for cross-stack output referencing.
  - Support for `||` operator for default values in expressions (e.g., `${{ env.VAR || 'default' }}`).
- **`samconfig.toml` Integration:**
  - Preprocessing of `samconfig.toml` for `${{ env.VARIABLE_NAME }}` substitutions.
  - Uses processed `samconfig.toml` for `sam build` and `sam deploy`.
- **Conditional Stack Deployment:**
  - `if` field in stack definitions to control deployment based on templated conditions.
- **Post-Deployment Scripts:**
  - `run` field in stack definitions for executing shell scripts after successful deployment.
  - Scripts support template substitution and run in the stack's directory.
- **Command-Line Interface (CLI):**
  - `samstacks deploy <manifest_file>` command with options for region, profile, debug, quiet.
  - `samstacks validate <manifest_file>` command.
  - `samstacks --version`.
  - Real-time streaming of `sam deploy` output.
  - **`--auto-delete-failed` flag:** 
    - Proactively deletes stacks in `ROLLBACK_COMPLETE` state before deployment.
    - Proactively deletes pre-existing 'FAILED' changesets with "No updates are to be performed." reason.
- **Automatic Cleanup:**
  - Default behavior: Automatically deletes the 'FAILED' changeset created by SAM CLI when a stack deployment results in "No changes to deploy."
- **Enhanced CLI Presentation:**
  - Integration with `rich` library for styled output (headers, tables, status messages).
  - Quieter logging for `boto3`/`botocore` by default.
  - UI styling inspired by `otel_layer_utils/ui_utils.py` (no emojis, no panels, specific prefixes).
- **Error Handling & Robustness:**
  - Graceful handling of "No changes to deploy" from SAM CLI.
  - Custom exception hierarchy (`SamStacksError`).
- **Development Setup:**
  - Instructions for `uv` and `ruff` in `README.md`.
  - Target Python 3.12+.
- **GitHub Actions CI/CD Workflow:**
  - Workflow for testing on PRs/pushes (Python 3.12, x64).
  - Quality checks (ruff, mypy, pytest with coverage).
  - Conditional publishing to PyPI on pushes to `main` branch, including version checking and Git tagging.
  - Codecov integration.

### Changed

- Stack directory paths (`dir`) in the manifest are now resolved relative to the manifest file's location, not the Current Working Directory.

### Fixed

- Addressed various bugs and improved stability during iterative development of features.
- Resolved circular import issue between `core.py` and `cli.py` by introducing `presentation.py`.
- Corrected path handling for post-deployment scripts.

[Unreleased]: https://github.com/dev7a/samstacks/compare/v0.3.1...HEAD
[0.3.1]: https://github.com/dev7a/samstacks/compare/v0.2.0...v0.3.1
[0.2.0]: https://github.com/dev7a/samstacks/compare/v0.1.4...v0.2.0
[0.1.4]: https://github.com/dev7a/samstacks/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/dev7a/samstacks/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/dev7a/samstacks/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/dev7a/samstacks/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/dev7a/samstacks/releases/tag/v0.1.0 