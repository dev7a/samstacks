# Publishing Guide for samstacks

This document outlines the steps to take before publishing a new version of the `samstacks` package to PyPI.

## Pre-Release Checklist

Before creating a new release and publishing, please ensure the following steps are completed and verified:

1.  **Branching Strategy (Recommended):**
    *   From your main development branch (e.g., `main` or `develop`), create a new release branch: 
        ```bash
        git checkout main # or your development branch
        git pull
        git checkout -b release/vX.Y.Z # Replace X.Y.Z with the target version
        ```
    *   Perform all subsequent pre-release steps (versioning, changelog, fixes) on this `release/vX.Y.Z` branch.

2.  **Update Version Number:**
    *   On the `release/vX.Y.Z` branch, determine the new version number based on [Semantic Versioning (SemVer)](https://semver.org) (e.g., `0.1.1`, `0.2.0`, `1.0.0`).
    *   Update the version number in **two** places:
        *   `pyproject.toml` (e.g., `version = "0.1.1"`)
        *   `samstacks/__init__.py` (e.g., `__version__ = "0.1.1"`)

3.  **Update `CHANGELOG.md`:**
    *   On the `release/vX.Y.Z` branch, add a new section for the upcoming version (e.g., `## [0.1.1] - YYYY-MM-DD`).
    *   Replace `YYYY-MM-DD` with the current date.
    *   List all notable changes (Added, Changed, Fixed, Removed, Deprecated, Security) under this version.
    *   Ensure a link to the new version is added at the top if you're following the "Keep a Changelog" diff link style.

4.  **Run All Local Checks (on `release/vX.Y.Z` branch):**
    *   Ensure your virtual environment is active and all dev dependencies are installed (`uv pip install -e ".[dev]"`).
    *   **Format Code:**
        ```bash
        ruff format --isolated samstacks tests
        ```
    *   **Lint Code & Auto-fix:**
        ```bash
        ruff check --fix --isolated samstacks tests
        ```
    *   **Static Type Checking (if using MyPy):**
        ```bash
        mypy samstacks
        ```
    *   **Run Unit Tests & Coverage:**
        ```bash
        pytest
        ```
        (Ensure all tests pass and coverage is acceptable.)

5.  **Update `README.md` (if necessary, on `release/vX.Y.Z` branch):**
    *   Review the `README.md` for any new features, CLI changes, or important notes that need to be documented for the new version.

6.  **Local Build Test (Highly Recommended, on `release/vX.Y.Z` branch):**
    *   Clean up any old build artifacts: `rm -rf dist/ build/ samstacks.egg-info/`
    *   Build the source distribution (sdist) and wheel:
        ```bash
        python -m build --sdist --wheel
        ```
    *   Inspect the contents of the generated `dist/` directory.
    *   (Optional) Install the wheel in a fresh virtual environment and test basic functionality.

7.  **Commit All Changes (to `release/vX.Y.Z` branch):**
    *   Ensure all changes (version bumps, changelog, README updates, code fixes) are committed.
    *   Example commit message: `Release: Prepare for version 0.1.1`

8.  **Push Release Branch and Open Pull Request:**
    *   Push the `release/vX.Y.Z` branch to GitHub:
        ```bash
        git push origin release/vX.Y.Z
        ```
    *   Open a Pull Request (PR) from `release/vX.Y.Z` to your main development branch (e.g., `main`).
    *   Ensure the PR title and description are clear (e.g., "Release vX.Y.Z").
    *   Wait for all automated checks (CI tests from GitHub Actions) to pass on the PR.

9.  **Review and Merge PR:**
    *   Have the PR reviewed if applicable.
    *   Once all checks pass and approvals are met, **squash merge** the PR into the `main` branch. This keeps the `main` branch history clean with a single commit for the release.

## Publishing Process (via GitHub Actions)

This project uses a GitHub Actions workflow (`.github/workflows/ci.yml`) to automate publishing to PyPI.

1.  **Trigger the Workflow:**
    *   Publishing is triggered by the **squash merge to the `main` branch** (which results in a push event on `main` containing the release changes).

2.  **Monitor the GitHub Action:**
    *   Go to the "Actions" tab in your GitHub repository.
    *   Find the workflow run triggered by the merge to `main`.
    *   The workflow will:
        *   Run tests and quality checks again on `main` (as a final safeguard).
        *   If tests pass, the `publish` job will proceed.
        *   Build the package.
        *   Verify the version (it should match what was merged).
        *   Publish the package to PyPI.
        *   If publishing is successful, create and push a Git tag (e.g., `v0.1.1`) to the `main` branch commit.

3.  **Verify on PyPI:**
    *   Once the workflow completes successfully, go to [https://pypi.org/project/samstacks/](https://pypi.org/project/samstacks/).
    *   Verify that the new version is listed and the package page looks correct.

4.  **Create a GitHub Release:**
    *   Go to your repository's "Releases" page on GitHub.
    *   Click "Draft a new release".
    *   Choose the Git tag that was just created by the workflow (e.g., `vX.Y.Z`).
    *   Set the release title (e.g., `Version X.Y.Z`).
    *   Copy the relevant section from `CHANGELOG.md` into the release description.
    *   (Optional) Upload the `sdist` and `wheel` files from the `dist/` directory (these can also be downloaded from the GitHub Actions run artifacts if configured, or from PyPI) as release assets.
    *   Publish the release.

## Publishing to TestPyPI (First Time or for Testing Changes)

Before publishing a new version to the real PyPI for the first time, or when testing changes to the packaging or publishing process, it's highly recommended to use [TestPyPI](https://test.pypi.org/).

1.  **Configure Workflow for TestPyPI (if needed):**
    *   You might need a separate workflow or a modification to the existing workflow to target TestPyPI. This usually involves:
        *   Using a different PyPI token secret (e.g., `secrets.TEST_PYPI_API_TOKEN`).
        *   Modifying the `twine upload` command: `twine upload --repository testpypi dist/*`.
    *   Alternatively, perform TestPyPI uploads manually from your local machine after building.

2.  **Manual TestPyPI Upload (Example):**
    *   Build the package: `python -m build --sdist --wheel`
    *   Upload to TestPyPI:
        ```bash
        twine upload --repository testpypi dist/*
        # You will be prompted for your TestPyPI username and password (or token)
        ```

3.  **Verify on TestPyPI:**
    *   Check [https://test.pypi.org/project/samstacks/](https://test.pypi.org/project/samstacks/).
    *   Try installing from TestPyPI in a clean virtual environment:
        ```bash
        pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple samstacks
        ```

---

This guide should help ensure that each release is consistent and of high quality. 