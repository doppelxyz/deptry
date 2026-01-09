# Release Process

This fork uses dynamic versioning based on git tags. The version is **automatically** set during CI builds.

## Creating a New Release

1. **Tag the commit with the version you want** on the `uv-workspace-support` branch (matching upstream deptry version):
   ```bash
   git checkout uv-workspace-support
   git tag v0.24.0
   git push origin v0.24.0
   ```

2. **GitHub Actions will automatically**:
   - Extract version from tag (e.g., `v0.24.0` → `0.24.0+doppel`)
   - Update `pyproject.toml` with the versioned build
   - Build wheels for Linux x86_64, macOS x86_64, and macOS ARM64
   - Create a GitHub release with all wheels
   - Update `index/deptry/index.html` with links to the new wheels
   - Commit the updated index back to the `uv-workspace-support` branch

3. **The release will be available at**:
   ```
   https://github.com/doppelxyz/deptry/releases/download/v0.24.0/
   ```

4. **The package index is hosted at**:
   ```
   https://raw.githubusercontent.com/doppelxyz/deptry/uv-workspace-support/index/
   ```

## Usage in Other Projects

Update your `pyproject.toml`:

```toml
dependencies = [
    "deptry==0.24.0+doppel",
]

[[tool.uv.index]]
name = "doppel-deptry"
url = "https://raw.githubusercontent.com/doppelxyz/deptry/uv-workspace-support/index/"
explicit = true

[tool.uv.sources]
deptry = { index = "doppel-deptry" }
```

The index is automatically updated when new releases are created on the `uv-workspace-support` branch.

## Version Format

- **Git tag**: `v0.24.0` (matches upstream deptry)
- **Built wheel**: `0.24.0+doppel` (local version identifier)
- **Codebase**: `0.0.0+dev` (placeholder, dynamically replaced by CI)

## Important Notes

- The version in `pyproject.toml` is a placeholder (`0.0.0+dev`)
- DO NOT manually update the version in the codebase
- The CI will fail if not triggered by a git tag
- Always use `+doppel` suffix to distinguish from upstream
- **Keep `main` branch clean**: All Doppel-specific changes live on `uv-workspace-support`
- The `main` branch is reserved for syncing with upstream deptry
