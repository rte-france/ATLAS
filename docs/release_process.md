# Release Process

This document outlines the process for creating releases and publishing documentation for the Atlas project.

## Overview

The Atlas project uses an automated release workflow that:

- Publishes packages to PyPI when version tags are pushed
- Automatically deploys versioned documentation using MkDocs and Mike
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

1. **Verify PyPI Publication**: Check https://pypi.org/project/rte-atlas/
2. **Verify Documentation**: Check the documentation site for the new version
3. **Create GitHub Release**: Optionally create a GitHub release with release notes

## Documentation Versioning

### How It Works

The documentation system uses [Mike](https://github.com/jimporter/mike) for version management:

- **Development docs** (`dev`): Auto-deployed from `dev` branch
- **Version docs** (e.g., `0.1.0`, `0.2.0`): Auto-deployed from version tags
- **Latest alias**: Points to the most recent stable version

### Version Deployment Process

1. **Main Branch Pushes**:
   - Deploys documentation as `dev` version
   - Updates `latest` alias to `dev`

2. **Version Tag Pushes** (e.g., `v0.2.0`):
   - Extracts version from tag (removes `v` prefix)
   - Deploys documentation with version number
   - Updates `latest` alias to new version

### Manual Documentation Operations

```bash
# List all deployed versions
uv run mike list

# Deploy a specific version manually
uv run mike deploy --push --update-aliases 0.2.0 latest

# Set default version
uv run mike set-default --push latest

# Delete a version
uv run mike delete --push old-version
```
