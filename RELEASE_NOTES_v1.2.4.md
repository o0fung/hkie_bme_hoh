## HKIE BME HOH v1.2.4

This release prepares the project for automated publishing to PyPI from GitHub Releases.

### What’s new

- Added GitHub Actions workflow for PyPI publishing via Trusted Publishing:
  - `.github/workflows/publish-pypi.yml`
  - Triggered on `release: published` and manual `workflow_dispatch`
  - Builds `sdist` and `wheel`, then publishes with `pypa/gh-action-pypi-publish`
- Improved packaging metadata in `pyproject.toml`:
  - Switched to SPDX license string (`MIT`)
  - Added `Programming Language :: Python :: 3 :: Only`
  - Added project URLs for `Issues` and `Releases`
  - Updated setuptools package discovery to include all subpackages (`app*`, `config*`, `assets*`)
- Cleaned `MANIFEST.in` asset patterns to match existing files and remove noisy build warnings

### Validation

- Confirmed `pyproject.toml` is valid TOML
- Successfully built both distribution artifacts:
  - Source distribution (`.tar.gz`)
  - Wheel (`.whl`)

### Maintainer note

To enable publish workflow end-to-end, configure PyPI Trusted Publisher for this repo and workflow (`publish-pypi.yml`, environment `pypi`).
