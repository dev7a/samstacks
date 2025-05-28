# SAM Configuration Persistence Plan

## 1. Goal ✅ COMPLETED

To allow `samstacks` to generate and manage a `samconfig.yaml` file within each stack's directory. This file will persist resolved configurations derived from the `pipeline.yml` (including global defaults, stack-specific overrides, and pipeline-driven parameters like stack outputs). This enables users to deploy individual stacks using `sam deploy` with the context of the last successful `samstacks` pipeline run and provides a centralized way to manage SAM CLI configurations.

**Status: ✅ FULLY IMPLEMENTED AND TESTED**

## 2. Configuration in `pipeline.yml` ✅ COMPLETED

Introduce new sections in `pipeline.yml` to define SAM CLI settings:

*   **`default_sam_config` (Pipeline-level under `pipeline_settings`, Optional):**
    *   A YAML structure mirroring `samconfig.yaml` format (e.g., `version`, `default.deploy.parameters`, `prod.build.parameters`).
    *   These settings serve as the global baseline for all stacks.
    *   Supports `samstacks` templating (`${{ env... }}`, `${{ inputs... }}`, `${{ pipeline... }}`).

*   **`sam_config_overrides` (Per-stack in `stacks` list, Optional):**
    *   A YAML structure mirroring `samconfig.yaml` format.
    *   These settings override or merge with `default_sam_config` for a specific stack.
    *   Supports `samstacks` templating.

**Example `pipeline.yml` Snippet:**

```yaml
# pipeline.yml
pipeline_name: MyApp

pipeline_settings:
  default_sam_config:
    version: 0.1
    default:
      deploy:
        parameters:
          resolve_s3: true
          capabilities: CAPABILITY_IAM
          confirm_changeset: false
          region: "${{ env.AWS_REGION || 'us-east-1' }}"
          tags:
            PipelineName: "${{ pipeline.name }}" # Example using pipeline context
            DeployedBy: "samstacks"

stacks:
  - id: vpc
    dir: stacks/vpc/
    # params are for pipeline-driven parameter_overrides
    params:
      VpcCidr: "10.0.0.0/16"

  - id: app
    dir: stacks/app/
    params:
      AppVpcId: "${{ stacks.vpc.outputs.VpcId }}"
    sam_config_overrides:
      default:
        deploy:
          parameters:
            capabilities: CAPABILITY_NAMED_IAM
            tags:
              ServiceName: "AppService" # Merges with default tags
```

**Important Notes:**
- **`version` key**: Required by SAM CLI. Automatically added if not present (defaults to 0.1).
- **`parameter_overrides` format**: SAM CLI expects this as a space-separated string of key=value pairs, not a dictionary. This is handled automatically by samstacks.
- **`confirm_changeset`**: Defaults to `false` for automated deployments.

## 3. Core `samstacks` Logic (Per Stack) ✅ COMPLETED

The following steps are executed by `samstacks` for each stack before its deployment:

### 3.1. File Handling & Backup ✅ IMPLEMENTED
*   Define paths:
    *   `target_samconfig_path = stack_dir / "samconfig.yaml"`
    *   `existing_toml_path = stack_dir / "samconfig.toml"`
    *   `backup_toml_path = stack_dir / "samconfig.toml.bak"`
    *   `backup_yaml_path = stack_dir / "samconfig.yaml.bak"`
*   If `existing_toml_path` exists:
    *   Log a message about backing up the existing file
    *   Remove `backup_toml_path` if it exists (to ensure fresh backup)
    *   Rename `existing_toml_path` to `backup_toml_path`
*   If `target_samconfig_path` exists:
    *   Back up existing `samconfig.yaml` to `samconfig.yaml.bak`

### 3.2. No Local Configuration Merging ✅ IMPLEMENTED
*   Existing local configurations are backed up but **NOT merged** into the new configuration
*   The new `samconfig.yaml` is based purely on `pipeline.yml` settings
*   Users must manually migrate desired settings from backup files to `pipeline.yml`

### 3.3. Derive Pipeline-Defined SAM Configuration ✅ IMPLEMENTED
*   Start with a deep copy of `pipeline_settings.default_sam_config` (if any, otherwise an empty dictionary)
*   If the current stack has `sam_config_overrides`, deep-merge these into the copied settings
*   Stack-specific overrides take precedence over defaults

### 3.4. Template Resolution ✅ IMPLEMENTED
*   Uses `TemplateProcessor.process_structure()` to recursively resolve all template expressions
*   Resolves `${{ env... }}`, `${{ inputs... }}`, `${{ pipeline... }}` expressions
*   Does **not** resolve `${{ stacks...outputs... }}` at this stage (handled separately for params)

### 3.5. Pipeline-Driven Parameters ✅ IMPLEMENTED
*   Handled by `Pipeline._deploy_stack()` before calling `SamConfigManager`
*   Stack `params` from `pipeline.yml` are fully resolved including stack outputs
*   Passed to `SamConfigManager` as `resolved_stack_params`

