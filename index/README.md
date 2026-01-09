# Package Index

This directory contains the PyPI "simple" index structure for deptry wheels hosted on GitHub releases.

## Structure

```
index/
├── index.html          # Root index listing all packages
└── deptry/
    └── index.html      # Package-specific index listing all deptry wheels
```

## How it Works

1. **Wheels are hosted on GitHub Releases**: Each tagged release (e.g., `v0.24.0`) contains pre-built wheels
2. **Index files are committed to the repository**: This directory is automatically updated by CI
3. **UV fetches index via GitHub raw URLs**: The index is accessed at `https://raw.githubusercontent.com/doppelxyz/deptry/main/index/`

## Usage

Add to your `pyproject.toml`:

```toml
dependencies = ["deptry==0.24.0+doppel"]

[[tool.uv.index]]
name = "doppel-deptry"
url = "https://raw.githubusercontent.com/doppelxyz/deptry/main/index/"
explicit = true

[tool.uv.sources]
deptry = { index = "doppel-deptry" }
```

## CI Updates

When a new release is created:
1. Wheels are built and uploaded to the GitHub release
2. `index/deptry/index.html` is regenerated with links to the new wheels
3. Changes are committed and pushed to the `main` branch

This ensures the index always points to the latest available wheels.
