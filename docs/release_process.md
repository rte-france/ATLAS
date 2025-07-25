# Release Process

This document outlines the process for creating releases and publishing documentation for the Atlas project.

## Overview

The Atlas project uses an automated release workflow that:
- Publishes packages to PyPI when version tags are pushed
- Automatically deploys versioned documentation using MkDocs and Mike
- Maintains both development and stable documentation versions

## Release Workflow

### 1. Prepare for Release

1. **Update Version**: Update the version in `pyproject.toml`:
   ```toml
   [project]
   name = "atlas"
   version = "0.2.0"  # Update this
   ```

2. **Update Changelog**: Add release notes to `docs/changelog.md`

3. **Run Quality Checks**:
   ```bash
   # Lint and format
   ruff check
   ruff format

   # Type checking
   mypy

   # Run tests
   pytest --cov=atlas
   ```

4. **Test Documentation Build**:
   ```bash
   # Build docs locally
   mkdocs build

   # Serve docs for review
   mkdocs serve
   ```

### 2. Create Release

1. **Commit Changes**:
   ```bash
   git add .
   git commit -m "chore: prepare release v0.2.0"
   git push origin main
   ```

2. **Create and Push Tag** (from main branch only):
   ```bash
   # Ensure you're on main branch
   git checkout main
   git pull origin main

   # Create and push tag
   git tag v0.2.0
   git push origin v0.2.0
   ```

3. **Verify Workflows**: Check GitHub Actions to ensure:
   - Package builds and publishes to PyPI
   - Documentation deploys with new version

### 3. Post-Release

1. **Verify PyPI Publication**: Check https://pypi.org/project/atlas/
2. **Verify Documentation**: Check the documentation site for the new version
3. **Create GitHub Release**: Optionally create a GitHub release with release notes

## Documentation Versioning

### How It Works

The documentation system uses [Mike](https://github.com/jimporter/mike) for version management:

- **Development docs** (`dev`): Auto-deployed from `main` branch
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

## Workflow Files

### Documentation Deployment (`.github/workflows/docs-deploy.yml`)
- Triggers on pushes to `main` and version tags
- Deploys development docs for main branch
- Deploys versioned docs for tags (only from main branch)
- Includes PR preview validation
- Verifies tag origin before deploying

### Package Publishing (`.github/workflows/publish.yml`)
- Triggers on version tags (only from main branch)
- Verifies tag was created from main branch
- Validates version matches pyproject.toml
- Builds and publishes to PyPI
- Requires `PYPI_API_TOKEN` secret

## Requirements

### GitHub Secrets
- `PYPI_API_TOKEN`: PyPI API token for package publishing

### Repository Settings
- GitHub Pages must be enabled
- Source should be set to "Deploy from a branch" with `gh-pages` branch

### Dependencies
The documentation dependencies are defined in `pyproject.toml`:
```toml
[dependency-groups]
docs = [
    "mike>=2.1.3",
    "mkdocs-jupyter>=0.25.1",
    "mkdocs-material>=9.6.11",
    "mkdocstrings>=0.29.1",
    "mkdocstrings-python>=1.16.10",
]
```

## Testing

### Test Release Process
Use the test workflow to validate the release process:

```bash
# Go to GitHub Actions -> Test Release Workflow Integration
# Click "Run workflow" and specify a test version
```

This will validate all release logic without actually publishing.

## Troubleshooting

### Documentation Not Deploying
1. Check GitHub Actions logs
2. Verify `gh-pages` branch exists
3. Ensure GitHub Pages is configured correctly
4. Check that `contents: write` permission is granted
5. **Verify tag was created from main branch**

### Version Not Showing
1. Verify tag format matches `v*` pattern
2. Check that mike commands executed successfully
3. Review git configuration in workflow
4. **Ensure tag originates from main branch**

### Package Not Publishing
1. **Verify tag was created from main branch**
2. Check `PYPI_API_TOKEN` secret is set
3. Ensure version in `pyproject.toml` matches tag
4. Confirm tag commit is ancestor of main branch

### Tag Rejected
If you see "Tag was not created from main branch" error:
1. Ensure you're on main branch: `git checkout main`
2. Pull latest changes: `git pull origin main`
3. Create tag from main: `git tag v1.0.0`
4. Push tag: `git push origin v1.0.0`