### 3.6. Apply Stack-Specific Configurations ✅ IMPLEMENTED
*   Handled by `SamConfigManager._apply_stack_specific_configs()`
*   Sets/overwrites core samstacks-controlled parameters:
    *   `stack_name`: Set to the pipeline-determined deployed stack name
    *   `s3_prefix`: Set to match the stack name
    *   `region`: Set if not already defined and effective_region is provided
    *   `resolve_s3`: Defaults to `true` if not set
    *   `confirm_changeset`: Defaults to `false` if not set
    *   `version`: Defaults to `0.1` if not set (required by SAM CLI)
*   Merges `resolved_stack_params` into `parameter_overrides` as a space-separated string

### 3.7. Write Final Configuration ✅ IMPLEMENTED
*   Uses PyYAML to write the fully materialized configuration to `samconfig.yaml`
*   No samstacks template expressions remain in the output file

### 3.8. SAM CLI Execution ✅ IMPLEMENTED
*   Changes working directory to `stack_dir`
*   Executes `sam build` and `sam deploy` without explicit config parameters
*   SAM CLI automatically discovers and uses the generated `samconfig.yaml`

## 4. Key Components/Modules ✅ COMPLETED

### 4.1. Core Module Updates ✅ IMPLEMENTED
*   **`samstacks/core.py`:**
    *   `Pipeline.__init__()`: Stores `default_sam_config` from Pydantic model
    *   `Pipeline._deploy_stack()`: Integrates `SamConfigManager` before SAM CLI execution
    *   `Stack.__init__()`: Stores `sam_config_overrides` from Pydantic model
    *   Simplified SAM CLI invocation (no explicit config parameters)

### 4.2. New SamConfigManager Module ✅ IMPLEMENTED
*   **`samstacks/samconfig_manager.py`:**
    *   `SamConfigManager` class with full functionality
    *   `generate_samconfig_for_stack()`: Main orchestration method
    *   `_apply_stack_specific_configs()`: Applies samstacks-controlled settings
    *   `_deep_copy_dict()`, `_deep_merge_dicts()`: Utility methods
    *   Proper handling of SAM CLI parameter format requirements

### 4.3. Template Processing Enhancement ✅ IMPLEMENTED
*   **`samstacks/templating.py`:**
    *   `TemplateProcessor.process_structure()`: Recursively processes nested structures
    *   Handles all template expression types except stack outputs (for SAM config)

### 4.4. Pydantic Models ✅ IMPLEMENTED
*   **`samstacks/pipeline_models.py`:**
    *   Updated models to include `default_sam_config` and `sam_config_overrides`
    *   Proper validation and type definitions
    *   `SamConfigContentType = Dict[str, Any]`

## 5. Libraries/Dependencies ✅ COMPLETED

*   **`PyYAML`**: For YAML parsing and writing ✅
*   **`tomllib`**: For parsing TOML (Python 3.11+ standard library) ✅
*   **`Pydantic V2`**: For enhanced validation and models ✅

## 6. Edge Cases & Considerations ✅ ADDRESSED

*   **Empty pipeline settings**: Gracefully handled with default empty dictionaries ✅
*   **Corrupted existing files**: Error handling with try-catch blocks ✅
*   **SAM CLI format requirements**: Parameter overrides formatted as space-separated strings ✅
*   **File permissions**: Proper error handling for write operations ✅
*   **Idempotency**: Consistent regeneration on re-runs ✅
*   **Version requirement**: Automatic addition of required `version` key ✅

## 7. Testing Strategy ✅ COMPLETED

### 7.1. Unit Tests ✅ IMPLEMENTED
*   **SamConfigManager tests**: 23 comprehensive tests covering all functionality
*   **Template processing tests**: Nested structure processing
*   **Pydantic model tests**: Validation and parsing
*   **Core integration tests**: End-to-end pipeline functionality

### 7.2. Integration Tests ✅ IMPLEMENTED
*   **File operation tests**: Backup mechanisms, YAML generation
*   **Multi-stack pipeline tests**: Output passing and parameter resolution
*   **CLI tests**: Full command-line interface testing

### 7.3. Real-world Testing ✅ VERIFIED
*   **Example deployment**: Successfully deployed S3 Object Processor pipeline
*   **SAM CLI compatibility**: Verified correct parameter format and execution
*   **All 158 tests passing**: Comprehensive test coverage

## 8. Implementation Status: ✅ COMPLETE

**All planned functionality has been successfully implemented and tested:**

1. ✅ SAM configuration persistence in `samconfig.yaml`
2. ✅ Pipeline-level and stack-level configuration management
3. ✅ Template expression resolution for SAM configs
4. ✅ Automatic backup of existing configurations
5. ✅ SAM CLI format compliance (parameter_overrides as strings)
6. ✅ Integration with existing samstacks pipeline flow
7. ✅ Comprehensive test suite (158 tests passing)
8. ✅ Real-world deployment verification

**Key Learnings During Implementation:**
- SAM CLI requires `parameter_overrides` as space-separated strings, not dictionaries
- The `version` key is mandatory in samconfig files
- `confirm_changeset: false` is essential for automated deployments
- Backup strategy works well for user migration path
- No automatic merging simplifies the implementation and user experience

**Next Steps:**
- Update README.md to document the new SAM configuration features
- Consider adding validation for common SAM CLI configuration fields
- Potential future enhancement: Migration tool to help users move from backup files to pipeline.yml