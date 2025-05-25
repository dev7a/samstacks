# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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