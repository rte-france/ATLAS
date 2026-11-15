# Release Process

This document outlines the process for creating releases and publishing documentation for the Atlas project.

## Overview

The Atlas project uses an automated release workflow that:

- Publishes packages to PyPI when version tags are pushed
- Automatically builds and deploys versioned documentation on Read the Docs
- Maintains both development and stable documentation versions

## Release Workflow

### 1. Prepare for Release

1. **Update Version**: Update the version using `uv`:

   ```python
   uv version --bump major
   # possible values: major, minor, patch, stable, alpha, beta, rc, post, dev]
   ```

2. **Update Changelog**: Add release notes to `docs/changelog.md`


### 2. Create Release

1. **Create a pull-request from develop to main**

2. **Create and Push Tag**

### 3. Post-Release

1. **Verify PyPI Publication**: Check https://pypi.org/project/atlas-model/
2. **Verify Documentation**: Check the documentation site for the new version
3. **Create GitHub Release**: Optionally create a GitHub release with release notes

## Documentation Versioning

### How It Works

The documentation is hosted on [Read the Docs](https://readthedocs.org/), which
builds the site automatically from the repository (see `.readthedocs.yaml`). The
build is driven by `zensical` and `uv`; Read the Docs handles hosting, the
version selector, and the canonical/latest aliases.

- **Development docs** (`latest`): built automatically on every push to the
  default branch.
- **Version docs** (e.g., `0.1.0`, `0.2.0`): built automatically when a version
  tag is pushed, once the corresponding version is activated in the Read the
  Docs project.
- **`stable` alias**: points to the most recent active versioned build.

### Version Deployment Process

1. **Branch Pushes** (default branch):
   - Read the Docs rebuilds the `latest` version via the project webhook.

2. **Version Tag Pushes** (e.g., `v0.2.0`):
   - The tag appears in the Read the Docs *Versions* dashboard.
   - Activate the version there (or enable "build new tags automatically") to
     publish a dedicated, versioned documentation build.
   - Read the Docs updates the `stable` alias to the latest active version.

### Manual Documentation Operations

Version management is done from the Read the Docs **Versions** dashboard of the
project (activate / deactivate / hide versions, set the default version). To
reproduce a build locally:

```bash
# Install the documentation dependency group
uv sync --group docs

# Build the static site (output in ./public)
uv run zensical build

# Build and serve locally on http://localhost:8000
uv run zensical serve
```
